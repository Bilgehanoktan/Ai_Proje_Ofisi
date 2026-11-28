"""Faz D2: ERPNext Invoice Draft & TR e-Fatura Validation Adapter.

Requires MOD-001 Kernel approval, valid Turkish VKN (10 digits) or TCKN
(11 digits), positive minor-unit amount, and MOD-014 idempotency key.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InvoiceDraftRequest:
    tenant_id: str
    idempotency_key: str
    approved_quote_id: str
    customer_tax_id: str
    amount_minor: int
    currency: str
    kernel_approved: bool


@dataclass(frozen=True)
class InvoiceDraftReceipt:
    erp_provider: str
    draft_invoice_id: str
    e_fatura_profile: str
    idempotency_key: str
    effect_digest: str
    deduplicated: bool


def validate_tr_tax_id(tax_id: str) -> str:
    cleaned = tax_id.strip()
    if not cleaned.isdigit() or len(cleaned) not in (10, 11):
        raise ValueError("INVALID_TR_TAX_ID")
    return cleaned


@dataclass
class ErpNextInvoiceAdapter:
    """Idempotent, Kernel-gated adapter for ERPNext (GPLv3-external/MIT API) & TR e-Fatura."""

    provider: str = "erpnext"
    _ledger: dict[tuple[str, str], InvoiceDraftReceipt] = field(default_factory=dict)

    def create_invoice_draft(self, req: InvoiceDraftRequest) -> InvoiceDraftReceipt:
        if not req.kernel_approved:
            raise PermissionError("MOD_001_KERNEL_APPROVAL_REQUIRED")
        if not req.tenant_id.strip() or not req.idempotency_key.strip():
            raise ValueError("TENANT_AND_IDEMPOTENCY_KEY_REQUIRED")
        if not req.approved_quote_id.strip():
            raise ValueError("APPROVED_QUOTE_ID_REQUIRED")
        if req.amount_minor <= 0:
            raise ValueError("POSITIVE_AMOUNT_REQUIRED")
        tax_id = validate_tr_tax_id(req.customer_tax_id)

        key = (req.tenant_id.strip(), req.idempotency_key.strip())
        if key in self._ledger:
            prev = self._ledger[key]
            return InvoiceDraftReceipt(
                erp_provider=prev.erp_provider,
                draft_invoice_id=prev.draft_invoice_id,
                e_fatura_profile=prev.e_fatura_profile,
                idempotency_key=prev.idempotency_key,
                effect_digest=prev.effect_digest,
                deduplicated=True,
            )

        digest = hashlib.sha256(
            f"{req.tenant_id}|{req.idempotency_key}|{req.approved_quote_id}|{tax_id}|{req.amount_minor}|{req.currency}".encode(
                "utf-8"
            )
        ).hexdigest()
        receipt = InvoiceDraftReceipt(
            erp_provider=self.provider,
            draft_invoice_id=f"INV-DRAFT-{digest[:10]}",
            e_fatura_profile="TR-UBL-TR1.2",
            idempotency_key=req.idempotency_key.strip(),
            effect_digest=digest,
            deduplicated=False,
        )
        self._ledger[key] = receipt
        return receipt
