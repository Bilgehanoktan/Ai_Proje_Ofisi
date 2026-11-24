"""MOD-002 / MOD-003 / MOD-011: Live office task submission & AutonomousWorkerDaemon bridge.

Connects office UI task submissions to:
1. Optional canonical DB/Kernel persistence hook (so tasks are recorded in PostgreSQL
   before execution).
2. AutonomousWorkerDaemon claiming queued tasks and invoking the free local Ollama model.
3. Independent structural verification (separate from producer generation) and SSE event
   broadcasting for live UI observation.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from company_os.catalog.extensions_store import Extensions087Store
from company_os.engine.ollama_adapter import DEFAULT_OLLAMA_MODEL, OllamaClient
from company_os.projections.sse_stream import ProjectionEvent
from company_os.runtime.agent_instances import AgentInstanceRegistry, AgentState
from company_os.runtime.worker_daemon import AutonomousWorkerDaemon, DaemonState

ALLOWED_WORK_TYPES = frozenset({"SOFTWARE", "RESEARCH", "SPREADSHEET", "OBLIGATION"})
ROLE_ID_PATTERN = re.compile(r"^(?:MGR|EXP|QA)-[0-9]{2,3}$")
ENGINEER_PILOT_VERSION = "1.0.0"
# Adapted from Agency Agents' Senior Developer approach to scope and verification.
ENGINEER_PILOT_PROMPT = (
    "Sen AI Proje Ofisi EXP-01 yazılım mühendisisin. Verilen kabul ölçütlerini çıkar. "
    "Mevcut davranışı koruyan en küçük değişikliği ve ilgili regresyon kontrolünü belirt. "
    "Gözlenen kanıtı varsayımdan ayır. Çalıştırmadığın testleri ve kullanmadığın araçları açıkça bildir."
)
ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "SOFTWARE": (
        "Sen AI Proje Ofisi içinde çalışan bir yazılım mühendisi ajanısın. "
        "Verilen görev ve kabul ölçütlerine göre somut, doğrulanabilir ve temiz çözüm üret."
    ),
    "RESEARCH": (
        "Sen AI Proje Ofisi içinde çalışan bir araştırma ajanısın. "
        "Görevi yapılandırılmış bulgular, riskler ve önerilen doğrulama adımlarıyla özetle."
    ),
    "SPREADSHEET": (
        "Sen AI Proje Ofisi içinde çalışan bir veri ve tablo ajanısın. "
        "İstenen tablo yapısını, sütunları, formül mantığını ve doğrulama kontrollerini açıkça ver."
    ),
    "OBLIGATION": (
        "Sen AI Proje Ofisi içinde çalışan bir uyumluluk ve yükümlülük ajanısın. "
        "Görevi kontrol listesi, süre/risk sınırı ve kanıt gereksinimleriyle raporla."
    ),
}


class OfficeTaskValidationError(ValueError):
    """Raised when an incoming office task request fails contract validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def validate_office_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an incoming office task submission payload."""
    if not isinstance(payload, dict):
        raise OfficeTaskValidationError("PAYLOAD_OBJECT_REQUIRED")

    title = str(payload.get("title") or "").strip()
    if not 3 <= len(title) <= 200:
        raise OfficeTaskValidationError("TITLE_LENGTH_3_TO_200_REQUIRED")

    goal = str(payload.get("goal") or "").strip()
    if not 10 <= len(goal) <= 4000:
        raise OfficeTaskValidationError("GOAL_LENGTH_10_TO_4000_REQUIRED")

    work_type = str(payload.get("work_type") or "SOFTWARE").strip().upper()
    if work_type not in ALLOWED_WORK_TYPES:
        raise OfficeTaskValidationError("UNSUPPORTED_WORK_TYPE")

    role_id = str(payload.get("role_id") or "EXP-01").strip().upper()
    if not ROLE_ID_PATTERN.match(role_id):
        raise OfficeTaskValidationError("INVALID_ROLE_ID")

    raw_criteria = payload.get("acceptance_criteria")
    if isinstance(raw_criteria, str):
        criteria = [ln.strip() for ln in raw_criteria.splitlines() if ln.strip()]
    elif isinstance(raw_criteria, list):
        criteria = [str(item).strip() for item in raw_criteria if str(item).strip()]
    else:
        criteria = []
    if not criteria:
        criteria = ["Yanıt boş olmamalı ve görev hedefini doğrudan ele almalıdır."]
    if len(criteria) > 20:
        raise OfficeTaskValidationError("TOO_MANY_ACCEPTANCE_CRITERIA")

    model = str(payload.get("model") or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    if len(model) > 120:
        raise OfficeTaskValidationError("INVALID_MODEL_NAME")

    read_path = str(payload.get("read_path") or "").strip() or None
    if read_path is not None:
        if "/" in read_path or "\\" in read_path or read_path in {".", ".."} or len(read_path) > 120:
            raise OfficeTaskValidationError("INVALID_READ_PATH")

    return {
        "title": title,
        "goal": goal,
        "work_type": work_type,
        "role_id": role_id,
        "acceptance_criteria": criteria,
        "model": model,
        "read_path": read_path,
    }


def verify_office_task_output(task: dict[str, Any], exec_result: dict[str, Any]) -> dict[str, Any]:
    """Independent structural verifier for local Ollama task outputs."""
    checks: list[dict[str, Any]] = []
    text = str(exec_result.get("response") or "").strip()
    digest = str(exec_result.get("response_sha256") or "")
    expected_digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""

    non_empty = len(text) >= 20
    checks.append({"check": "min_response_length_20", "passed": non_empty, "length": len(text)})

    digest_match = bool(digest) and digest == expected_digest
    checks.append({"check": "response_sha256_integrity", "passed": digest_match})

    eval_count = int(exec_result.get("eval_count") or 0)
    has_tokens = eval_count > 0
    checks.append({"check": "model_eval_tokens_positive", "passed": has_tokens, "eval_count": eval_count})

    accepted = all(item["passed"] for item in checks)
    reason = "LOCAL_VERIFIER_CHECKS_PASSED" if accepted else next(
        f"FAILED_{item['check'].upper()}" for item in checks if not item["passed"]
    )
    return {
        "accepted": accepted,
        "reason": reason,
        "verified_by": "INDEPENDENT_LOCAL_VERIFIER",
        "work_type": task.get("work_type", "SOFTWARE"),
        "checks": checks,
        "verified_at": _now_iso(),
    }


@dataclass
class OfficeTaskRecord:
    """Mutable lifecycle record for a task submitted from the office UI."""

    task_id: str
    tenant_id: str
    title: str
    goal: str
    work_type: str
    role_id: str
    acceptance_criteria: list[str]
    model: str
    state: str = "QUEUED"
    read_path: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    db_persisted: bool = False
    db_receipt: dict[str, Any] | None = None
    exec_result: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    error: str | None = None
    agent_instance_id: str | None = None
    attempt_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "goal": self.goal,
            "work_type": self.work_type,
            "role_id": self.role_id,
            "acceptance_criteria": list(self.acceptance_criteria),
            "model": self.model,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "db_persisted": self.db_persisted,
            "db_receipt": self.db_receipt,
            "exec_result": self.exec_result,
            "verification": self.verification,
            "error": self.error,
            "agent_instance_id": self.agent_instance_id,
            "attempt_id": self.attempt_id,
        }


class LiveOfficeTaskRunner:
    """Connects office task submissions to AutonomousWorkerDaemon + local Ollama."""

    def __init__(
        self,
        *,
        tenant_id: str = "t1",
        ollama_client: OllamaClient | None = None,
        persist_submission: Callable[[dict[str, Any], str | None], dict[str, Any]] | None = None,
        persist_result: Callable[[OfficeTaskRecord], None] | None = None,
        on_task_accepted: Callable[[OfficeTaskRecord], Any] | None = None,
        agent_registry: AgentInstanceRegistry | None = None,
        registry_tenant_id: str | None = None,
        engineer_pilot_catalog: Extensions087Store | None = None,
        research_broker_reader: Callable[[str], dict[str, Any]] | None = None,
        queue_runner: Any | None = None,
        project_id: str | None = None,
        verifier: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = verify_office_task_output,
        poll_interval_seconds: float = 0.5,
        max_consecutive_errors: int = 5,
        max_history: int = 40,
    ) -> None:
        self.tenant_id = tenant_id
        self.ollama = ollama_client or OllamaClient()
        self._persist_submission = persist_submission
        self._persist_result = persist_result
        self._on_task_accepted = on_task_accepted
        self._agent_registry = agent_registry
        self._registry_tenant_id = registry_tenant_id
        if engineer_pilot_catalog is not None and not registry_tenant_id:
            raise ValueError("ENGINEER_PILOT_TENANT_REQUIRED")
        self._engineer_pilot_catalog = engineer_pilot_catalog
        self._research_broker_reader = research_broker_reader
        self._queue_runner = queue_runner
        self._project_id = project_id
        self._verifier = verifier
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._tasks: dict[str, OfficeTaskRecord] = {}
        self._task_order: deque[str] = deque(maxlen=max_history)
        self._events: deque[ProjectionEvent] = deque(maxlen=200)
        self._event_seq = 0
        self._thread: threading.Thread | None = None
        self._daemon = AutonomousWorkerDaemon(
            claim_next=self._claim_next,
            execute_task=self._execute_task,
            verify_task=self._verify_task,
            on_event=self._on_daemon_event,
            poll_interval_seconds=poll_interval_seconds,
            max_consecutive_errors=max_consecutive_errors,
        )

    def _record_event(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._event_seq += 1
            self._events.append(
                ProjectionEvent(
                    self._event_seq,
                    self.tenant_id,
                    kind,
                    dict(payload),
                )
            )

    def submit_task(
        self, payload: dict[str, Any], *, bearer_token: str | None = None
    ) -> dict[str, Any]:
        """Validate, optionally persist to DB/Kernel, and enqueue for worker execution."""
        normalized = validate_office_task_payload(payload)
        db_receipt: dict[str, Any] | None = None
        db_persisted = False
        task_id = str(uuid4())

        if self._persist_submission is not None:
            db_receipt = self._persist_submission(normalized, bearer_token)
            if isinstance(db_receipt, dict) and db_receipt.get("task_id"):
                task_id = str(db_receipt["task_id"])
            db_persisted = bool(db_receipt and db_receipt.get("persisted", True))

        record = OfficeTaskRecord(
            task_id=task_id,
            tenant_id=self.tenant_id,
            title=normalized["title"],
            goal=normalized["goal"],
            work_type=normalized["work_type"],
            role_id=normalized["role_id"],
            acceptance_criteria=normalized["acceptance_criteria"],
            model=normalized["model"],
            read_path=normalized.get("read_path"),
            state="QUEUED",
            db_persisted=db_persisted,
            db_receipt=db_receipt,
        )
        with self._lock:
            self._tasks[task_id] = record
            self._task_order.appendleft(task_id)
            self._queue.append(task_id)

        self._record_event(
            "OfficeTaskQueued",
            {
                "task_id": task_id,
                "title": record.title,
                "work_type": record.work_type,
                "role_id": record.role_id,
                "db_persisted": db_persisted,
            },
        )
        return record.to_dict()

    def _claim_next(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._queue:
                return None
            task_id = self._queue.popleft()
            record = self._tasks.get(task_id)
            if record is None:
                return None
            record.state = "RUNNING"
            record.updated_at = _now_iso()
            role_id = record.role_id
            title = record.title
        if self._agent_registry is not None and self._registry_tenant_id and self._project_id:
            chosen = self._agent_registry.select_idle_for_role(
                tenant_id=self._registry_tenant_id,
                project_id=self._project_id,
                role_id=role_id,
            )
            if chosen is not None:
                attempt_id = str(uuid4())
                self._agent_registry.assign_task(
                    agent_instance_id=chosen,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    task_title=title,
                )
                with self._lock:
                    record.agent_instance_id = chosen
                    record.attempt_id = attempt_id
                self._record_event(
                    "AgentInstanceAssigned",
                    {"agent_instance_id": chosen, "task_id": task_id, "attempt_id": attempt_id, "role_id": role_id},
                )
        with self._lock:
            record_dict = record.to_dict()
            record_dict["read_path"] = record.read_path
            return record_dict

    def _execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        criteria_lines = "\n".join(f"- {c}" for c in task.get("acceptance_criteria") or [])
        prompt = (
            f"Görev Başlığı: {task['title']}\n"
            f"İş Türü: {task['work_type']}\n"
            f"Ajan Rolü: {task['role_id']}\n"
            f"Hedef:\n{task['goal']}\n\n"
            f"Kabul Ölçütleri:\n{criteria_lines}\n\n"
            "Türkçe, net, somut ve uygulanabilir yanıt üret."
        )
        system = ROLE_SYSTEM_PROMPTS.get(str(task["work_type"]), ROLE_SYSTEM_PROMPTS["SOFTWARE"])
        pilot_digest = None
        if (
            self._engineer_pilot_catalog is not None
            and self._registry_tenant_id
            and task["role_id"] == "EXP-01"
            and task["work_type"] == "SOFTWARE"
        ):
            pilot_digest = hashlib.sha256(ENGINEER_PILOT_PROMPT.encode("utf-8")).hexdigest()
            entries = self._engineer_pilot_catalog.list_catalog_entries(self._registry_tenant_id)
            if not any(
                entry["tenant_id"] == self._registry_tenant_id
                and entry["kind"] == "ROLE"
                and entry["name"] == "EXP-01"
                and entry["version"] == ENGINEER_PILOT_VERSION
                and entry["digest"] == pilot_digest
                and entry["active"] is True
                for entry in entries
            ):
                raise OfficeTaskValidationError("ENGINEER_PILOT_CATALOG_PIN_MISSING_OR_INVALID")
            system = ENGINEER_PILOT_PROMPT
        broker_read_receipt = None
        if task["work_type"] == "RESEARCH" and task.get("read_path"):
            read_path = str(task["read_path"])
            if self._queue_runner is not None:
                self._queue_runner.execute_task(task)
            if self._research_broker_reader is None:
                raise OfficeTaskValidationError("RESEARCH_BROKER_READER_NOT_CONFIGURED")
            broker_read_receipt = self._research_broker_reader(read_path)
        gen = self.ollama.generate(prompt, model=str(task.get("model") or DEFAULT_OLLAMA_MODEL), system=system)
        result = gen.to_dict()
        if broker_read_receipt is not None:
            result["broker_read_receipt"] = broker_read_receipt
        if pilot_digest is not None:
            result["role_profile"] = {
                "name": "EXP-01",
                "version": ENGINEER_PILOT_VERSION,
                "sha256": pilot_digest,
            }
        with self._lock:
            rec = self._tasks.get(str(task["task_id"]))
            if rec is not None:
                rec.exec_result = result
                rec.updated_at = _now_iso()
        return result

    def _verify_task(self, task: dict[str, Any], exec_result: dict[str, Any]) -> dict[str, Any]:
        verdict = self._verifier(task, exec_result)
        with self._lock:
            rec = self._tasks.get(str(task["task_id"]))
            if rec is not None:
                rec.verification = verdict
                rec.state = "ACCEPTED" if verdict.get("accepted") else "REJECTED"
                rec.updated_at = _now_iso()
                snapshot = rec
            else:
                snapshot = None
        if snapshot is not None and self._agent_registry is not None and snapshot.agent_instance_id and snapshot.attempt_id:
            try:
                self._agent_registry.release_task(
                    agent_instance_id=snapshot.agent_instance_id,
                    attempt_id=snapshot.attempt_id,
                    outcome="COMPLETED" if verdict.get("accepted") else "FAILED",
                    next_state=AgentState.IDLE,
                )
                self._record_event(
                    "AgentInstanceReleased",
                    {"agent_instance_id": snapshot.agent_instance_id, "task_id": snapshot.task_id, "attempt_id": snapshot.attempt_id},
                )
            except Exception:
                pass
        if snapshot is not None and self._persist_result is not None:
            try:
                self._persist_result(snapshot)
            except Exception:
                # Verification result stays intact; persistence failure is surfaced separately.
                pass
        if snapshot is not None and verdict.get("accepted") and self._on_task_accepted is not None:
            try:
                self._on_task_accepted(snapshot)
            except Exception:
                # Memory promotion candidate creation never alters task verification verdict.
                pass
        return verdict

    def _on_daemon_event(self, kind: str, payload: dict[str, Any]) -> None:
        if kind == "WorkerTaskError":
            task_id = str(payload.get("task_id") or "")
            release_pair: tuple[str, str] | None = None
            with self._lock:
                rec = self._tasks.get(task_id)
                if rec is not None:
                    rec.state = "ERROR"
                    err_type = str(payload.get("error_type") or "WORKER_ERROR")
                    err_detail = str(payload.get("error") or "").strip()
                    rec.error = f"{err_type}: {err_detail}" if err_detail and err_detail != err_type else err_type
                    rec.updated_at = _now_iso()
                    if rec.agent_instance_id and rec.attempt_id:
                        release_pair = (rec.agent_instance_id, rec.attempt_id)
            if release_pair is not None and self._agent_registry is not None:
                try:
                    self._agent_registry.release_task(
                        agent_instance_id=release_pair[0],
                        attempt_id=release_pair[1],
                        outcome="FAILED",
                        next_state=AgentState.IDLE,
                    )
                except Exception:
                    pass
        self._record_event(kind, payload)

    def run_once(self) -> Any:
        """Process at most one queued task synchronously (useful for tests/CLI)."""
        return self._daemon.run_once()

    def start_background(self) -> None:
        """Start AutonomousWorkerDaemon in a background daemon thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._daemon.run_forever,
                name="aipof-live-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        """Request graceful stop of the background worker daemon."""
        self._daemon.request_stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)

    def list_runs(self, *, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._task_order)[:limit]
            return [self._tasks[tid].to_dict() for tid in ids if tid in self._tasks]

    def recent_events(self) -> list[ProjectionEvent]:
        with self._lock:
            return list(self._events)

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            queued = len(self._queue)
            state = self._daemon.stats.state.value
            if self._thread is not None and self._thread.is_alive() and state == DaemonState.IDLE.value:
                state = DaemonState.RUNNING.value
            return {
                "daemon_state": state,
                "queued": queued,
                "processed": self._daemon.stats.processed,
                "accepted": self._daemon.stats.accepted,
                "rejected": self._daemon.stats.rejected,
                "errors": self._daemon.stats.errors,
            }
