"""Exercise the office task form, real local HTTP and worker with a synthetic model."""

import hashlib
import sys
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
        response = f"{title}\n1. Girdiyi doğrula.\n2. Sonuçları kontrol et."
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

    def snapshot():
        return {
            "mode": "LOCAL_OFFICE_ONLY",
            "connected": True,
            "command_enabled": True,
            "ollama": {"available": True},
            "office_runs": runner.list_runs(),
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
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{server.server_port}/preview")
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
                        expect(card).to_contain_text("ACCEPTED", timeout=12000)
                        expect(card.locator(".run-output")).to_have_text(
                            f"{title}\n1. Girdiyi doğrula.\n2. Sonuçları kontrol et."
                        )
                        assert runner.list_runs()[0]["work_type"] == work_type
                finally:
                    browser.close()
        finally:
            runner.stop()
            server.shutdown()
            thread.join(timeout=2)
    print("PASS: browser, HTTP, worker and result card for 3 work types (synthetic model)")


if __name__ == "__main__":
    main()
