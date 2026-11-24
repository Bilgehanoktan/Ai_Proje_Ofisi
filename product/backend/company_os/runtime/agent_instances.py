"""MOD-003 / MOD-011: Canonical AgentInstance identity, attempt binding & authorized read service.

Maintains distinct AgentInstance identities (multiple instances may share a role_id),
links active runs to exact (task_id, attempt_id, worker_principal) tuples, supersedes
stale attempts on retry so old attempts never remain active, and enforces tenant/project
authorization on reads.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

ROLE_ID_PATTERN = re.compile(r"^(?:MGR|EXP|QA)-[0-9]{2,3}$")


class AgentState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    STALE = "STALE"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _require_uuid(value: str, field_name: str) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{field_name}_UUID_REQUIRED") from None
    return value


@dataclass
class AgentInstanceRecord:
    agent_instance_id: str
    tenant_id: str
    project_id: str
    role_id: str
    display_name: str
    worker_principal: str
    state: AgentState = AgentState.IDLE
    active_task_id: str | None = None
    active_attempt_id: str | None = None
    active_task_title: str | None = None
    revision: int = 0
    last_seen_at: str = ""
    last_seen_monotonic: float = 0.0

    def to_dict(self, *, effective_state: str | None = None) -> dict[str, Any]:
        st = effective_state or self.state.value
        is_active = st == AgentState.RUNNING.value
        return {
            "agent_instance_id": self.agent_instance_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "role_id": self.role_id,
            "display_name": self.display_name,
            "worker_principal": self.worker_principal,
            "state": st,
            "active_task_id": self.active_task_id if is_active else None,
            "active_attempt_id": self.active_attempt_id if is_active else None,
            "active_task_title": self.active_task_title if is_active else None,
            "revision": self.revision,
            "last_seen_at": self.last_seen_at,
        }


class AgentInstanceRegistry:
    """Thread-safe canonical registry for AgentInstance identities and active task attempts."""

    def __init__(
        self,
        *,
        persist_agent: Callable[[AgentInstanceRecord, str | None], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        stale_after_seconds: float = 120.0,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("STALE_AFTER_POSITIVE_REQUIRED")
        self._persist_agent = persist_agent
        self._clock = clock
        self._stale_after = float(stale_after_seconds)
        self._lock = threading.Lock()
        self._agents: dict[str, AgentInstanceRecord] = {}
        self._assignments: list[dict[str, Any]] = []

    def register_agent(
        self,
        *,
        tenant_id: str,
        project_id: str,
        role_id: str,
        display_name: str,
        worker_principal: str,
        agent_instance_id: str | None = None,
    ) -> dict[str, Any]:
        tid = _require_uuid(tenant_id, "TENANT_ID")
        pid = _require_uuid(project_id, "PROJECT_ID")
        rid = str(role_id or "").strip().upper()
        if not ROLE_ID_PATTERN.match(rid):
            raise ValueError("INVALID_ROLE_ID")
        name = str(display_name or "").strip()
        principal = str(worker_principal or "").strip()
        if not name or not principal:
            raise ValueError("DISPLAY_NAME_AND_WORKER_PRINCIPAL_REQUIRED")
        aid = _require_uuid(agent_instance_id, "AGENT_INSTANCE_ID") if agent_instance_id else str(uuid4())

        rec = AgentInstanceRecord(
            agent_instance_id=aid,
            tenant_id=tid,
            project_id=pid,
            role_id=rid,
            display_name=name,
            worker_principal=principal,
            state=AgentState.IDLE,
            revision=0,
            last_seen_at=_now_iso(),
            last_seen_monotonic=self._clock(),
        )
        with self._lock:
            self._agents[aid] = rec
            snapshot = rec.to_dict()
        if self._persist_agent is not None:
            self._persist_agent(rec, None)
        return snapshot

    def select_idle_for_role(
        self, *, tenant_id: str, project_id: str, role_id: str
    ) -> str | None:
        with self._lock:
            candidates = [
                a
                for a in self._agents.values()
                if a.tenant_id == tenant_id
                and a.project_id == project_id
                and a.role_id == role_id
                and a.state == AgentState.IDLE
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda a: (a.revision, a.agent_instance_id))
            return candidates[0].agent_instance_id

    def assign_task(
        self,
        *,
        agent_instance_id: str,
        task_id: str,
        attempt_id: str | None = None,
        task_title: str = "",
    ) -> dict[str, Any]:
        """Bind a task attempt to an AgentInstance; supersedes any prior active attempt for task_id."""
        aid = _require_uuid(agent_instance_id, "AGENT_INSTANCE_ID")
        tid_str = str(task_id or "").strip()
        if not tid_str:
            raise ValueError("TASK_ID_REQUIRED")
        att_id = _require_uuid(attempt_id, "ATTEMPT_ID") if attempt_id else str(uuid4())

        superseded_records: list[AgentInstanceRecord] = []
        with self._lock:
            target = self._agents.get(aid)
            if target is None:
                raise KeyError("AGENT_INSTANCE_NOT_FOUND")
            if target.state == AgentState.BLOCKED:
                raise RuntimeError("AGENT_INSTANCE_BLOCKED")

            # Retry invariant: supersede any previous active attempt for the same task_id
            for other in self._agents.values():
                if (
                    other.tenant_id == target.tenant_id
                    and other.project_id == target.project_id
                    and other.active_task_id == tid_str
                    and other.state == AgentState.RUNNING
                ):
                    other.state = AgentState.IDLE
                    other.active_task_id = None
                    other.active_attempt_id = None
                    other.active_task_title = None
                    other.revision += 1
                    other.last_seen_at = _now_iso()
                    other.last_seen_monotonic = self._clock()
                    superseded_records.append(other)
            for hist in self._assignments:
                if hist["task_id"] == tid_str and hist["status"] == "ACTIVE":
                    hist["status"] = "SUPERSEDED"
                    hist["ended_at"] = _now_iso()

            target.state = AgentState.RUNNING
            target.active_task_id = tid_str
            target.active_attempt_id = att_id
            target.active_task_title = str(task_title or tid_str).strip()
            target.revision += 1
            target.last_seen_at = _now_iso()
            target.last_seen_monotonic = self._clock()
            self._assignments.append(
                {
                    "agent_instance_id": aid,
                    "task_id": tid_str,
                    "attempt_id": att_id,
                    "status": "ACTIVE",
                    "started_at": target.last_seen_at,
                    "ended_at": None,
                }
            )
            snapshot = target.to_dict()

        if self._persist_agent is not None:
            for sup in superseded_records:
                self._persist_agent(sup, "SUPERSEDED")
            self._persist_agent(target, "ACTIVE")
        return snapshot

    def release_task(
        self,
        *,
        agent_instance_id: str,
        attempt_id: str,
        outcome: str = "COMPLETED",
        next_state: AgentState = AgentState.IDLE,
    ) -> dict[str, Any]:
        """Release the active attempt only if attempt_id matches (prevents stale overwrite)."""
        aid = _require_uuid(agent_instance_id, "AGENT_INSTANCE_ID")
        att_id = _require_uuid(attempt_id, "ATTEMPT_ID")
        if next_state not in (AgentState.IDLE, AgentState.BLOCKED):
            raise ValueError("INVALID_RELEASE_STATE")

        with self._lock:
            target = self._agents.get(aid)
            if target is None:
                raise KeyError("AGENT_INSTANCE_NOT_FOUND")
            if target.active_attempt_id != att_id:
                raise ValueError("ATTEMPT_ID_MISMATCH_OR_SUPERSEDED")
            target.state = next_state
            target.active_task_id = None
            target.active_attempt_id = None
            target.active_task_title = None
            target.revision += 1
            target.last_seen_at = _now_iso()
            target.last_seen_monotonic = self._clock()
            for hist in self._assignments:
                if hist["attempt_id"] == att_id and hist["status"] == "ACTIVE":
                    hist["status"] = "COMPLETED" if outcome == "COMPLETED" else "FAILED"
                    hist["ended_at"] = target.last_seen_at
            snapshot = target.to_dict()

        if self._persist_agent is not None:
            self._persist_agent(target, "COMPLETED" if outcome == "COMPLETED" else "FAILED")
        return snapshot

    def heartbeat(self, *, agent_instance_id: str) -> dict[str, Any]:
        aid = _require_uuid(agent_instance_id, "AGENT_INSTANCE_ID")
        with self._lock:
            target = self._agents.get(aid)
            if target is None:
                raise KeyError("AGENT_INSTANCE_NOT_FOUND")
            target.last_seen_at = _now_iso()
            target.last_seen_monotonic = self._clock()
            snapshot = target.to_dict()
        if self._persist_agent is not None:
            self._persist_agent(target, None)
        return snapshot

    def list_authorized(
        self,
        *,
        tenant_id: str,
        project_id: str,
        allowed_tenant_id: str,
        allowed_project_ids: frozenset[str],
    ) -> list[dict[str, Any]]:
        """Return project-scoped AgentInstances; denies missing/foreign tenant or project."""
        tid = _require_uuid(tenant_id, "TENANT_ID")
        pid = _require_uuid(project_id, "PROJECT_ID")
        if tid != allowed_tenant_id or pid not in allowed_project_ids:
            raise PermissionError("AGENT_INSTANCE_SCOPE_DENIED")

        now_mono = self._clock()
        out: list[dict[str, Any]] = []
        with self._lock:
            for rec in self._agents.values():
                if rec.tenant_id != tid or rec.project_id != pid:
                    continue
                is_stale = (now_mono - rec.last_seen_monotonic) > self._stale_after
                effective = AgentState.STALE.value if is_stale else rec.state.value
                out.append(rec.to_dict(effective_state=effective))
        out.sort(key=lambda item: (item["role_id"], item["display_name"], item["agent_instance_id"]))
        return out
