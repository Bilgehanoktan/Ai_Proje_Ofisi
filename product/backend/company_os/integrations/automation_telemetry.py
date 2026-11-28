"""Faz D4 & D5: Activepieces (MIT Community) & Langfuse/OpenTelemetry Adapters.

- D4 enforces Community MIT edition (rejects Enterprise lock-in) + MOD-001/MOD-014.
- D5 enforces privacy-by-default: raw prompts and customer documents are redacted
  unless explicit data-governance approval (`allow_raw_payload=True`) is provided.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutomationTriggerRequest:
    tenant_id: str
    idempotency_key: str
    flow_name: str
    edition: str
    kernel_approved: bool


@dataclass(frozen=True)
class AutomationReceipt:
    provider: str
    flow_name: str
    idempotency_key: str
    effect_digest: str
    deduplicated: bool


@dataclass
class ActivepiecesAdapter:
    """Kernel-gated adapter for Activepieces Community (MIT)."""

    provider: str = "activepieces-community"
    _ledger: dict[tuple[str, str], AutomationReceipt] = field(default_factory=dict)

    def trigger_flow(self, req: AutomationTriggerRequest) -> AutomationReceipt:
        if req.edition.strip().lower() != "community-mit":
            raise ValueError("ONLY_COMMUNITY_MIT_EDITION_ALLOWED")
        if not req.kernel_approved:
            raise PermissionError("MOD_001_KERNEL_APPROVAL_REQUIRED")
        if not req.tenant_id.strip() or not req.idempotency_key.strip():
            raise ValueError("TENANT_AND_IDEMPOTENCY_KEY_REQUIRED")

        key = (req.tenant_id.strip(), req.idempotency_key.strip())
        if key in self._ledger:
            prev = self._ledger[key]
            return AutomationReceipt(
                provider=prev.provider,
                flow_name=prev.flow_name,
                idempotency_key=prev.idempotency_key,
                effect_digest=prev.effect_digest,
                deduplicated=True,
            )

        digest = hashlib.sha256(
            f"{req.tenant_id}|{req.idempotency_key}|{req.flow_name}".encode("utf-8")
        ).hexdigest()
        receipt = AutomationReceipt(
            provider=self.provider,
            flow_name=req.flow_name.strip(),
            idempotency_key=req.idempotency_key.strip(),
            effect_digest=digest,
            deduplicated=False,
        )
        self._ledger[key] = receipt
        return receipt


@dataclass(frozen=True)
class TraceSpanEvent:
    trace_id: str
    span_name: str
    latency_ms: float
    status: str
    raw_prompt: str | None = None
    document_body: str | None = None
    allow_raw_payload: bool = False


class TelemetrySanitizerAdapter:
    """Sanitizes multi-agent traces before exporting to Langfuse / OpenTelemetry."""

    REDACTED = "[REDACTED_BY_PRIVACY_POLICY]"

    def export_span(self, event: TraceSpanEvent) -> dict[str, str | float]:
        prompt_val = event.raw_prompt if (event.allow_raw_payload and event.raw_prompt) else self.REDACTED
        doc_val = event.document_body if (event.allow_raw_payload and event.document_body) else self.REDACTED
        return {
            "trace_id": event.trace_id,
            "span_name": event.span_name,
            "latency_ms": event.latency_ms,
            "status": event.status,
            "raw_prompt": prompt_val,
            "document_body": doc_val,
        }
