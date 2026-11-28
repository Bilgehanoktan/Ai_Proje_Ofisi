"""Unit and security tests for Faz D2: ERPNext & TR e-Fatura adapter."""

from __future__ import annotations

import unittest

from company_os.integrations.erpnext_adapter import ErpNextInvoiceAdapter, InvoiceDraftRequest


class ErpNextAdapterTests(unittest.TestCase):
    def test_approved_quote_creates_idempotent_tr_efatura_draft(self) -> None:
        adapter = ErpNextInvoiceAdapter()
        req = InvoiceDraftRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-inv-001",
            approved_quote_id="QT-2026-001",
            customer_tax_id="1234567890",
            amount_minor=150000,
            currency="TRY",
            kernel_approved=True,
        )
        first = adapter.create_invoice_draft(req)
        self.assertFalse(first.deduplicated)
        self.assertEqual(first.e_fatura_profile, "TR-UBL-TR1.2")

        second = adapter.create_invoice_draft(req)
        self.assertTrue(second.deduplicated)
        self.assertEqual(second.draft_invoice_id, first.draft_invoice_id)

    def test_invalid_tr_tax_id_and_unapproved_kernel_rejected(self) -> None:
        adapter = ErpNextInvoiceAdapter()
        bad_tax = InvoiceDraftRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-inv-002",
            approved_quote_id="QT-2026-002",
            customer_tax_id="123",
            amount_minor=1000,
            currency="TRY",
            kernel_approved=True,
        )
        with self.assertRaisesRegex(ValueError, "INVALID_TR_TAX_ID"):
            adapter.create_invoice_draft(bad_tax)

        unapproved = InvoiceDraftRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-inv-003",
            approved_quote_id="QT-2026-003",
            customer_tax_id="1234567890",
            amount_minor=1000,
            currency="TRY",
            kernel_approved=False,
        )
        with self.assertRaisesRegex(PermissionError, "MOD_001_KERNEL_APPROVAL_REQUIRED"):
            adapter.create_invoice_draft(unapproved)


if __name__ == "__main__":
    unittest.main()
