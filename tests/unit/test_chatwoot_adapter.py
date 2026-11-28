"""Unit and security tests for Faz D3: Chatwoot support adapter."""

from __future__ import annotations

import unittest

from company_os.integrations.chatwoot_adapter import ChatwootSupportAdapter, SupportReplyRequest


class ChatwootAdapterTests(unittest.TestCase):
    def test_approved_outbound_reply_is_idempotent(self) -> None:
        adapter = ChatwootSupportAdapter()
        req = SupportReplyRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-cw-001",
            conversation_id="CONV-42",
            reply_body="Talebiniz isleme alindi.",
            outbound_reply=True,
            kernel_approved=True,
        )
        first = adapter.post_message(req)
        self.assertFalse(first.deduplicated)
        self.assertTrue(first.external_message_id.startswith("CW-MSG-"))

        second = adapter.post_message(req)
        self.assertTrue(second.deduplicated)
        self.assertEqual(second.external_message_id, first.external_message_id)

    def test_unapproved_outbound_reply_is_denied(self) -> None:
        adapter = ChatwootSupportAdapter()
        req = SupportReplyRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-cw-002",
            conversation_id="CONV-42",
            reply_body="Onaysiz dis cevap",
            outbound_reply=True,
            kernel_approved=False,
        )
        with self.assertRaisesRegex(PermissionError, "MOD_001_OUTBOUND_REPLY_APPROVAL_REQUIRED"):
            adapter.post_message(req)


if __name__ == "__main__":
    unittest.main()
