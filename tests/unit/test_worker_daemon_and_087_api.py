"""Unit tests for AutonomousWorkerDaemon, Extensions087Store, and MOD-012..014 HTTP APIs."""

from __future__ import annotations

import json
import unittest
from io import BytesIO

from company_os.api.http.app import make_wsgi_app
from company_os.budget.ledger import ExternalEffectEntry
from company_os.catalog.extensions_store import Extensions087Store
from company_os.catalog.memory_promotion import (
    CatalogEntry,
    CatalogKind,
    MemoryRecord,
    PromotionState,
)
from company_os.runtime.worker_daemon import AutonomousWorkerDaemon, DaemonState
from company_os.workflows.queue_adapter import MultiWorkTypeQueueRunner
from company_os.workflows.templates import WorkType
from independent_verifier.research_readback import confirm_receipt, current_read


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeConn:
    def __init__(self, rows):
        self.cur = _FakeCursor(rows)
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class WorkerDaemonTests(unittest.TestCase):
    def test_daemon_processes_queue_and_emits_events(self):
        queue = [
            {"task_id": "t-1", "kind": "SOFTWARE"},
            {"task_id": "t-2", "kind": "RESEARCH"},
        ]
        events = []

        def claim():
            return queue.pop(0) if queue else None

        def execute(task):
            return {"patch": task["task_id"]}

        def verify(task, _exec):
            return {"accepted": task["task_id"] == "t-1"}

        daemon = AutonomousWorkerDaemon(
            claim_next=claim,
            execute_task=execute,
            verify_task=verify,
            on_event=lambda k, p: events.append((k, p)),
            poll_interval_seconds=0.0,
        )
        stats = daemon.run_forever(max_cycles=3)
        self.assertEqual(stats.state, DaemonState.STOPPED)
        self.assertEqual(stats.processed, 2)
        self.assertEqual(stats.accepted, 1)
        self.assertEqual(stats.rejected, 1)
        self.assertEqual(stats.errors, 0)
        self.assertEqual(
            [e[0] for e in events],
            [
                "WorkerTaskClaimed",
                "WorkerTaskAccepted",
                "WorkerTaskClaimed",
                "WorkerTaskRejected",
            ],
        )

    def test_daemon_halts_fail_closed_on_consecutive_errors(self):
        def claim():
            return {"task_id": "t-bad"}

        def execute(_task):
            raise RuntimeError("WORKER_CRASH")

        daemon = AutonomousWorkerDaemon(
            claim_next=claim,
            execute_task=execute,
            verify_task=lambda _t, _e: {"accepted": False},
            poll_interval_seconds=0.0,
            max_consecutive_errors=2,
        )
        stats = daemon.run_forever(max_cycles=10)
        self.assertEqual(stats.state, DaemonState.HALTED_ON_ERRORS)
        self.assertEqual(stats.errors, 2)
        self.assertEqual(stats.processed, 2)


class Extensions087StoreAndApiTests(unittest.TestCase):
    def test_store_rejects_same_actor_promotion_before_sql(self):
        called = False

        def connect():
            nonlocal called
            called = True
            return _FakeConn([])

        store = Extensions087Store(connect=connect)
        rec = MemoryRecord(
            tenant_id="11111111-1111-4111-8111-111111111111",
            record_id="m-1",
            summary="bad",
            evidence_digest="sha256:x",
            state=PromotionState.PROMOTED,
            verified_by="actor-1",
            promoted_by="actor-1",
        )
        with self.assertRaises(PermissionError):
            store.save_memory_promotion(rec)
        self.assertFalse(called)

    def test_store_parameterized_catalog_and_effect_roundtrip(self):
        tid = "11111111-1111-4111-8111-111111111111"
        conn = _FakeConn([(tid, "MODEL", "qwen2.5-coder", "3b", "sha256:abc", True)])
        store = Extensions087Store(connect=lambda: conn)
        entry = CatalogEntry(tid, CatalogKind.MODEL, "qwen2.5-coder", "3b", "sha256:abc")
        res = store.upsert_catalog_entry(entry)
        self.assertTrue(conn.committed)
        self.assertEqual(res["name"], "qwen2.5-coder")
        self.assertEqual(
            conn.cur.executed[0],
            ("SELECT set_config('app.tenant_id', %s, true)", (tid,)),
        )

        conn_eff = _FakeConn([(tid, "idem-1", "eff-1", "webhook", "COMMITTED")])
        store_eff = Extensions087Store(connect=lambda: conn_eff)
        eff = ExternalEffectEntry("eff-1", tid, "idem-1", "webhook", "COMMITTED")
        res_eff = store_eff.record_external_effect(eff)
        self.assertEqual(res_eff["status"], "COMMITTED")
        self.assertEqual(
            conn_eff.cur.executed[0],
            ("SELECT set_config('app.tenant_id', %s, true)", (tid,)),
        )

    def test_http_wsgi_endpoints_require_tenant_id_and_return_scoped_json(self):
        app = make_wsgi_app(
            catalog_provider=lambda tid: [{"tenant_id": tid, "name": "qwen2.5-coder"}],
            promotions_provider=lambda tid: [{"tenant_id": tid, "record_id": "m-1", "state": "PROMOTED"}],
            effects_provider=lambda tid: [{"tenant_id": tid, "effect_id": "e-1", "status": "COMMITTED"}],
        )

        def call(path, query=""):
            status_box = []

            def start_response(status, headers):
                status_box.append((status, dict(headers)))

            body = b"".join(
                app(
                    {
                        "REQUEST_METHOD": "GET",
                        "PATH_INFO": path,
                        "QUERY_STRING": query,
                        "wsgi.input": BytesIO(),
                    },
                    start_response,
                )
            )
            return status_box[0][0], body

        for endpoint in ("/api/catalog", "/api/memory-promotions", "/api/external-effects"):
            st, _ = call(endpoint, "")
            self.assertTrue(st.startswith("400"))

        st1, b1 = call("/api/catalog", "tenant_id=t-alpha")
        self.assertTrue(st1.startswith("200"))
        self.assertEqual(json.loads(b1)["catalog"][0]["tenant_id"], "t-alpha")

        st2, b2 = call("/api/memory-promotions", "tenant_id=t-alpha")
        self.assertTrue(st2.startswith("200"))
        self.assertEqual(json.loads(b2)["promotions"][0]["state"], "PROMOTED")

        st3, b3 = call("/api/external-effects", "tenant_id=t-alpha")
        self.assertTrue(st3.startswith("200"))
        self.assertEqual(json.loads(b3)["external_effects"][0]["effect_id"], "e-1")

    def test_seed_default_catalog_profiles_and_remote_preflight_allowlist(self):
        from scripts.operations.start_office_local import (
            build_remote_production_preflight,
            parse_allowed_https_domains,
        )

        tid = "11111111-1111-4111-8111-111111111111"
        saved = []

        class _CaptureStore(Extensions087Store):
            def upsert_catalog_entry(self, entry: CatalogEntry):
                item = {
                    "tenant_id": entry.tenant_id,
                    "kind": entry.kind.value,
                    "name": entry.name,
                    "version": entry.version,
                    "digest": entry.digest,
                    "active": entry.active,
                }
                saved.append(item)
                return item

        store = _CaptureStore(connect=lambda: _FakeConn([]))
        seeded = store.seed_default_catalog_profiles(tid)
        self.assertEqual(len(seeded), 11)
        kinds = {item["kind"] for item in seeded}
        self.assertEqual(kinds, {"ROLE", "SKILL", "MODEL"})
        names = {item["name"] for item in seeded}
        self.assertTrue(
            {"EXP-01", "EXP-02", "MGR-01", "QA-01", "qwen2.5-coder:3b", "qwen2.5-coder:7b", "llama3.2:3b"}.issubset(
                names
            )
        )

        domains = parse_allowed_https_domains("docs.example.org, mevzuat.gov.tr ")
        self.assertEqual(domains, frozenset({"docs.example.org", "mevzuat.gov.tr"}))
        with self.assertRaises(ValueError):
            parse_allowed_https_domains("https://bad.example.org")
        with self.assertRaises(ValueError):
            parse_allowed_https_domains("*.wildcard.example.org")

        preflight = build_remote_production_preflight("aipof-prod-01", domains)
        self.assertEqual(preflight["ssh_host_alias"], "aipof-prod-01")
        self.assertEqual(preflight["allowed_https_domains"], ["docs.example.org", "mevzuat.gov.tr"])
        self.assertEqual(len(preflight["steps"]), 4)
        with self.assertRaises(ValueError):
            build_remote_production_preflight("-bad-host", domains)


class MultiWorkTypeQueueRunnerTests(unittest.TestCase):
    def test_research_spreadsheet_obligation_queue_accept_and_reject(self):
        tid = "11111111-1111-4111-8111-111111111111"
        queue = [
            {"task_id": "res-1", "tenant_id": tid, "work_type": "RESEARCH", "valid": True},
            {"task_id": "xls-1", "tenant_id": tid, "work_type": "SPREADSHEET", "valid": True},
            {"task_id": "obl-1", "tenant_id": tid, "work_type": "OBLIGATION", "valid": True},
            {"task_id": "res-bad", "tenant_id": tid, "work_type": "RESEARCH", "valid": False},
        ]
        runner = MultiWorkTypeQueueRunner(
            executors={
                WorkType.RESEARCH: lambda t: (
                    {"citations": [{"source_uri": "https://example.org/doc1"}]}
                    if t["valid"]
                    else {"citations": []}
                ),
                WorkType.SPREADSHEET: lambda _t: {
                    "post_commit_verified": True,
                    "workbook_digest": "sha256:sheet1",
                },
                WorkType.OBLIGATION: lambda _t: {
                    "uncertainty_ms": 15,
                    "max_uncertainty_ms": 100,
                },
            }
        )
        emitted = []
        daemon = AutonomousWorkerDaemon(
            claim_next=lambda: queue.pop(0) if queue else None,
            execute_task=runner.execute_task,
            verify_task=runner.verify_task,
            on_event=lambda kind, payload: emitted.append((kind, payload)),
            poll_interval_seconds=0.0,
        )
        stats = daemon.run_forever(max_cycles=5)
        self.assertEqual(stats.state, DaemonState.STOPPED)
        self.assertEqual(stats.processed, 4)
        self.assertEqual(stats.accepted, 3)
        self.assertEqual(stats.rejected, 1)
        self.assertEqual(stats.errors, 0)
        self.assertEqual(stats.history[3].detail["verify"]["reason"], "RESEARCH_CITATIONS_REQUIRED")
        self.assertEqual(sum(1 for k, _ in emitted if k == "WorkerTaskAccepted"), 3)
        self.assertEqual(sum(1 for k, _ in emitted if k == "WorkerTaskRejected"), 1)

    def test_research_kernel_receipt_readback_current_read_and_confirm_receipt(self):
        from uuid import uuid4

        tid = str(uuid4())
        pid = str(uuid4())
        task_id = str(uuid4())
        att_id = str(uuid4())
        rec_id = str(uuid4())

        conn_ok = _FakeConn([(att_id, rec_id, "a" * 64)])
        res = current_read(
            lambda: conn_ok,
            {"tenant_id": tid, "project_id": pid, "task_id": task_id, "read_path": "task_title.py"},
        )
        self.assertEqual(
            res,
            {
                "attempt_id": att_id,
                "receipt_id": rec_id,
                "relative_path": "task_title.py",
                "sha256": "a" * 64,
            },
        )
        self.assertEqual(conn_ok.cur.executed[0][0], "SET TRANSACTION READ ONLY")

        # Duplicate or missing rows in current_read must fail-closed
        for bad_rows in ([], [(att_id, rec_id, "a" * 64), (att_id, rec_id, "b" * 64)]):
            with self.assertRaisesRegex(ValueError, "UNIQUE_KERNEL_RESEARCH_READ_REQUIRED"):
                current_read(
                    lambda rows=bad_rows: _FakeConn(rows),
                    {"tenant_id": tid, "project_id": pid, "task_id": task_id, "read_path": "task_title.py"},
                )

        # confirm_receipt checks valid scope, require_current parameter binding, and invalid inputs
        conn_confirm = _FakeConn([(True,)])
        scope = {
            "tenant_id": tid,
            "project_id": pid,
            "task_id": task_id,
            "attempt_id": att_id,
            "read_path": "task_title.py",
        }
        self.assertTrue(confirm_receipt(lambda: conn_confirm, scope, rec_id, require_current=True))
        self.assertEqual(conn_confirm.cur.executed[0][0], "SET TRANSACTION READ ONLY")
        self.assertIn("active_attempt_id", conn_confirm.cur.executed[1][0])
        self.assertEqual(len(conn_confirm.cur.executed[1][1]), 10)

        self.assertFalse(confirm_receipt(lambda: _FakeConn([(True,)]), {**scope, "read_path": ""}, rec_id))
        self.assertFalse(confirm_receipt(lambda: _FakeConn([(True,)]), scope, "not-a-uuid"))

    def test_multi_worker_and_persistent_sse_soak(self):
        from scripts.verification.probe_office_durability import (
            run_multi_worker_and_persistent_sse_soak,
        )

        result = run_multi_worker_and_persistent_sse_soak()
        self.assertTrue(result["passed"])
        self.assertEqual(result["workers"], 4)
        self.assertEqual(result["total_tasks"], 480)
        self.assertEqual(result["unique_claimed"], 480)
        self.assertEqual(result["accepted"], 480)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(result["journal_restart_recovery_passed"])


if __name__ == "__main__":
    unittest.main()
