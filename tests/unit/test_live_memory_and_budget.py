"""Unit tests for LiveMemoryAndBudgetCoordinator (MOD-012 & MOD-014) and WSGI routes."""

from __future__ import annotations

import hashlib
import json
import unittest
from io import BytesIO

from company_os.api.http.app import make_wsgi_app
from company_os.catalog.live_lifecycle import LiveMemoryAndBudgetCoordinator
from company_os.engine.ollama_adapter import OllamaGenerationResult
from company_os.runtime.live_task_runner import LiveOfficeTaskRunner


class _StubOllama:
    def __init__(self, text: str):
        self.text = text

    def generate(self, prompt: str, *, model=None, system=None, temperature: float = 0.2):
        return OllamaGenerationResult(
            model=model or "qwen2.5-coder:3b",
            response=self.text,
            response_sha256=hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
            prompt_eval_count=20,
            eval_count=35,
            total_duration_ms=90,
        )


class LiveMemoryPromotionLifecycleTests(unittest.TestCase):
    def test_accepted_task_creates_verified_candidate_and_enforces_sod_on_promotion(self):
        saved_states = []
        coord = LiveMemoryAndBudgetCoordinator(
            tenant_id="11111111-1111-4111-8111-111111111111",
            persist_promotion=lambda rec: saved_states.append((rec.record_id, rec.state.value)),
        )
        runner = LiveOfficeTaskRunner(
            tenant_id="t1",
            ollama_client=_StubOllama("1. Bulgu dogrulandi.\n2. Kanit ozeti uretildi."),  # type: ignore[arg-type]
            on_task_accepted=coord.on_task_verified,
            poll_interval_seconds=0.0,
        )
        submitted = runner.submit_task(
            {
                "title": "Hafiza aday uretim testi",
                "goal": "Kabul edilen gorev otomatik hafiza adayi uretmelidir.",
                "work_type": "RESEARCH",
                "role_id": "EXP-02",
            }
        )
        summary = runner.run_once()
        self.assertEqual(summary.outcome, "ACCEPTED")

        promotions = coord.list_promotions()
        self.assertEqual(len(promotions), 1)
        rec_id = promotions[0]["record_id"]
        self.assertTrue(rec_id.startswith(f"mem-{submitted['task_id'][:12]}"))
        self.assertEqual(promotions[0]["state"], "VERIFIED")
        self.assertEqual(promotions[0]["verified_by"], "INDEPENDENT_LOCAL_VERIFIER")

        # Same actor cannot promote (Separation of Duties)
        with self.assertRaises(PermissionError):
            coord.promote_memory(record_id=rec_id, approver_id="INDEPENDENT_LOCAL_VERIFIER")

        # Distinct approver promotes cleanly
        promoted = coord.promote_memory(record_id=rec_id, approver_id="OWNER_HUMAN")
        self.assertEqual(promoted["state"], "PROMOTED")
        self.assertEqual(promoted["promoted_by"], "OWNER_HUMAN")
        self.assertEqual(saved_states[-1], (rec_id, "PROMOTED"))

    def test_rejected_task_does_not_create_memory_candidate(self):
        coord = LiveMemoryAndBudgetCoordinator(tenant_id="11111111-1111-4111-8111-111111111111")
        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("kisa"),  # type: ignore[arg-type]
            on_task_accepted=coord.on_task_verified,
            poll_interval_seconds=0.0,
        )
        runner.submit_task(
            {
                "title": "Reddedilen gorev",
                "goal": "Reddedilen gorev hafiza adayi acmamalidir.",
                "work_type": "SOFTWARE",
                "role_id": "EXP-01",
            }
        )
        summary = runner.run_once()
        self.assertEqual(summary.outcome, "REJECTED")
        self.assertEqual(coord.list_promotions(), [])


class ExternalEffectAndBudgetLifecycleTests(unittest.TestCase):
    def test_host_restriction_idempotency_and_unknown_reconciliation(self):
        outcomes = iter(
            [
                {"outcome": "COMMITTED", "http_status": 200},
                {"outcome": "UNKNOWN", "http_status": 504},
                {"outcome": "COMMITTED", "http_status": 200},
            ]
        )
        saved_effects = []
        coord = LiveMemoryAndBudgetCoordinator(
            tenant_id="11111111-1111-4111-8111-111111111111",
            budget_limit_minor=500,
            dispatcher=lambda _url, _payload: next(outcomes),
            persist_effect=lambda entry: saved_effects.append((entry.idempotency_key, entry.status)),
        )

        # Remote host blocked before touching budget
        with self.assertRaises(PermissionError):
            coord.execute_external_effect(
                idempotency_key="k-remote",
                provider="webhook",
                target_url="https://untrusted.example/hook",
                payload={"x": 1},
                reserved_minor=50,
            )
        self.assertEqual(coord.budget_summary()["available_minor"], 500)

        # Successful commit deducts settled cost
        res1 = coord.execute_external_effect(
            idempotency_key="k-1",
            provider="local-webhook",
            target_url="http://127.0.0.1:9999/hook",
            payload={"event": "ping"},
            reserved_minor=100,
            actual_minor=80,
        )
        self.assertFalse(res1["replayed"])
        self.assertEqual(res1["effect"]["status"], "COMMITTED")
        self.assertEqual(res1["budget"]["spent_minor"], 80)
        self.assertEqual(res1["budget"]["available_minor"], 420)

        # Idempotent replay does not double-spend
        replay = coord.execute_external_effect(
            idempotency_key="k-1",
            provider="local-webhook",
            target_url="http://127.0.0.1:9999/hook",
            payload={"event": "ping"},
            reserved_minor=100,
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["budget"]["spent_minor"], 80)

        # Conflicting provider for same idempotency key fails closed
        with self.assertRaises(ValueError):
            coord.execute_external_effect(
                idempotency_key="k-1",
                provider="other-provider",
                target_url="http://127.0.0.1:9999/hook",
                payload={},
                reserved_minor=10,
            )

        # UNKNOWN locks further spend until reconciled
        res_unk = coord.execute_external_effect(
            idempotency_key="k-2",
            provider="local-webhook",
            target_url="http://127.0.0.1:9999/hook",
            payload={"event": "timeout"},
            reserved_minor=120,
        )
        self.assertEqual(res_unk["effect"]["status"], "UNKNOWN")
        self.assertTrue(res_unk["budget"]["blocked_by_unknown"])
        with self.assertRaises(RuntimeError):
            coord.execute_external_effect(
                idempotency_key="k-3",
                provider="local-webhook",
                target_url="http://127.0.0.1:9999/hook",
                payload={},
                reserved_minor=10,
            )

        # Reconcile UNKNOWN -> unblocks budget
        rec = coord.reconcile_unknown_effect(
            idempotency_key="k-2", actual_minor=60, final_status="COMMITTED"
        )
        self.assertFalse(rec["budget"]["blocked_by_unknown"])
        self.assertEqual(rec["budget"]["spent_minor"], 140)
        self.assertEqual(rec["budget"]["available_minor"], 360)
        self.assertEqual(saved_effects[-1], ("k-2", "COMMITTED"))

    def test_sustained_budget_reconciliation_soak_100_effects(self):
        """MOD-014 sustained reconciliation soak: 100 effects with mixed COMMITTED/REVERTED/UNKNOWN."""
        calls = 0

        def dispatcher(_url, payload):
            nonlocal calls
            calls += 1
            idx = int(payload["idx"])
            if idx % 10 == 0:
                return {"outcome": "UNKNOWN", "http_status": 504}
            if idx % 5 == 0:
                return {"outcome": "REVERTED", "http_status": 422}
            return {"outcome": "COMMITTED", "http_status": 200}

        coord = LiveMemoryAndBudgetCoordinator(
            tenant_id="11111111-1111-4111-8111-111111111111",
            budget_limit_minor=10_000,
            allowed_hosts=frozenset({"127.0.0.1", "api.approved.example"}),
            dispatcher=dispatcher,
        )
        expected_spent = 0
        for idx in range(1, 101):
            key = f"soak-key-{idx:03d}"
            res = coord.execute_external_effect(
                idempotency_key=key,
                provider="approved-api",
                target_url="https://api.approved.example/v1/run",
                payload={"idx": idx},
                reserved_minor=50,
                actual_minor=40,
            )
            if idx % 10 == 0:
                self.assertEqual(res["effect"]["status"], "UNKNOWN")
                self.assertTrue(res["budget"]["blocked_by_unknown"])
                coord.reconcile_unknown_effect(
                    idempotency_key=key, actual_minor=30, final_status="COMMITTED"
                )
                expected_spent += 30
            elif idx % 5 == 0:
                self.assertEqual(res["effect"]["status"], "REVERTED")
            else:
                self.assertEqual(res["effect"]["status"], "COMMITTED")
                expected_spent += 40

        summary = coord.budget_summary()
        self.assertEqual(calls, 100)
        self.assertFalse(summary["blocked_by_unknown"])
        self.assertEqual(summary["held_minor"], 0)
        self.assertEqual(summary["spent_minor"], expected_spent)
        self.assertEqual(summary["available_minor"], 10_000 - expected_spent)
        self.assertEqual(len(coord.list_effects()), 100)


class LifecycleWsgiRoutesTests(unittest.TestCase):
    def _post(self, app, path: str, payload: dict, *, origin: str = "http://127.0.0.1:8765"):
        raw = json.dumps(payload).encode("utf-8")
        box = []

        def start_response(status, headers):
            box.append((status, dict(headers)))

        out = b"".join(
            app(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": path,
                    "QUERY_STRING": "",
                    "CONTENT_TYPE": "application/json",
                    "CONTENT_LENGTH": str(len(raw)),
                    "HTTP_HOST": "127.0.0.1:8765",
                    "HTTP_ORIGIN": origin,
                    "wsgi.input": BytesIO(raw),
                },
                start_response,
            )
        )
        return box[0][0], json.loads(out.decode("utf-8")) if out.startswith(b"{") else out

    def test_readonly_app_rejects_post_lifecycle_routes(self):
        app = make_wsgi_app()
        st1, _ = self._post(app, "/api/memory-promotions", {"action": "promote"})
        st2, _ = self._post(app, "/api/external-effects", {"action": "dispatch"})
        self.assertTrue(st1.startswith("405"))
        self.assertTrue(st2.startswith("405"))

    def test_post_memory_and_external_effect_routes_enforce_sod_and_unknown_lock(self):
        coord = LiveMemoryAndBudgetCoordinator(
            tenant_id="11111111-1111-4111-8111-111111111111",
            budget_limit_minor=200,
            dispatcher=lambda _u, _p: {"outcome": "UNKNOWN", "http_status": 503},
        )
        coord.submit_candidate(record_id="m-1", summary="s", evidence_digest="sha256:abc")
        coord.verify_candidate(record_id="m-1", verifier_id="VERIFIER_A")

        def mem_handler(p):
            if p.get("action") == "promote":
                return coord.promote_memory(record_id=p["record_id"], approver_id=p["actor_id"])
            raise ValueError("BAD_ACTION")

        def eff_handler(p):
            return coord.execute_external_effect(
                idempotency_key=p["idempotency_key"],
                provider=p["provider"],
                target_url=p["target_url"],
                payload=p.get("payload") or {},
                reserved_minor=int(p["reserved_minor"]),
            )

        app = make_wsgi_app(memory_action_handler=mem_handler, external_effect_handler=eff_handler)

        # SoD violation -> 403
        st_sod, _ = self._post(
            app,
            "/api/memory-promotions",
            {"action": "promote", "record_id": "m-1", "actor_id": "VERIFIER_A"},
        )
        self.assertTrue(st_sod.startswith("403"))

        # Distinct approver -> 200
        st_ok, body_ok = self._post(
            app,
            "/api/memory-promotions",
            {"action": "promote", "record_id": "m-1", "actor_id": "OWNER_HUMAN"},
        )
        self.assertTrue(st_ok.startswith("200"))
        self.assertEqual(body_ok["record"]["state"], "PROMOTED")

        # First UNKNOWN effect -> 201, second effect -> 409 Conflict (BLOCKED_BY_UNKNOWN_COST)
        st_u1, _ = self._post(
            app,
            "/api/external-effects",
            {
                "idempotency_key": "eff-u1",
                "provider": "local-hook",
                "target_url": "http://127.0.0.1:9999/h",
                "reserved_minor": 50,
            },
        )
        self.assertTrue(st_u1.startswith("201"))
        st_u2, _ = self._post(
            app,
            "/api/external-effects",
            {
                "idempotency_key": "eff-u2",
                "provider": "local-hook",
                "target_url": "http://127.0.0.1:9999/h",
                "reserved_minor": 50,
            },
        )
        self.assertTrue(st_u2.startswith("409"))

    def test_foreign_tenant_catalog_pin_rejected(self):
        from company_os.runtime.live_task_runner import (
            ENGINEER_PILOT_PROMPT,
            ENGINEER_PILOT_VERSION,
        )

        pilot_digest = hashlib.sha256(ENGINEER_PILOT_PROMPT.encode("utf-8")).hexdigest()

        class _ForeignTenantCatalog:
            def list_catalog_entries(self, tenant_id: str) -> list[dict]:
                return [
                    {
                        "tenant_id": "22222222-2222-4222-8222-222222222222",
                        "kind": "ROLE",
                        "name": "EXP-01",
                        "version": ENGINEER_PILOT_VERSION,
                        "digest": pilot_digest,
                        "active": True,
                    }
                ]

        runner = LiveOfficeTaskRunner(
            tenant_id="11111111-1111-4111-8111-111111111111",
            registry_tenant_id="11111111-1111-4111-8111-111111111111",
            ollama_client=_StubOllama("1. Katalog testi."),  # type: ignore[arg-type]
            engineer_pilot_catalog=_ForeignTenantCatalog(),
            poll_interval_seconds=0.0,
        )
        submitted = runner.submit_task(
            {
                "title": "Yabancı tenant katalog reddi",
                "goal": "Yabancı tenant katalog pini kabul edilmemelidir.",
                "work_type": "SOFTWARE",
                "role_id": "EXP-01",
            }
        )
        runner.run_once()
        runs = {r["task_id"]: r for r in runner.list_runs()}
        self.assertEqual(runs[submitted["task_id"]]["state"], "ERROR")
        self.assertEqual(
            runs[submitted["task_id"]].get("error"),
            "OfficeTaskValidationError: ENGINEER_PILOT_CATALOG_PIN_MISSING_OR_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
