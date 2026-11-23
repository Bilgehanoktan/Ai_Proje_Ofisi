"""MOD-013: Autonomous queue dispatcher and independent verifier for Research, Spreadsheet, and Obligation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from company_os.catalog.extensions_store import Extensions087Store
from company_os.workflows.templates import WorkType, validate_work_output


def _canonical_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass
class MultiWorkTypeQueueRunner:
    """Connects MOD-013 work types to AutonomousWorkerDaemon and independent validation."""

    executors: dict[WorkType, Callable[[dict[str, Any]], dict[str, Any]]]
    store: Extensions087Store | None = None

    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        raw_type = task.get("work_type")
        try:
            work_type = WorkType(str(raw_type))
        except ValueError as exc:
            raise ValueError(f"UNSUPPORTED_WORK_TYPE:{raw_type}") from exc
        if work_type not in self.executors:
            raise ValueError(f"EXECUTOR_NOT_REGISTERED:{work_type.value}")
        output = dict(self.executors[work_type](task))
        return {
            "work_type": work_type.value,
            "payload": output,
            "evidence_digest": _canonical_digest(output),
        }

    def verify_task(self, task: dict[str, Any], exec_result: dict[str, Any]) -> dict[str, Any]:
        work_type = WorkType(str(exec_result["work_type"]))
        payload = exec_result.get("payload") or {}
        evidence_digest = str(exec_result.get("evidence_digest") or "")
        try:
            validation = validate_work_output(work_type, payload)
            accepted = bool(validation.get("validated"))
            reason = None
        except ValueError as exc:
            validation = {
                "work_type": work_type.value,
                "template_id": f"WFT-{work_type.value}-01",
                "version": "1.0.0",
                "validated": False,
            }
            accepted = False
            reason = str(exc)

        persisted = None
        if self.store is not None and task.get("tenant_id"):
            persisted = self.store.record_work_validation(
                tenant_id=str(task["tenant_id"]),
                work_type=validation["work_type"],
                template_id=validation["template_id"],
                template_version=validation["version"],
                validated=accepted,
                evidence_digest=evidence_digest or _canonical_digest(payload),
            )

        return {
            "accepted": accepted,
            "reason": reason,
            "validation": validation,
            "evidence_digest": evidence_digest,
            "persisted": persisted,
        }
