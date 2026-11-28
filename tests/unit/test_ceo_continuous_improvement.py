"""Unit and HTTP boundary tests for MGR-01 (CEO) Continuous Company Improvement (Kaizen)."""

from __future__ import annotations

import io
import json
import unittest
from typing import Any

from company_os.api.http.app import make_wsgi_app
from company_os.runtime.ceo_improvement import (
    KAIZEN_PREFIX,
    CeoContinuousImprovementEngine,
    CeoImprovementValidationError,
)
from company_os.runtime.live_task_runner import LiveOfficeTaskRunner


def _wsgi_request(
    app: Any,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    origin: str = "http://127.0.0.1:8765",
) -> tuple[str, dict[str, Any]]:
    raw = json.dumps(body).encode("utf-8") if body is not None else b""
    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "HTTP_HOST": "127.0.0.1:8765",
        "HTTP_ORIGIN": origin,
        "wsgi.input": io.BytesIO(raw),
    }
    if body is not None:
        environ["CONTENT_TYPE"] = "application/json"
        environ["CONTENT_LENGTH"] = str(len(raw))
    captured: dict[str, str] = {}

    def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
        captured["status"] = status

    chunks = app(environ, start_response)
    payload = json.loads(b"".join(chunks).decode("utf-8"))
    return captured["status"], payload


class CeoContinuousImprovementTests(unittest.TestCase):
    def test_detects_budget_unknown_and_failed_runs_without_kaizen_recursion(self) -> None:
        dispatched_specs: list[dict[str, Any]] = []
        engine = CeoContinuousImprovementEngine(
            task_submitter=lambda spec, _bearer: (
                dispatched_specs.append(spec) or {"task_id": f"task-{len(dispatched_specs)}"}
            ),
        )
        runs = [
            {
                "task_id": "t-fail-1",
                "title": "Tablo Denetimi",
                "work_type": "SPREADSHEET",
                "role_id": "EXP-04",
                "state": "REJECTED",
                "verification": {"reason": "SPREADSHEET_CELL_COUNT_ZERO"},
            },
            {
                "task_id": "t-kaizen-fail",
                "title": f"{KAIZEN_PREFIX} Önceki Kaizen Görevi",
                "work_type": "RESEARCH",
                "role_id": "MGR-01",
                "state": "REJECTED",
                "verification": {"reason": "SHOULD_NOT_RECURSE"},
            },
        ]
        promotions = [{"record_id": "mem-1", "state": "VERIFIED"}]
        budget = {"budget_limit_minor": 1000, "spent_minor": 200, "blocked_by_unknown": True}
        effects = [{"effect_id": "eff-1", "status": "UNKNOWN"}]

        snap = engine.evaluate_company_state(
            runs=runs,
            memory_promotions=promotions,
            budget=budget,
            external_effects=effects,
        )
        self.assertLess(snap["metrics"]["health_score"], 70)
        categories = {p["category"] for p in snap["proposals"]}
        self.assertIn("BUDGET_RECONCILIATION", categories)
        self.assertIn("QUALITY_REMEDIATION", categories)
        self.assertIn("MEMORY_GOVERNANCE", categories)

        # Ensure the failed [CEO-KAIZEN] task did NOT generate a recursive remediation proposal
        remediations = [p for p in snap["proposals"] if p["category"] == "QUALITY_REMEDIATION"]
        self.assertEqual(len(remediations), 1)
        self.assertIn("EXP-04", remediations[0]["title"])
        self.assertNotIn("SHOULD_NOT_RECURSE", remediations[0]["rationale"])

        # Separation of duties: memory promotion stays untouched until human action
        self.assertEqual(promotions[0]["state"], "VERIFIED")
        self.assertEqual(len(dispatched_specs), 0)

    def test_proactive_kaizen_and_bounded_auto_dispatch_respects_idle_and_cap(self) -> None:
        submitted: list[dict[str, Any]] = []
        engine = CeoContinuousImprovementEngine(
            task_submitter=lambda spec, _bearer: (
                submitted.append(spec) or {"task_id": f"auto-{len(submitted)}"}
            ),
            max_auto_dispatches=2,
        )

        # 1. Idle state without failures still yields 1 proactive Kaizen proposal
        snap0 = engine.evaluate_company_state(runs=[])
        self.assertEqual(snap0["open_proposals_count"], 1)
        self.assertEqual(snap0["proposals"][0]["category"], "PROACTIVE_KAIZEN")
        self.assertEqual(len(submitted), 0)

        # 2. Enabling auto-kaizen while a task is RUNNING must NOT auto-dispatch
        engine.set_auto_kaizen(True)
        busy_runs = [{"task_id": "r1", "title": "Aktif İş", "state": "RUNNING", "role_id": "EXP-01"}]
        engine.evaluate_company_state(runs=busy_runs)
        self.assertEqual(len(submitted), 0)

        # 3. Once queue is idle, auto-kaizen dispatches up to max_auto_dispatches=2 and then stops
        engine.evaluate_company_state(runs=[])
        self.assertEqual(len(submitted), 1)
        engine.evaluate_company_state(runs=[])
        self.assertEqual(len(submitted), 2)
        snap_capped = engine.evaluate_company_state(runs=[])
        self.assertEqual(len(submitted), 2)
        self.assertEqual(snap_capped["auto_dispatched_count"], 2)

    def test_http_endpoints_origin_guard_and_runner_settlement_hook(self) -> None:
        settled_ids: list[str] = []
        runner = LiveOfficeTaskRunner(
            ollama_client=None,
            on_task_settled=lambda rec: settled_ids.append(rec.task_id),
        )
        engine = CeoContinuousImprovementEngine(
            task_submitter=lambda spec, bearer: runner.submit_task(spec, bearer_token=bearer),
        )
        app = make_wsgi_app(
            ceo_improvement_provider=lambda: engine.evaluate_company_state(runs=runner.list_runs()),
            ceo_improvement_handler=lambda payload, bearer: engine.handle_action(
                payload,
                bearer_token=bearer,
                state_provider=lambda: {"runs": runner.list_runs()},
            ),
        )

        status_get, data_get = _wsgi_request(app, "GET", "/api/ceo-improvement")
        self.assertEqual(status_get, "200 OK")
        self.assertGreaterEqual(len(data_get["proposals"]), 1)
        prop_id = data_get["proposals"][0]["proposal_id"]

        # Cross-origin POST rejected
        status_bad_origin, err_origin = _wsgi_request(
            app,
            "POST",
            "/api/ceo-improvement",
            body={"action": "dispatch", "proposal_id": prop_id},
            origin="https://attacker.example",
        )
        self.assertEqual(status_bad_origin, "403 Forbidden")
        self.assertEqual(err_origin["error"], "ORIGIN_REJECTED")

        # Valid loopback dispatch queues real task in LiveOfficeTaskRunner
        status_disp, res_disp = _wsgi_request(
            app,
            "POST",
            "/api/ceo-improvement",
            body={"action": "dispatch", "proposal_id": prop_id},
        )
        self.assertEqual(status_disp, "200 OK")
        self.assertEqual(res_disp["result"]["proposal"]["state"], "DISPATCHED")
        queued_runs = runner.list_runs()
        self.assertEqual(len(queued_runs), 1)
        self.assertIn(KAIZEN_PREFIX, queued_runs[0]["title"])

        # Unknown proposal returns 404, invalid action returns 400
        status_404, _ = _wsgi_request(
            app,
            "POST",
            "/api/ceo-improvement",
            body={"action": "dismiss", "proposal_id": "missing-id"},
        )
        self.assertEqual(status_404, "404 Not Found")
        status_400, _ = _wsgi_request(
            app,
            "POST",
            "/api/ceo-improvement",
            body={"action": "invalid_cmd"},
        )
        self.assertEqual(status_400, "400 Bad Request")
        with self.assertRaises(CeoImprovementValidationError):
            engine.dismiss_proposal("")

    def test_memory_backlog_updates_in_place_and_runner_preserves_parent_and_skips_kaizen_promo(self) -> None:
        engine = CeoContinuousImprovementEngine()
        snap1 = engine.evaluate_company_state(
            memory_promotions=[{"record_id": "m1", "state": "VERIFIED"}],
        )
        mem_props_1 = [p for p in snap1["proposals"] if p["category"] == "MEMORY_GOVERNANCE"]
        self.assertEqual(len(mem_props_1), 1)
        first_id = mem_props_1[0]["proposal_id"]

        snap4 = engine.evaluate_company_state(
            memory_promotions=[{"record_id": f"m{i}", "state": "VERIFIED"} for i in range(4)],
        )
        mem_props_4 = [p for p in snap4["proposals"] if p["category"] == "MEMORY_GOVERNANCE"]
        self.assertEqual(len(mem_props_4), 1)
        self.assertEqual(mem_props_4[0]["proposal_id"], first_id)
        self.assertIn("Bekleyen 4", mem_props_4[0]["title"])

        # Runner parent inclusion in list_runs(limit=1) and [CEO-KAIZEN] skipping on_task_accepted
        class _StubOllama:
            default_model = "stub-model"

            @staticmethod
            def generate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {
                    "model": "stub-model",
                    "response": "1. Adım kontrolü\n2. Doğrulama adımı\n3. Sonuç özeti tamamlandı.",
                    "eval_count": 24,
                    "total_duration_ms": 5,
                }

        accepted_promos: list[str] = []
        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama(),  # type: ignore[arg-type]
            on_task_accepted=lambda rec: accepted_promos.append(rec.title),
            verifier=lambda _spec, _exec: {"accepted": True, "verified_by": "TEST", "reason": "OK"},
        )
        created_kaizen = runner.submit_task(
            {
                "title": f"{KAIZEN_PREFIX} Test Kaizen",
                "goal": "Test kaizen hedefi uzun aciklama",
                "work_type": "RESEARCH",
                "role_id": "MGR-01",
            }
        )
        runner.run_once()
        # Kaizen task itself must not trigger MOD-012 product memory promotion candidate
        self.assertEqual(accepted_promos, [])
        # Even with limit=1, the delegated child pulls its parent MGR-01 task into list_runs
        runs_limited = runner.list_runs(limit=1)
        returned_ids = {r["task_id"] for r in runs_limited}
        self.assertIn(created_kaizen["task_id"], returned_ids)


if __name__ == "__main__":
    unittest.main()
