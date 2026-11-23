"""Safe operator diagnostics and real-binding-only launcher regressions."""

import unittest
from unittest.mock import patch

from scripts.database.audit_local_state import installation_readiness, owner_auth_readiness


class DiagnosticConnection:
    def __init__(self, roots, receipts):
        self.roots = roots
        self.receipts = receipts
        self.calls = []

    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        return self

    def fetchall(self):
        return self.roots

    def fetchone(self):
        return self.receipts


class ReadinessTests(unittest.TestCase):
    def test_expired_or_rebooted_root_has_specific_diagnostic_without_writes(self):
        c = DiagnosticConnection(
            [("installation-fixture", 1, False, False, True, False, False)], (1, 0, 1)
        )
        with (
            patch("pathlib.Path.read_text", return_value="fixture-boot"),
            patch("time.clock_gettime_ns", return_value=1000, create=True),
            patch("time.CLOCK_BOOTTIME", 7, create=True),
        ):
            result = installation_readiness(c)
        self.assertEqual(
            result["roots"][0]["blockers"], ["HOST_BOOT_MISMATCH", "ROOT_BOOTTIME_WINDOW_CLOSED"]
        )
        self.assertEqual(result["next_step"], "SUPPORTED_OWNER_AUTH_OR_RECOVERY_REQUIRED")
        self.assertTrue(all(sql.startswith("SELECT") for sql, _ in c.calls))
        self.assertEqual(result["scope"], "DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION")

    def test_old_root_does_not_hide_new_open_window_and_no_authorization_is_claimed(self):
        c = DiagnosticConnection(
            [
                ("old-fixture", 1, False, False, False, True, False),
                ("new-fixture", 2, True, True, True, False, False),
            ],
            (2, 1, 2),
        )
        with (
            patch("pathlib.Path.read_text", return_value="fixture-boot"),
            patch("time.clock_gettime_ns", return_value=1000, create=True),
            patch("time.CLOCK_BOOTTIME", 7, create=True),
        ):
            result = installation_readiness(c)
        self.assertEqual(result["next_step"], "CHECK_NATIVE_AUTHORITY_AND_SESSION")
        self.assertNotIn("authorized", result)

    def test_canonical_kernel_launcher_requires_real_profile_before_connect(self):
        from company_os.api.http.kernel_binding import main

        with patch("company_os.api.http.kernel_binding.make_connector") as connect:
            with self.assertRaises(SystemExit) as caught:
                main([])
        self.assertEqual(caught.exception.code, 2)
        connect.assert_not_called()

    def test_legacy_entries_are_inert_and_cannot_create_demo_receipts(self):
        import importlib

        for name in ("scripts.serve_configured_ui", "scripts.serve_standalone"):
            with self.subTest(module=name):
                with patch(
                    "company_os.api.http.task_http.create_server",
                    side_effect=AssertionError("Import must not start a server"),
                ):
                    module = importlib.import_module(name)
                self.assertFalse(hasattr(module, "InteractiveDemoBackend"))
                with patch("company_os.api.http.kernel_binding.make_connector") as connect:
                    with self.assertRaises(SystemExit) as caught:
                        module.main([])
                self.assertEqual(caught.exception.code, 2)
                connect.assert_not_called()

    def test_owner_auth_readiness_reports_three_diagnostic_states_readonly(self):
        class QueueDiagnosticConnection:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = []

            def execute(self, sql, args=()):
                self.calls.append((sql, args))
                return self

            def fetchone(self):
                return self.responses.pop(0)

        cases = [
            (
                [(False, False, False), (0,), (0,)],
                "INSTALL_OWNER_AUTH_V1_AFTER_G0_APPROVAL",
                False,
            ),
            (
                [(True, True, True), (0,), (1,)],
                "ENROLL_OWNER_AUTH_SIGNER_AND_CLOCK_REQUIRED",
                True,
            ),
            (
                [(True, True, True), (1,), (1,)],
                "READY_FOR_NATIVE_OWNER_AUTH_CHECK",
                True,
            ),
        ]
        for responses, expected_step, expected_installed in cases:
            conn = QueueDiagnosticConnection(responses)
            with self.subTest(expected_step=expected_step):
                result = owner_auth_readiness(conn)
                self.assertEqual(result["scope"], "DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION")
                self.assertIs(result["native_v1_installed"], expected_installed)
                self.assertEqual(result["next_step"], expected_step)
                self.assertNotIn("authorized", result)
                self.assertTrue(all(sql.startswith("SELECT") for sql, _ in conn.calls))
