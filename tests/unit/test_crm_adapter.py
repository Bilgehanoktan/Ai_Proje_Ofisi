"""Unit and security tests for Faz D1: Frappe CRM adapter."""

from __future__ import annotations

import unittest

from company_os.integrations.crm_adapter import CrmLeadRequest, FrappeCrmAdapter


class FrappeCrmAdapterTests(unittest.TestCase):
    def test_kernel_approved_lead_is_idempotent(self) -> None:
        adapter = FrappeCrmAdapter()
        req = CrmLeadRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-lead-001",
            customer_name="Acme A.S.",
            deal_title="Yillik Bakim Teklifi",
            kernel_approved=True,
        )
        first = adapter.create_lead_and_deal(req)
        self.assertFalse(first.deduplicated)
        self.assertEqual(first.crm_provider, "frappe-crm")

        second = adapter.create_lead_and_deal(req)
        self.assertTrue(second.deduplicated)
        self.assertEqual(second.external_id, first.external_id)
        self.assertEqual(second.effect_digest, first.effect_digest)

    def test_unapproved_kernel_request_is_denied(self) -> None:
        adapter = FrappeCrmAdapter()
        req = CrmLeadRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-lead-002",
            customer_name="Acme A.S.",
            deal_title="Yetkisiz Teklif",
            kernel_approved=False,
        )
        with self.assertRaisesRegex(PermissionError, "MOD_001_KERNEL_APPROVAL_REQUIRED"):
            adapter.create_lead_and_deal(req)


if __name__ == "__main__":
    unittest.main()
