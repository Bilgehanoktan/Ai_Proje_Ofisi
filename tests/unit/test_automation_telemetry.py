"""Unit and security tests for Faz D4 (Activepieces) & D5 (Langfuse/OTel)."""

from __future__ import annotations

import unittest

from company_os.integrations.automation_telemetry import (
    ActivepiecesAdapter,
    AutomationTriggerRequest,
    TelemetrySanitizerAdapter,
    TraceSpanEvent,
)


class AutomationTelemetryTests(unittest.TestCase):
    def test_activepieces_community_mit_idempotent_and_enterprise_rejected(self) -> None:
        adapter = ActivepiecesAdapter()
        req = AutomationTriggerRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-ap-001",
            flow_name="sync-crm-to-erp",
            edition="community-mit",
            kernel_approved=True,
        )
        first = adapter.trigger_flow(req)
        self.assertFalse(first.deduplicated)
        second = adapter.trigger_flow(req)
        self.assertTrue(second.deduplicated)

        ent_req = AutomationTriggerRequest(
            tenant_id="tenant-1",
            idempotency_key="idem-ap-002",
            flow_name="sync-crm-to-erp",
            edition="enterprise",
            kernel_approved=True,
        )
        with self.assertRaisesRegex(ValueError, "ONLY_COMMUNITY_MIT_EDITION_ALLOWED"):
            adapter.trigger_flow(ent_req)

    def test_telemetry_redacts_raw_prompt_and_document_by_default(self) -> None:
        sanitizer = TelemetrySanitizerAdapter()
        span = TraceSpanEvent(
            trace_id="tr-100",
            span_name="exp01.run",
            latency_ms=120.5,
            status="OK",
            raw_prompt="SECRET PROMPT",
            document_body="CUSTOMER CONTRACT",
            allow_raw_payload=False,
        )
        exported = sanitizer.export_span(span)
        self.assertEqual(exported["raw_prompt"], TelemetrySanitizerAdapter.REDACTED)
        self.assertEqual(exported["document_body"], TelemetrySanitizerAdapter.REDACTED)


if __name__ == "__main__":
    unittest.main()
