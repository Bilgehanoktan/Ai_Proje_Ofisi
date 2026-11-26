"""MOD-012 / MOD-014: Live product memory promotion & external effect/budget coordinator.

Connects verified task outputs to controlled product memory promotion
(CANDIDATE -> VERIFIED -> PROMOTED with strict separation of duties) and
reconciles external API/webhook dispatches against BudgetAndEffectLedger
and PostgreSQL 087 tables.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict
from typing import Any, Callable
from uuid import uuid4

from company_os.budget.ledger import (
    BudgetAndEffectLedger,
    ExternalEffectEntry,
    ReservationState,
)
from company_os.catalog.memory_promotion import (
    MemoryRecord,
    ProductMemoryPromotionPipeline,
    PromotionState,
)
from company_os.projections.sse_stream import ProjectionEvent

DEFAULT_ALLOWED_WEBHOOK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _memory_to_dict(rec: MemoryRecord) -> dict[str, Any]:
    return {
        "tenant_id": rec.tenant_id,
        "record_id": rec.record_id,
        "summary": rec.summary,
        "evidence_digest": rec.evidence_digest,
        "state": rec.state.value,
        "verified_by": rec.verified_by,
        "promoted_by": rec.promoted_by,
    }


def _effect_to_dict(entry: ExternalEffectEntry) -> dict[str, Any]:
    return asdict(entry)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block HTTP 3xx redirects so an allowlisted host cannot redirect to an untrusted host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, f"REDIRECT_BLOCKED:{msg}", headers, fp)


def _default_loopback_webhook_dispatch(
    target_url: str, payload: dict[str, Any], *, timeout: float = 5.0
) -> dict[str, Any]:
    """Bounded stdlib HTTP POST dispatcher for allowed webhook endpoints."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        target_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler())
    try:
        with opener.open(req, timeout=timeout) as resp:
            status_code = int(getattr(resp, "status", 200))
            return {"outcome": "COMMITTED", "http_status": status_code}
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500:
            return {"outcome": "REVERTED", "http_status": int(exc.code)}
        return {"outcome": "UNKNOWN", "http_status": int(exc.code)}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"outcome": "UNKNOWN", "http_status": 0}


class LiveMemoryAndBudgetCoordinator:
    """Thread-safe coordinator for MOD-012 memory promotions and MOD-014 budget/effects."""

    def __init__(
        self,
        *,
        tenant_id: str,
        budget_limit_minor: int = 1000,
        max_single_effect_minor: int | None = None,
        allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_WEBHOOK_HOSTS,
        persist_promotion: Callable[[MemoryRecord], None] | None = None,
        persist_effect: Callable[[ExternalEffectEntry], None] | None = None,
        dispatcher: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        max_events: int = 200,
    ) -> None:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("TENANT_ID_REQUIRED")
        if type(budget_limit_minor) is not int or budget_limit_minor <= 0:
            raise ValueError("BUDGET_LIMIT_POSITIVE_REQUIRED")
        if max_single_effect_minor is not None and (
            type(max_single_effect_minor) is not int or max_single_effect_minor <= 0
        ):
            raise ValueError("MAX_SINGLE_EFFECT_POSITIVE_REQUIRED")
        self.tenant_id = tenant_id.strip()
        self.allowed_hosts = frozenset(allowed_hosts)
        self._persist_promotion = persist_promotion
        self._persist_effect = persist_effect
        self._dispatcher = dispatcher or _default_loopback_webhook_dispatch
        self._lock = threading.Lock()
        self._pipeline = ProductMemoryPromotionPipeline()
        self._ledger = BudgetAndEffectLedger(
            tenant_id=self.tenant_id,
            budget_limit_minor=budget_limit_minor,
            max_single_effect_minor=max_single_effect_minor,
        )
        self._effect_reservations: dict[str, str] = {}
        self._events: deque[ProjectionEvent] = deque(maxlen=max_events)
        self._event_seq = 0

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_seq += 1
        self._events.append(
            ProjectionEvent(self._event_seq, self.tenant_id, event_type, dict(payload))
        )

    def _save_promotion(self, rec: MemoryRecord) -> None:
        if self._persist_promotion is not None:
            self._persist_promotion(rec)

    def _save_effect(self, entry: ExternalEffectEntry) -> None:
        if self._persist_effect is not None:
            self._persist_effect(entry)

    # --- MOD-012: Product memory promotion lifecycle ---

    def on_task_verified(self, task_record: Any) -> dict[str, Any] | None:
        """Create a CANDIDATE (and VERIFIED if independently accepted) memory record from a task."""
        verification = getattr(task_record, "verification", None)
        exec_result = getattr(task_record, "exec_result", None)
        if not isinstance(verification, dict) or not verification.get("accepted"):
            return None
        if not isinstance(exec_result, dict) or not exec_result.get("response_sha256"):
            return None

        task_id = str(getattr(task_record, "task_id", "") or "").strip()
        title = str(getattr(task_record, "title", "") or "").strip()
        work_type = str(getattr(task_record, "work_type", "SOFTWARE") or "SOFTWARE").strip()
        verifier_id = str(verification.get("verified_by") or "INDEPENDENT_LOCAL_VERIFIER").strip()
        digest = f"sha256:{exec_result['response_sha256']}"
        record_id = f"mem-{task_id[:12]}" if task_id else f"mem-{uuid4().hex[:12]}"
        summary = f"[{work_type}] {title} — doğrulanan ajan çıktısı"

        with self._lock:
            rec = self._pipeline.submit_candidate(self.tenant_id, record_id, summary, digest)
            self._emit("MemoryCandidateCreated", {"record_id": record_id, "work_type": work_type})
            rec = self._pipeline.verify(self.tenant_id, record_id, verifier_id=verifier_id)
            self._emit(
                "MemoryCandidateVerified",
                {"record_id": record_id, "verified_by": verifier_id},
            )
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    def submit_candidate(
        self, *, record_id: str, summary: str, evidence_digest: str
    ) -> dict[str, Any]:
        with self._lock:
            rec = self._pipeline.submit_candidate(
                self.tenant_id, record_id.strip(), summary.strip(), evidence_digest.strip()
            )
            self._emit("MemoryCandidateCreated", {"record_id": rec.record_id})
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    def verify_candidate(self, *, record_id: str, verifier_id: str) -> dict[str, Any]:
        with self._lock:
            rec = self._pipeline.verify(self.tenant_id, record_id.strip(), verifier_id.strip())
            self._emit(
                "MemoryCandidateVerified",
                {"record_id": rec.record_id, "verified_by": rec.verified_by},
            )
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    def promote_memory(self, *, record_id: str, approver_id: str) -> dict[str, Any]:
        with self._lock:
            rec = self._pipeline.promote(self.tenant_id, record_id.strip(), approver_id.strip())
            self._emit(
                "MemoryPromoted",
                {
                    "record_id": rec.record_id,
                    "verified_by": rec.verified_by,
                    "promoted_by": rec.promoted_by,
                },
            )
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    def reject_memory(self, *, record_id: str, reviewer_id: str) -> dict[str, Any]:
        if not reviewer_id or not reviewer_id.strip():
            raise ValueError("REVIEWER_ID_REQUIRED")
        with self._lock:
            rec = self._pipeline._get_scoped(self.tenant_id, record_id.strip())
            if rec.state == PromotionState.PROMOTED:
                raise ValueError("CANNOT_REJECT_PROMOTED_MEMORY")
            rec.state = PromotionState.REJECTED
            self._emit(
                "MemoryRejected",
                {"record_id": rec.record_id, "reviewer_id": reviewer_id.strip()},
            )
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    def list_promotions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                _memory_to_dict(rec)
                for (tid, _), rec in self._pipeline._records.items()
                if tid == self.tenant_id
            ]

    def search_promoted_memory(self, query: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                _memory_to_dict(rec)
                for rec in self._pipeline.search_promoted(self.tenant_id, query)
            ]

    def repropose_memory(
        self, *, record_id: str, summary: str, evidence_digest: str
    ) -> dict[str, Any]:
        with self._lock:
            rec = self._pipeline.repropose_rejected(
                self.tenant_id, record_id.strip(), summary, evidence_digest
            )
            self._emit("MemoryReproposed", {"record_id": rec.record_id})
            snapshot = _memory_to_dict(rec)
        self._save_promotion(rec)
        return snapshot

    # --- MOD-014: External effect & budget reservation / reconciliation ---

    def _validate_target_url(self, target_url: str) -> str:
        if type(target_url) is not str or not target_url.strip():
            raise ValueError("TARGET_URL_REQUIRED")
        cleaned = target_url.strip()
        parsed = urllib.parse.urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("INVALID_TARGET_URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("CREDENTIALS_IN_URL_FORBIDDEN")
        host = parsed.hostname.lower()
        if host not in self.allowed_hosts:
            raise PermissionError("EXTERNAL_HOST_NOT_ALLOWED")
        if host not in DEFAULT_ALLOWED_WEBHOOK_HOSTS and parsed.scheme != "https":
            raise PermissionError("HTTPS_REQUIRED_FOR_EXTERNAL_HOST")
        return cleaned

    def execute_external_effect(
        self,
        *,
        idempotency_key: str,
        provider: str,
        target_url: str,
        payload: dict[str, Any],
        reserved_minor: int,
        actual_minor: int | None = None,
    ) -> dict[str, Any]:
        """Reserve budget, dispatch external call idempotently, and reconcile ledger."""
        key = str(idempotency_key or "").strip()
        prov = str(provider or "").strip()
        if not key or not prov:
            raise ValueError("IDEMPOTENCY_KEY_AND_PROVIDER_REQUIRED")
        url = self._validate_target_url(target_url)
        if not isinstance(payload, dict):
            raise ValueError("PAYLOAD_OBJECT_REQUIRED")
        if type(reserved_minor) is not int or reserved_minor <= 0:
            raise ValueError("NON_ZERO_RESERVATION_REQUIRED")

        with self._lock:
            existing = self._ledger._effects_by_key.get(key)
            if existing is not None:
                if existing.provider != prov:
                    raise ValueError("EXTERNAL_EFFECT_IDEMPOTENCY_CONFLICT")
                return {
                    "replayed": True,
                    "effect": _effect_to_dict(existing),
                    "reservation_id": self._effect_reservations.get(key),
                    "budget": self._budget_snapshot_unlocked(),
                }
            reservation_id = f"res-{uuid4().hex[:12]}"
            effect_id = f"eff-{uuid4().hex[:12]}"
            self._ledger.reserve(reservation_id, reserved_minor)

        dispatch_res = self._dispatcher(url, payload)
        outcome = str(dispatch_res.get("outcome") or "UNKNOWN").upper()
        settled_cost = reserved_minor if actual_minor is None else int(actual_minor)

        with self._lock:
            if outcome == "COMMITTED":
                self._ledger.settle(reservation_id, min(settled_cost, reserved_minor))
                entry = self._ledger.record_external_effect(effect_id, key, prov, "COMMITTED")
                self._emit(
                    "ExternalEffectCommitted",
                    {
                        "effect_id": effect_id,
                        "provider": prov,
                        "settled_minor": min(settled_cost, reserved_minor),
                    },
                )
            elif outcome == "REVERTED":
                self._ledger.release(reservation_id)
                entry = self._ledger.record_external_effect(effect_id, key, prov, "REVERTED")
                self._emit("ExternalEffectReverted", {"effect_id": effect_id, "provider": prov})
            else:
                self._ledger.mark_unknown(reservation_id)
                entry = self._ledger.record_external_effect(effect_id, key, prov, "UNKNOWN")
                self._emit(
                    "ExternalEffectUnknown",
                    {"effect_id": effect_id, "reservation_id": reservation_id, "provider": prov},
                )
            self._effect_reservations[key] = reservation_id
            result = {
                "replayed": False,
                "effect": _effect_to_dict(entry),
                "reservation_id": reservation_id,
                "http_status": dispatch_res.get("http_status"),
                "budget": self._budget_snapshot_unlocked(),
            }
        self._save_effect(entry)
        return result

    def reconcile_unknown_effect(
        self,
        *,
        idempotency_key: str,
        actual_minor: int,
        final_status: str = "COMMITTED",
    ) -> dict[str, Any]:
        """Resolve an UNKNOWN reservation & external effect to unblock future spend."""
        key = str(idempotency_key or "").strip()
        status = str(final_status or "COMMITTED").strip().upper()
        if status not in ("COMMITTED", "REVERTED"):
            raise ValueError("INVALID_RECONCILE_STATUS")
        if type(actual_minor) is not int or actual_minor < 0:
            raise ValueError("ACTUAL_MINOR_NON_NEGATIVE_REQUIRED")

        with self._lock:
            entry = self._ledger._effects_by_key.get(key)
            res_id = self._effect_reservations.get(key)
            if entry is None or res_id is None:
                raise KeyError("EXTERNAL_EFFECT_NOT_FOUND")
            res = self._ledger._reservations.get(res_id)
            if res is None or res.state != ReservationState.UNKNOWN:
                raise ValueError("RESERVATION_NOT_UNKNOWN")
            self._ledger.settle(res_id, actual_minor)
            entry.status = status
            self._emit(
                "ExternalEffectReconciled",
                {
                    "effect_id": entry.effect_id,
                    "reservation_id": res_id,
                    "actual_minor": actual_minor,
                    "status": status,
                },
            )
            snapshot = {
                "effect": _effect_to_dict(entry),
                "reservation_id": res_id,
                "budget": self._budget_snapshot_unlocked(),
            }
        self._save_effect(entry)
        return snapshot

    def _budget_snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "budget_limit_minor": self._ledger.budget_limit_minor,
            "max_single_effect_minor": self._ledger.max_single_effect_minor,
            "spent_minor": self._ledger.spent_minor,
            "held_minor": self._ledger.held_minor,
            "available_minor": self._ledger.available_minor,
            "blocked_by_unknown": self._ledger.has_unresolved_unknown(),
        }

    def budget_summary(self) -> dict[str, Any]:
        with self._lock:
            return self._budget_snapshot_unlocked()

    def provider_summary(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return self._ledger.provider_summary()

    def list_effects(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_effect_to_dict(e) for e in self._ledger._effects_by_key.values()]

    def recent_events(self) -> list[ProjectionEvent]:
        with self._lock:
            return list(self._events)
