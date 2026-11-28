"""Faz D1: Single CRM Adapter — Frappe CRM (MIT) with MOD-001 & MOD-014 gates.

Selection rationale:
- Frappe CRM (MIT) is commercially compatible with `.github/grant.yml` and shares
  the Frappe ecosystem with D2 (ERPNext).
- Twenty CRM (AGPL-3.0) is excluded by the release license policy.
- Company Kernel (MOD-001) remains the sole write-authorization authority;
  every external CRM mutation requires an idempotency key and MOD-014 receipt.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CrmLeadRequest:
    tenant_id: str
    idempotency_key: str
    customer_name: str
    deal_title: str
    kernel_approved: bool


@dataclass(frozen=True)
class CrmReceipt:
    crm_provider: str
    external_id: str
    idempotency_key: str
    effect_digest: str
    deduplicated: bool


@dataclass
class FrappeCrmAdapter:
    """Idempotent, Kernel-gated adapter for Frappe CRM (MIT)."""

    provider: str = "frappe-crm"
    license_spdx: str = "MIT"
    _ledger: dict[tuple[str, str], CrmReceipt] = field(default_factory=dict)

    def create_lead_and_deal(self, req: CrmLeadRequest) -> CrmReceipt:
        if not req.kernel_approved:
            raise PermissionError("MOD_001_KERNEL_APPROVAL_REQUIRED")
        if not req.tenant_id.strip() or not req.idempotency_key.strip():
            raise ValueError("TENANT_AND_IDEMPOTENCY_KEY_REQUIRED")

        key = (req.tenant_id.strip(), req.idempotency_key.strip())
        if key in self._ledger:
            prev = self._ledger[key]
            return CrmReceipt(
                crm_provider=prev.crm_provider,
                external_id=prev.external_id,
                idempotency_key=prev.idempotency_key,
                effect_digest=prev.effect_digest,
                deduplicated=True,
            )

        digest = hashlib.sha256(
            f"{req.tenant_id}|{req.idempotency_key}|{req.customer_name}|{req.deal_title}".encode("utf-8")
        ).hexdigest()
        receipt = CrmReceipt(
            crm_provider=self.provider,
            external_id=f"CRM-{digest[:12]}",
            idempotency_key=req.idempotency_key.strip(),
            effect_digest=digest,
            deduplicated=False,
        )
        self._ledger[key] = receipt
        return receipt
