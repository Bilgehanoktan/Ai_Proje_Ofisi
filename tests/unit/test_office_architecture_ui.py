"""Unit tests for MOD-011 / DEC-28C / DEC-017 Office Architecture UI & FloorGeometryVersion API."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from typing import Any

from company_os.api.http.app import make_wsgi_app
from company_os.projections.office_layout import (
    build_dec28c_floor_geometry,
    build_office_architecture_payload,
)

ROOT = Path(__file__).resolve().parents[2]


class OfficeArchitectureUiTests(unittest.TestCase):
    def test_dec28c_floor_geometry_is_deterministic_non_authoritative_and_reserve_closed(self) -> None:
        g1 = build_dec28c_floor_geometry()
        g2 = build_dec28c_floor_geometry()
        self.assertEqual(g1["geometry_hash"], g2["geometry_hash"])
        self.assertTrue(g1["geometry_hash"].startswith("sha256:"))
        self.assertEqual(g1["floor_id"], "F1-DEC28C")
        self.assertEqual(g1["authority_mode"], "READ_ONLY_PRESENTATION_NO_GRANT")

        zones = {z["zone_id"]: z for z in g1["zones"]}
        self.assertIn("F1-COR", zones)
        self.assertFalse(zones["F1-EXP"]["open"])
        doors = {d["door_id"]: d for d in g1["door_portals"]}
        self.assertFalse(doors["D-EXP"]["enabled"])
        portals = {p["portal_id"]: p for p in g1["floor_portals"]}
        self.assertFalse(portals["P-UPPER-FLOOR"]["enabled"])

    def test_http_office_architecture_exposes_087_pins_without_grant_authority(self) -> None:
        app = make_wsgi_app()
        captured: dict[str, str] = {}

        def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
            captured["status"] = status

        environ: dict[str, Any] = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/office-architecture",
            "QUERY_STRING": "tenant_id=t-test",
            "wsgi.input": io.BytesIO(b""),
        }
        body = b"".join(app(environ, start_response))
        self.assertEqual(captured["status"], "200 OK")
        payload = json.loads(body.decode("utf-8"))
        cat = payload["catalog_summary"]
        self.assertEqual(cat["authority_note"], "SKILL_AND_ROLE_DEFINITIONS_ARE_NOT_GRANTS_MOD_001_REQUIRED")
        self.assertGreaterEqual(len(cat["roles"]), 6)
        self.assertGreaterEqual(len(cat["skills"]), 6)
        self.assertTrue(all(s["grant_authority"] is False for s in cat["skills"]))
        direct = build_office_architecture_payload(tenant_id="t-test")
        self.assertEqual(payload["floor_geometry"]["geometry_hash"], direct["floor_geometry"]["geometry_hash"])

    def test_dashboard_template_includes_dec017_seven_tabs_and_accessibility_controls(self) -> None:
        html = (ROOT / "product/frontend/office/scenes/dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="agent-detail-view"', html)
        for tab_panel in (
            "ad-overview",
            "ad-runs",
            "ad-skills",
            "ad-authority",
            "ad-evidence",
            "ad-memory",
            "ad-audit",
        ):
            self.assertIn(f'id="{tab_panel}"', html)
        self.assertIn('id="toggle-motion"', html)
        self.assertIn('id="scene-filter"', html)
        self.assertIn('id="focus-selected"', html)
        self.assertIn('id="skill-library"', html)
        self.assertIn('id="nav-kpi-box"', html)


if __name__ == "__main__":
    unittest.main()
