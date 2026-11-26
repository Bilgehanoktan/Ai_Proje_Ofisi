"""Unit tests for worker health snapshot, key rotation policy, verifier calibration, and readiness."""

from __future__ import annotations

import unittest

from company_os.bootstrap.readiness import build_production_readiness_snapshot
from company_os.kernel.key_rotation import KeyRotationPolicy
from company_os.runtime.worker_daemon import AutonomousWorkerDaemon
from independent_verifier.calibration import VerifierCalibrationProfile


class ProductionReadinessAndHardeningTests(unittest.TestCase):
    def test_worker_daemon_health_snapshot_healthy_and_halted(self) -> None:
        tasks = [{"task_id": "t-1"}]

        daemon = AutonomousWorkerDaemon(
            claim_next=lambda: tasks.pop(0) if tasks else None,
            execute_task=lambda task: {"ok": True},
            verify_task=lambda task, res: {"accepted": True},
            max_consecutive_errors=2,
        )
        daemon.run_once()
        snap = daemon.health_snapshot()
        self.assertTrue(snap["healthy"])
        self.assertEqual(snap["processed"], 1)
        self.assertEqual(snap["accepted"], 1)

        failing = AutonomousWorkerDaemon(
            claim_next=lambda: {"task_id": "t-err"},
            execute_task=lambda task: (_ for _ in ()).throw(RuntimeError("boom")),
            verify_task=lambda task, res: {"accepted": False},
            max_consecutive_errors=1,
        )
        failing.run_once()
        bad_snap = failing.health_snapshot()
        self.assertFalse(bad_snap["healthy"])
        self.assertEqual(bad_snap["state"], "HALTED_ON_ERRORS")

    def test_key_rotation_policy(self) -> None:
        policy = KeyRotationPolicy(max_key_age_days=90, grace_period_days=7)
        self.assertEqual(policy.evaluate_key_age(10), "ACTIVE")
        self.assertEqual(policy.evaluate_key_age(85), "ROTATION_DUE")
        self.assertEqual(policy.evaluate_key_age(90), "EXPIRED")
        policy.validate_rotation("key-v1", "key-v2")
        with self.assertRaises(ValueError):
            policy.validate_rotation("key-v1", "key-v1")

    def test_verifier_calibration_profile(self) -> None:
        cal = VerifierCalibrationProfile()
        self.assertTrue(cal.check_work_type("SOFTWARE", passed_checks=13, total_checks=13)["accepted"])
        self.assertFalse(cal.check_work_type("SOFTWARE", passed_checks=12, total_checks=13)["accepted"])
        self.assertTrue(cal.check_work_type("RESEARCH", receipt_count=2)["accepted"])
        self.assertFalse(cal.check_work_type("RESEARCH", receipt_count=0)["accepted"])
        self.assertTrue(cal.check_work_type("SPREADSHEET", cell_count=10)["accepted"])
        self.assertTrue(cal.check_work_type("OBLIGATION", uncertainty_ratio=0.2)["accepted"])
        self.assertFalse(cal.check_work_type("OBLIGATION", uncertainty_ratio=0.5)["accepted"])

    def test_production_readiness_snapshot(self) -> None:
        ready = build_production_readiness_snapshot(
            schema_version=88,
            owner_auth_enrolled=True,
            clock_epoch_active=True,
            allowed_https_domains=["api.example.com"],
            signer_key_age_days=15,
            remote_ssh_host="prod-eu-1",
        )
        self.assertTrue(ready["ready_for_remote_deploy"])
        self.assertEqual(ready["blockers"], [])

        blocked = build_production_readiness_snapshot(
            schema_version=88,
            owner_auth_enrolled=True,
            clock_epoch_active=True,
            allowed_https_domains=[],
            signer_key_age_days=95,
            remote_ssh_host="",
        )
        self.assertFalse(blocked["ready_for_remote_deploy"])
        self.assertIn("signer_key_valid", blocked["blockers"])
        self.assertIn("https_allowlist_configured", blocked["blockers"])
        self.assertIn("remote_ssh_host_configured", blocked["blockers"])

    def test_http_readiness_and_verifier_calibration_endpoints(self) -> None:
        import json
        import os
        from unittest.mock import patch
        from company_os.api.http.app import make_wsgi_app

        app = make_wsgi_app()

        def call_get(path: str) -> tuple[str, dict]:
            captured: dict[str, str] = {}

            def start_response(status: str, headers: list[tuple[str, str]]) -> None:
                captured["status"] = status

            body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path}, start_response))
            return captured["status"], json.loads(body.decode("utf-8"))

        with patch.dict(
            os.environ,
            {
                "AIPOF_SCHEMA_VERSION": "88",
                "AIPOF_OWNER_AUTH_ENROLLED": "true",
                "AIPOF_CLOCK_EPOCH_ACTIVE": "1",
                "AIPOF_ALLOWED_HTTPS_DOMAINS": "api.example.com",
                "AIPOF_SIGNER_KEY_AGE_DAYS": "10",
                "AIPOF_REMOTE_SSH_HOST": "prod-eu-1",
            },
            clear=False,
        ):
            status, payload = call_get("/api/readiness")
            self.assertEqual(status, "200 OK")
            self.assertTrue(payload["ready_for_remote_deploy"])
            self.assertEqual(payload["key_status"], "ACTIVE")

        cal_status, cal_payload = call_get("/api/verifier-calibration")
        self.assertEqual(cal_status, "200 OK")
        self.assertEqual(cal_payload["calibration"]["min_software_oracle_pass_ratio"], 1.0)
        self.assertEqual(cal_payload["calibration"]["min_research_receipt_count"], 1)


if __name__ == "__main__":
    unittest.main()
