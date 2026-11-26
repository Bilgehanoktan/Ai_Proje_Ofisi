"""Unit tests for MOD-012 catalog lifecycle, MOD-014 budget caps/SSRF, and MOD-006/007 HTTPS allowlist."""

from __future__ import annotations

import http.server
import threading
import unittest
import urllib.error

from company_os.broker.https_allowlist import HttpsAllowlistPolicy
from company_os.catalog.live_lifecycle import LiveMemoryAndBudgetCoordinator
from company_os.catalog.memory_promotion import (
    CatalogEntry,
    CatalogKind,
    CatalogProfileSpec,
    PromotionState,
    TenantCatalogRegistry,
)


class _TestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello-allowlist")
        elif self.path == "/big":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 2048)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class HardeningMod012Mod014HttpsTests(unittest.TestCase):
    def test_catalog_deprecate_list_and_verify_digest(self) -> None:
        reg = TenantCatalogRegistry()
        spec = CatalogProfileSpec(
            kind=CatalogKind.ROLE, name="EXP-01", version="1.0.0", content="role-body-v1"
        )
        reg.register(spec.to_entry("tenant-a"))
        reg.register(spec.to_entry("tenant-b"))

        self.assertTrue(reg.verify_digest("tenant-a", CatalogKind.ROLE, "EXP-01", "1.0.0", "role-body-v1"))
        self.assertFalse(reg.verify_digest("tenant-a", CatalogKind.ROLE, "EXP-01", "1.0.0", "tampered"))
        self.assertEqual(len(reg.list_entries("tenant-a")), 1)

        deprecated = reg.deprecate("tenant-a", CatalogKind.ROLE, "EXP-01", "1.0.0")
        self.assertFalse(deprecated.active)
        self.assertEqual(len(reg.list_entries("tenant-a", active_only=True)), 0)
        self.assertEqual(len(reg.list_entries("tenant-a", active_only=False)), 1)
        # Tenant-b remains unaffected
        self.assertEqual(len(reg.list_entries("tenant-b", active_only=True)), 1)
        with self.assertRaises(PermissionError):
            reg.resolve("tenant-a", CatalogKind.ROLE, "EXP-01", "1.0.0")

    def test_memory_search_and_repropose_rejected(self) -> None:
        coord = LiveMemoryAndBudgetCoordinator(tenant_id="tenant-a", budget_limit_minor=500)
        coord.submit_candidate(
            record_id="mem-001",
            summary="PostgreSQL 087 RLS isolation rule",
            evidence_digest="sha256:aaa",
        )
        coord.reject_memory(record_id="mem-001", reviewer_id="rev-1")
        reproposed = coord.repropose_memory(
            record_id="mem-001",
            summary="PostgreSQL 087 FORCE RLS isolation rule (updated)",
            evidence_digest="sha256:bbb",
        )
        self.assertEqual(reproposed["state"], PromotionState.CANDIDATE.value)
        coord.verify_candidate(record_id="mem-001", verifier_id="ver-1")
        coord.promote_memory(record_id="mem-001", approver_id="app-1")

        hits = coord.search_promoted_memory("force rls")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["record_id"], "mem-001")
        self.assertEqual(coord.search_promoted_memory("nonexistent"), [])

    def test_budget_single_effect_cap_provider_summary_and_https_requirement(self) -> None:
        coord = LiveMemoryAndBudgetCoordinator(
            tenant_id="tenant-a",
            budget_limit_minor=1000,
            max_single_effect_minor=200,
            allowed_hosts=frozenset({"127.0.0.1", "api.example.com"}),
            dispatcher=lambda url, payload: {"outcome": "COMMITTED", "http_status": 200},
        )
        # Exceeds per-effect cap
        with self.assertRaises(ValueError):
            coord.execute_external_effect(
                idempotency_key="k-cap",
                provider="prov-a",
                target_url="https://api.example.com/hook",
                payload={"x": 1},
                reserved_minor=250,
            )
        # External host over plain http must be rejected
        with self.assertRaises(PermissionError):
            coord.execute_external_effect(
                idempotency_key="k-http",
                provider="prov-a",
                target_url="http://api.example.com/hook",
                payload={"x": 1},
                reserved_minor=100,
            )
        # Credentials in URL must be rejected
        with self.assertRaises(ValueError):
            coord.execute_external_effect(
                idempotency_key="k-cred",
                provider="prov-a",
                target_url="https://user:pass@api.example.com/hook",
                payload={"x": 1},
                reserved_minor=100,
            )
        # Valid external https call succeeds
        res = coord.execute_external_effect(
            idempotency_key="k-ok",
            provider="prov-a",
            target_url="https://api.example.com/hook",
            payload={"x": 1},
            reserved_minor=150,
            actual_minor=120,
        )
        self.assertEqual(res["effect"]["status"], "COMMITTED")
        self.assertEqual(coord.budget_summary()["max_single_effect_minor"], 200)
        self.assertEqual(coord.provider_summary()["prov-a"]["COMMITTED"], 1)

    def test_https_allowlist_policy_ssrf_redirects_and_size_cap(self) -> None:
        policy = HttpsAllowlistPolicy(allowed_domains=frozenset({"docs.example.com"}))
        self.assertEqual(
            policy.validate_url("https://docs.example.com/spec"),
            "https://docs.example.com/spec",
        )
        with self.assertRaises(PermissionError):
            policy.validate_url("http://docs.example.com/spec")
        with self.assertRaises(PermissionError):
            policy.validate_url("https://169.254.169.254/latest/meta-data/")
        with self.assertRaises(PermissionError):
            policy.validate_url("https://10.0.0.1/internal")
        with self.assertRaises(PermissionError):
            policy.validate_url("https://evil.example.org/data")
        with self.assertRaises(ValueError):
            policy.validate_url("https://u:p@docs.example.com/spec")

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TestHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            local_policy = HttpsAllowlistPolicy(
                allowed_domains=frozenset({"127.0.0.1"}),
                allow_loopback_http=True,
                max_response_bytes=1024,
            )
            self.assertEqual(local_policy.fetch_bounded(f"http://127.0.0.1:{port}/ok"), b"hello-allowlist")
            with self.assertRaises(ValueError):
                local_policy.fetch_bounded(f"http://127.0.0.1:{port}/big")
            with self.assertRaises(urllib.error.HTTPError):
                local_policy.fetch_bounded(f"http://127.0.0.1:{port}/redirect")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
