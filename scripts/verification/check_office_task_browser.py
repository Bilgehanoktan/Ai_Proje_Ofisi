"""Exercise the office task form, real local HTTP and worker with a synthetic model."""

import hashlib
import sys
from time import monotonic
from pathlib import Path
from threading import Thread
from wsgiref.simple_server import make_server

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "product/backend"), str(ROOT / "contracts/source/python")]

from company_os.api.http.app import make_wsgi_app  # noqa: E402
from company_os.engine.ollama_adapter import OllamaGenerationResult  # noqa: E402
from company_os.runtime.live_task_runner import LiveOfficeTaskRunner  # noqa: E402


class SyntheticModel:
    def generate(self, prompt, *, model, system):
        title = prompt.splitlines()[0].removeprefix("Görev Başlığı: ")
        response = f"{title}\n" + "\n".join(f"{i}. Girdiyi doğrula." for i in range(1, 61))
        return OllamaGenerationResult(
            model=model,
            response=response,
            response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
            prompt_eval_count=20,
            eval_count=35,
            total_duration_ms=1,
        )


def main():
    runner = LiveOfficeTaskRunner(ollama_client=SyntheticModel(), poll_interval_seconds=0.05)
    connection = {"mode": "LOCAL_OFFICE_ONLY", "connected": True}
    agents = [
        {"agent_instance_id": "agent-1", "role_id": "EXP-02", "display_name": "Araştırmacı A",
         "state": "IDLE", "worker_principal": "test-worker-a", "revision": 1},
        {"agent_instance_id": "agent-2", "role_id": "EXP-02", "display_name": "Araştırmacı B",
         "state": "IDLE", "worker_principal": "test-worker-b", "revision": 2,
         "active_task_id": "test-task", "active_attempt_id": "test-attempt",
         "active_task_title": "Örnek kaynak incelemesi"},
    ]

    lease_end = 0

    def snapshot():
        return {
            **connection,
            "command_enabled": True,
            "ollama": {"available": True},
            "office_runs": runner.list_runs(),
            "agent_instances": [dict(a, lease_remaining_ms=int((lease_end - monotonic()) * 1000))
                                for a in agents],
        }

    app = make_wsgi_app(
        live_snapshot_provider=snapshot,
        office_task_submitter=lambda payload, token: runner.submit_task(payload, bearer_token=token),
        office_tasks_provider=runner.list_runs,
    )
    with make_server("127.0.0.1", 0, app) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        runner.start_background()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    local_file = browser.new_page()
                    try:
                        dashboard = ROOT / "product/frontend/office/scenes/dashboard.html"
                        local_file.goto(dashboard.as_uri())
                        expect(local_file.locator(".file-preview-guide")).to_be_visible()
                        expect(local_file.locator("#office-task-submit")).to_be_disabled()
                        expect(local_file.locator(".task-card")).to_have_css("display", "grid")
                        assert local_file.locator("#office-canvas").evaluate(
                            "(canvas) => canvas.getContext('2d').getImageData(1, 1, 1, 1).data[3] > 0"
                        )
                        assert "__HEAD_ASSETS__" not in local_file.locator("body").inner_text()
                    finally:
                        local_file.close()
                    preview_url = f"http://127.0.0.1:{server.server_port}/preview"
                    page = browser.new_page(viewport={"width": 1440, "height": 960})
                    page.goto(preview_url)
                    expect(page.locator(".file-preview-guide")).to_be_hidden()
                    expect(page.locator(".viewport")).to_have_css("background-color", "rgb(16, 28, 48)")
                    assert page.locator("#office-canvas").evaluate(
                        "(canvas) => canvas.getContext('2d').getImageData(1, 1, 1, 1).data[0] < 40"
                    )
                    expect(page.locator("#mode-badge")).to_have_text("Yerel ofis · UNVERIFIED")
                    expect(page.locator("#stat-roles")).to_have_text("Veri yok")
                    form_bounds = page.locator("#office-task-form").bounding_box()
                    results_bounds = page.locator(".task-results").bounding_box()
                    assert form_bounds and results_bounds
                    assert results_bounds["x"] >= form_bounds["x"] + form_bounds["width"]
                    mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True,
                                              has_touch=True)
                    try:
                        mobile.goto(preview_url)
                        form_bounds = mobile.locator("#office-task-form").bounding_box()
                        results_bounds = mobile.locator(".task-results").bounding_box()
                        assert form_bounds and results_bounds
                        assert results_bounds["y"] >= form_bounds["y"] + form_bounds["height"]
                        assert mobile.evaluate("document.documentElement.scrollWidth === innerWidth")
                        expect(mobile.locator("#office-task-submit")).to_be_enabled()
                    finally:
                        mobile.close()
                    for work_type in ("RESEARCH", "SPREADSHEET", "OBLIGATION"):
                        title = f"Tarayıcı testi {work_type}"
                        expect(page.locator("#office-task-submit")).to_be_enabled()
                        page.locator("#office-task-title").fill(title)
                        page.locator("#office-task-work-type").select_option(work_type)
                        page.locator("#office-task-goal").fill("Sentetik görev çıktısını doğrula.")
                        with page.expect_response(
                            lambda response: response.url.endswith("/api/office-tasks")
                            and response.request.method == "POST"
                        ) as submission:
                            page.locator("#office-task-submit").click()
                        assert submission.value.ok, work_type
                        card = page.locator(".run-card").filter(has_text=title)
                        expect(card.locator("h3")).to_have_text(title, timeout=12000)
                        expect(card.locator(".run-status")).to_have_text("Kabul edildi", timeout=12000)
                        expect(card.locator(".run-meta")).to_be_hidden()
                        card.locator("summary").click()
                        expect(card.locator(".run-output")).to_be_visible()
                        expect(card.locator(".run-output")).to_have_text(
                            f"{title}\n" + "\n".join(f"{i}. Girdiyi doğrula." for i in range(1, 61))
                        )
                        output = card.locator(".run-output")
                        position = output.evaluate("el => { el.scrollTop = 180; return el.scrollTop; }")
                        assert position > 0
                        with page.expect_response(lambda r: r.url.endswith("/api/office-live")) as poll:
                            page.evaluate("() => import('/office/modules/main.js').then(m => m.refreshLiveOffice())")
                        poll.value.finished()
                        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                        assert output.evaluate("el => el.scrollTop") == position
                        assert runner.list_runs()[0]["work_type"] == work_type
                    page.locator("#office-task-title").fill("Kaynaklı araştırma testi")
                    page.locator("#office-task-work-type").select_option("RESEARCH")
                    page.locator("#office-task-goal").fill("Bu görev belge okuması gerektiriyor.")
                    page.locator("#office-task-read-path").fill("research_note.txt")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/office-tasks")
                        and response.request.method == "POST"
                    ) as rejected:
                        page.locator("#office-task-submit").click()
                    assert rejected.value.status == 400
                    assert rejected.value.json()["error"] == "RESEARCH_BROKER_READER_NOT_CONFIGURED"
                    assert len(runner.list_runs()) == 3
                    expect(page.locator(".scene-agent")).to_have_count(2)
                    phaser_floor = page.locator('.phaser-floor[data-ready="true"] canvas')
                    expect(phaser_floor).to_be_visible()
                    assert page.locator(".scene-agent-avatar").first.evaluate(
                        """(avatar) => {
                            const sprite = avatar.getBoundingClientRect();
                            const floor = document.querySelector('.phaser-floor canvas');
                            const bounds = floor.getBoundingClientRect();
                            const x = Math.floor((sprite.left + sprite.width / 2 - bounds.left)
                                * floor.width / bounds.width);
                            const y = Math.floor((sprite.top + sprite.height / 2 - bounds.top)
                                * floor.height / bounds.height);
                            return floor.getContext('2d').getImageData(x, y, 1, 1).data[1] > 140;
                        }"""
                    )
                    page.locator('[data-scene-agent-id="agent-2"]').press("Enter")
                    expect(page.locator("#role-title")).to_have_text("Araştırmacı B")
                    expect(page.locator("#context-state")).to_have_text("Boşta (IDLE)")
                    agents[1]["state"] = "RUNNING"
                    lease_end = monotonic() + 30
                    await_refresh = "() => import('/office/modules/main.js').then(m => m.refreshLiveOffice())"
                    page.evaluate(await_refresh)
                    expect(page.locator("#context-state")).to_have_text("Çalışıyor (RUNNING)")
                    expect(page.locator('[data-scene-agent-id="agent-2"]')).to_have_attribute("aria-pressed", "true")
                    page.locator("#tab-agents").press("Enter")
                    page.locator('[data-agent-id="agent-2"]').press("Enter")
                    expect(page.locator("#role-title")).to_have_text("Araştırmacı B")
                    expect(page.locator("#context-task-title")).to_have_text("Örnek kaynak incelemesi")
                    expect(page.locator("#context-task")).to_be_visible()
                    expect(page.locator("#context-evidence")).to_be_hidden()
                    page.locator(".agent-record summary").press("Enter")
                    expect(page.locator("#context-evidence")).to_be_visible()
                    expect(page.locator("#context-evidence")).to_contain_text("test-attempt")
                    lease_end = monotonic() + 1
                    page.evaluate(await_refresh)
                    marker = page.locator('[data-scene-agent-id="agent-2"]')
                    expect(marker).to_contain_text("Çalışıyor")
                    expect(marker).to_contain_text("Güncel değil")
                    expect(page.locator("#context-state")).to_have_text("Güncel değil (STALE)")
                    expect(page.locator("#context-task")).to_be_hidden()
                    connection["connected"] = False
                    page.evaluate(await_refresh)
                    expect(marker).to_have_count(0)
                    connection["connected"] = True
                    page.evaluate(await_refresh)
                    marker.press("Enter")
                    expect(marker).to_contain_text("Güncel değil")
                    expect(page.locator("#context-state")).to_have_text("Güncel değil (STALE)")
                    agents.pop()
                    expect(page.locator("#role-title")).to_have_text("Araştırmacı A", timeout=12000)
                    expect(page.locator('[data-scene-agent-id="agent-2"]')).to_have_count(0)
                    expect(page.locator("#context-evidence")).not_to_contain_text("test-attempt")
                    expect(page.locator("#context-task")).to_be_hidden()
                    agents.clear()
                    expect(page.locator("#role-title")).to_have_text("Seçili ajan yok", timeout=12000)
                    expect(page.locator("#context-state")).to_have_text("UNVERIFIED")
                    connection["mode"] = "LIVE_POSTGRES_18_6"
                    expect(page.locator("#mode-badge")).to_have_text("PostgreSQL bağlı")
                    connection["connected"] = False
                    expect(page.locator("#mode-badge")).to_have_text("Bağlantı kesildi")
                    expect(page.locator("#office-task-submit")).to_be_disabled()
                    expect(page.locator("#ollama-badge")).to_have_text("Ollama durumu bilinmiyor")
                    connection.update(mode="LOCAL_OFFICE_ONLY", connected=True)
                    expect(page.locator("#mode-badge")).to_have_text("Yerel ofis · UNVERIFIED")
                    expect(page.locator("#office-task-submit")).to_be_enabled()
                finally:
                    browser.close()
        finally:
            runner.stop()
            server.shutdown()
            thread.join(timeout=2)
    print("PASS: three synthetic tasks and unconfigured RESEARCH reader rejected before queueing")


if __name__ == "__main__":
    main()
