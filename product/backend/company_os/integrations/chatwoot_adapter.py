"""Faz D3: Chatwoot Support Adapter with MOD-001 & MOD-014 gates.

Maps external conversation/message IDs and enforces MOD-001 Kernel approval
before any outbound customer reply is dispatched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SupportReplyRequest:
    tenant_id: str
    idempotency_key: str
    conversation_id: str
    reply_body: str
    outbound_reply: bool
    kernel_approved: bool


@dataclass(frozen=True)
class SupportReceipt:
    support_provider: str
    conversation_id: str
    external_message_id: str
    idempotency_key: str
    effect_digest: str
    deduplicated: bool


@dataclass
class ChatwootSupportAdapter:
    """Idempotent, Kernel-gated adapter for Chatwoot (MIT)."""

    provider: str = "chatwoot"
    license_spdx: str = "MIT"
    _ledger: dict[tuple[str, str], SupportReceipt] = field(default_factory=dict)

    def post_message(self, req: SupportReplyRequest) -> SupportReceipt:
        if req.outbound_reply and not req.kernel_approved:
            raise PermissionError("MOD_001_OUTBOUND_REPLY_APPROVAL_REQUIRED")
        if not req.tenant_id.strip() or not req.idempotency_key.strip():
            raise ValueError("TENANT_AND_IDEMPOTENCY_KEY_REQUIRED")
        if not req.conversation_id.strip() or not req.reply_body.strip():
            raise ValueError("CONVERSATION_AND_BODY_REQUIRED")

        key = (req.tenant_id.strip(), req.idempotency_key.strip())
        if key in self._ledger:
            prev = self._ledger[key]
            return SupportReceipt(
                support_provider=prev.support_provider,
                conversation_id=prev.conversation_id,
                external_message_id=prev.external_message_id,
                idempotency_key=prev.idempotency_key,
                effect_digest=prev.effect_digest,
                deduplicated=True,
            )

        digest = hashlib.sha256(
            f"{req.tenant_id}|{req.idempotency_key}|{req.conversation_id}|{req.reply_body}".encode("utf-8")
        ).hexdigest()
        receipt = SupportReceipt(
            support_provider=self.provider,
            conversation_id=req.conversation_id.strip(),
            external_message_id=f"CW-MSG-{digest[:10]}",
            idempotency_key=req.idempotency_key.strip(),
            effect_digest=digest,
            deduplicated=False,
        )
        self._ledger[key] = receipt
        return receipt
