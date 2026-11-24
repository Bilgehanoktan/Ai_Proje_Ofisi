"""Verify /preview/phaser works air-gapped (no external CDN) with live agent_instances."""

import sys
from pathlib import Path
from threading import Thread
from wsgiref.simple_server import make_server

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "product/backend"), str(ROOT / "contracts/source/python")]

from company_os.api.http.app import make_wsgi_app  # noqa: E402


def main():
    state = {"connected": True}

    def snapshot():
        if not state["connected"]:
            return {"mode": "DEMO_SYNTHETIC", "connected": False}
        return {
            "mode": "LOCAL_OFFICE_ONLY",
            "connected": True,
            "agent_instances": [
                {"agent_instance_id": "1", "role_id": "EXP-01", "display_name": "Engineer #1", "state": "RUNNING", "active_task_title": "MGT-01"},
                {"agent_instance_id": "2", "role_id": "EXP-01", "display_name": "Engineer #2", "state": "IDLE"},
                {"agent_instance_id": "3", "role_id": "EXP-02", "display_name": "Research #1", "state": "IDLE"},
                {"agent_instance_id": "4", "role_id": "MGR-01", "display_name": "Orchestrator #1", "state": "IDLE"},
                {"agent_instance_id": "5", "role_id": "QA-01", "display_name": "QA #1", "state": "IDLE"},
            ],
        }

    app = make_wsgi_app(live_snapshot_provider=snapshot)
    with make_server("127.0.0.1", 0, app) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    page = browser.new_page()
                    page.route("https://**/*", lambda route: route.abort())
                    page.goto(f"http://127.0.0.1:{server.server_port}/preview/phaser")
                    expect(page.locator("#status")).to_contain_text("5 canlı ajan", timeout=8000)
                    expect(page.locator("#agents li")).to_have_count(5)
                    state["connected"] = False
                    expect(page.locator("#status")).to_contain_text("ulaşılamadı", timeout=8000)
                    expect(page.locator("#agents li")).to_have_count(0)
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=2)
    print("PASS: air-gapped local Phaser 2.5D + 5 agent_instances + disconnect guard")


if __name__ == "__main__":
    main()
