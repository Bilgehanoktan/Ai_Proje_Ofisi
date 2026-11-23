"""Unit tests for MOD-011 SSE, MOD-012 catalog/memory, MOD-013 work types, and MOD-014 budget/ledger."""

from __future__ import annotations

import sys
import unittest

from company_os.api.http.app import make_wsgi_app
from company_os.budget.ledger import BudgetAndEffectLedger, ReservationState
from company_os.catalog.memory_promotion import (
    CatalogEntry,
    CatalogKind,
    ProductMemoryPromotionPipeline,
    PromotionState,
    TenantCatalogRegistry,
)
from company_os.projections.sse_stream import ProjectionEvent, stream_tenant_events
from company_os.runtime.r65_native_launcher import NativeLauncherError, R65NativeLauncher
from company_os.workflows.templates import WorkType, validate_work_output


class Mod012CatalogAndMemoryTests(unittest.TestCase):
    def test_tenant_catalog_pinning_and_conflict(self) -> None:
        reg = TenantCatalogRegistry()
        e1 = CatalogEntry("t1", CatalogKind.MODEL, "qwen2.5-coder", "3b", "sha256:aaa")
        reg.register(e1)
        self.assertEqual(reg.resolve("t1", CatalogKind.MODEL, "qwen2.5-coder", "3b"), e1)
        with self.assertRaises(KeyError):
            reg.resolve("t2", CatalogKind.MODEL, "qwen2.5-coder", "3b")
        with self.assertRaises(ValueError):
            reg.register(CatalogEntry("t1", CatalogKind.MODEL, "qwen2.5-coder", "3b", "sha256:bbb"))

    def test_memory_promotion_enforces_verification_separation_and_tenant_scope(self) -> None:
        pipe = ProductMemoryPromotionPipeline()
        rec = pipe.submit_candidate("t1", "mem-1", "Normalized title rule", "sha256:ev1")
        self.assertEqual(rec.state, PromotionState.CANDIDATE)
        with self.assertRaises(ValueError):
            pipe.promote("t1", "mem-1", "approver-1")
        with self.assertRaises(PermissionError):
            pipe.verify("t2", "mem-1", "verifier-1")
        pipe.verify("t1", "mem-1", "verifier-1")
        with self.assertRaises(PermissionError):
            pipe.promote("t1", "mem-1", "verifier-1")
        promoted = pipe.promote("t1", "mem-1", "approver-1")
        self.assertEqual(promoted.state, PromotionState.PROMOTED)
        self.assertEqual(len(pipe.list_promoted("t1")), 1)
        self.assertEqual(len(pipe.list_promoted("t2")), 0)


class Mod013WorkTypesTests(unittest.TestCase):
    def test_research_spreadsheet_and_obligation_validation(self) -> None:
        r = validate_work_output(WorkType.RESEARCH, {"citations": [{"source_uri": "https://example.org/doc"}]})
        self.assertTrue(r["validated"])
        with self.assertRaises(ValueError):
            validate_work_output(WorkType.RESEARCH, {"citations": []})

        s = validate_work_output(
            WorkType.SPREADSHEET, {"post_commit_verified": True, "workbook_digest": "sha256:wb1"}
        )
        self.assertTrue(s["validated"])
        with self.assertRaises(ValueError):
            validate_work_output(WorkType.SPREADSHEET, {"post_commit_verified": False, "workbook_digest": "sha256:wb1"})

        o = validate_work_output(WorkType.OBLIGATION, {"uncertainty_ms": 50, "max_uncertainty_ms": 100})
        self.assertTrue(o["validated"])
        with self.assertRaises(ValueError):
            validate_work_output(WorkType.OBLIGATION, {"uncertainty_ms": 250, "max_uncertainty_ms": 100})


class Mod014BudgetAndLedgerTests(unittest.TestCase):
    def test_nonzero_budget_unknown_cost_blocking_and_reconciliation(self) -> None:
        ledger = BudgetAndEffectLedger(tenant_id="t1", budget_limit_minor=1000)
        with self.assertRaises(ValueError):
            ledger.reserve("r0", 0)
        r1 = ledger.reserve("r1", 400)
        self.assertEqual(ledger.available_minor, 600)
        ledger.mark_unknown("r1")
        self.assertEqual(r1.state, ReservationState.UNKNOWN)
        with self.assertRaises(RuntimeError):
            ledger.reserve("r2", 100)
        ledger.settle("r1", 350)
        self.assertEqual(ledger.spent_minor, 350)
        self.assertEqual(ledger.available_minor, 650)
        r2 = ledger.reserve("r2", 200)
        ledger.release(r2.reservation_id)
        self.assertEqual(ledger.available_minor, 650)

    def test_external_effect_idempotency(self) -> None:
        ledger = BudgetAndEffectLedger(tenant_id="t1", budget_limit_minor=1000)
        e1 = ledger.record_external_effect("eff-1", "idem-1", "webhook", "COMMITTED")
        e2 = ledger.record_external_effect("eff-1", "idem-1", "webhook", "COMMITTED")
        self.assertEqual(e1, e2)
        with self.assertRaises(ValueError):
            ledger.record_external_effect("eff-2", "idem-1", "webhook", "COMMITTED")


class Mod011SseStreamTests(unittest.TestCase):
    def test_sse_stream_filters_by_tenant_and_cursor(self) -> None:
        events = [
            ProjectionEvent(1, "t1", "ObjectiveCreated", {"id": "o1"}),
            ProjectionEvent(2, "t2", "ObjectiveCreated", {"id": "o2"}),
            ProjectionEvent(3, "t1", "TaskCreated", {"id": "k1"}),
        ]
        frames = stream_tenant_events(events, tenant_id="t1", last_event_id=1)
        self.assertEqual(len(frames), 1)
        self.assertIn("id: 3\n", frames[0])
        self.assertIn("event: TaskCreated\n", frames[0])
        self.assertNotIn("o2", frames[0])

    def test_wsgi_sse_and_work_types_endpoints(self) -> None:
        events = [
            ProjectionEvent(1, "t1", "ObjectiveCreated", {"id": "o1"}),
            ProjectionEvent(2, "t2", "ObjectiveCreated", {"id": "o2"}),
            ProjectionEvent(3, "t1", "TaskCreated", {"id": "k1"}),
        ]
        app = make_wsgi_app(events_provider=lambda _tid: events)

        def call(path: str, qs: str = "", extra: dict | None = None):
            captured = {}
            def start_response(status, headers):
                captured["status"] = status
                captured["headers"] = dict(headers)
            env = {"PATH_INFO": path, "REQUEST_METHOD": "GET", "QUERY_STRING": qs}
            if extra:
                env.update(extra)
            body = b"".join(app(env, start_response))
            return captured["status"], captured["headers"], body.decode("utf-8")

        st, _, _ = call("/api/events")
        self.assertTrue(st.startswith("400 "))

        st, hdrs, body = call("/api/events", "tenant_id=t1", {"HTTP_LAST_EVENT_ID": "1"})
        self.assertEqual(st, "200 OK")
        self.assertIn("text/event-stream", hdrs["Content-Type"])
        self.assertIn("id: 3\n", body)
        self.assertNotIn("o2", body)

        st, hdrs, body = call("/api/work-types")
        self.assertEqual(st, "200 OK")
        self.assertIn("WFT-RESEARCH-01", body)
        self.assertIn("WFT-SPREADSHEET-01", body)
        self.assertIn("WFT-OBLIGATION-01", body)

        st, hdrs, body = call("/live-events")
        self.assertEqual(st, "200 OK")
        self.assertIn("text/html", hdrs["Content-Type"])
        self.assertIn("EventSource", body)


class Mod004NativeLauncherBridgeTests(unittest.TestCase):
    def test_fail_closed_on_non_linux_or_missing_library(self) -> None:
        with self.assertRaises(NativeLauncherError) as ctx:
            R65NativeLauncher("/nonexistent/r65_spawn_linux.so")
        if sys.platform != "linux":
            self.assertIn("R65_LINUX_ONLY", str(ctx.exception))
        else:
            self.assertIn("R65_LIBRARY_NOT_FOUND", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
