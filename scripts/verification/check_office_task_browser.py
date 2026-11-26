"""Exercise the office task form, real local HTTP and worker with a synthetic model and real Broker/XLSX/Obligation tool adapters."""

from contextlib import contextmanager
import hashlib
import io
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from time import monotonic
from pathlib import Path
from threading import Thread
from uuid import uuid4
from wsgiref.simple_server import make_server

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "product/backend"), str(ROOT / "contracts/source/python")]

from company_os.api.http.app import make_wsgi_app  # noqa: E402
from company_os.broker.tool_broker import Broker  # noqa: E402
from company_os.engine.ollama_adapter import OllamaGenerationResult  # noqa: E402
from company_os.runtime.live_task_runner import LiveOfficeTaskRunner  # noqa: E402
from packages.contracts.execution import EngineBinding, ToolRequest  # noqa: E402


def _build_minimal_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="3" uniqueCount="3">'
            "<si><t>Kalem</t></si><si><t>Lisans</t></si><si><t>Sunucu</t></si></sst>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>2000</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>1200</v></c></row>'
            '<row r="3"><c r="A3" t="s"><v>2</v></c><c r="B3"><v>800</v></c></row>'
            "</sheetData></worksheet>",
        )
    return buf.getvalue()


def _parse_xlsx_summary(raw_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        shared = [
            si.text or ""
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).iter()
            if si.tag.endswith("}t") or si.tag == "t"
        ]
        root_sh = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        cells: list[str] = []
        for c in root_sh.iter():
            if not (c.tag.endswith("}c") or c.tag == "c"):
                continue
            v_elem = next((ch for ch in c if ch.tag.endswith("}v") or ch.tag == "v"), None)
            if v_elem is None or v_elem.text is None:
                continue
            val = v_elem.text
            if c.attrib.get("t") == "s" and val.isdigit() and int(val) < len(shared):
                val = shared[int(val)]
            cells.append(val)
    return {"sheet": "xl/worksheets/sheet1.xml", "cell_count": len(cells), "sample_cells": cells}


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
                        page.locator("#office-task-role").select_option("EXP-01")
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

                    # Wire real Broker workspace.read, OpenXML .xlsx SPREADSHEET reader, and OBLIGATION reader
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_root = Path(tmp_dir)
                        research_file = tmp_root / "research_note.txt"
                        research_file.write_text("MADDE-42: Mimari kapsam ve güvenlik sınırı doğrulandı.\n", encoding="utf-8")
                        research_sha = hashlib.sha256(research_file.read_bytes()).hexdigest()

                        xlsx_file = tmp_root / "budget_2026.xlsx"
                        xlsx_file.write_bytes(_build_minimal_xlsx())
                        xlsx_sha = hashlib.sha256(xlsx_file.read_bytes()).hexdigest()

                        ob_file = tmp_root / "obligation_2026.html"
                        ob_file.write_text("<html><body><p>MADDE-12: Yedekleme doğrulaması zorunludur.</p></body></html>", encoding="utf-8")
                        ob_sha = hashlib.sha256(ob_file.read_bytes()).hexdigest()

                        class _MemKernel:
                            def consume(self, request, *, frame_digest: str, frame: bytes) -> dict:
                                return {
                                    "effect_permitted": True,
                                    "frame_digest": frame_digest,
                                    "consume_id": str(uuid4()),
                                }

                            @contextmanager
                            def effect_scope(self, consume_id, request, *, frame_digest: str):
                                class _Tx:
                                    def complete(self_tx, c_id, result):
                                        return {
                                            "status": "SUCCEEDED",
                                            "consume_id": str(c_id),
                                            "frame_digest": frame_digest,
                                            "receipt_id": str(uuid4()),
                                            "artifact_ids": [],
                                        }

                                yield _Tx()

                        class _MemJournal:
                            def reserve(self, key: str, payload: dict) -> None:
                                return None

                        class _FileReadExec:
                            def execute(self, call, *, transaction):
                                raw = (tmp_root / call.arguments.relative_path).read_bytes()
                                return {
                                    "kind": "READ",
                                    "content_digest": hashlib.sha256(raw).hexdigest(),
                                    "bytes_read": len(raw),
                                }

                        binding = EngineBinding(
                            engine_session_id=uuid4(),
                            attempt_id=uuid4(),
                            fencing_epoch=1,
                            revision=1,
                            tool_manifest_digest="a" * 64,
                        )
                        broker = Broker(
                            kernel=_MemKernel(),
                            journal=_MemJournal(),
                            executor=_FileReadExec(),
                            binding=binding,
                            allowed_read_paths=frozenset({"research_note.txt"}),
                        )

                        def real_research_broker_reader(rel_path: str) -> dict:
                            req = ToolRequest.model_validate(
                                {
                                    "protocol": "company-tool/1",
                                    "request_id": str(uuid4()),
                                    "engine_session_id": str(binding.engine_session_id),
                                    "attempt_id": str(binding.attempt_id),
                                    "fencing_epoch": binding.fencing_epoch,
                                    "expected_revision": binding.revision,
                                    "sequence": broker.sequence,
                                    "tool_manifest_digest": binding.tool_manifest_digest,
                                    "call": {
                                        "tool_id": "workspace.read",
                                        "arguments": {"relative_path": rel_path, "max_bytes": 4096},
                                    },
                                }
                            )
                            reply = broker.handle((req.model_dump_json() + "\n").encode("utf-8"), channel="BOUND_ENGINE_STDOUT")
                            if reply.status != "OK":
                                raise PermissionError(reply.error_code or "BROKER_DENIED")
                            return {
                                "relative_path": rel_path,
                                "receipt_id": str(reply.receipt_id),
                                "sha256": research_sha,
                            }

                        def real_spreadsheet_reader(rel_path: str) -> dict:
                            raw = (tmp_root / rel_path).read_bytes()
                            return {
                                "relative_path": rel_path,
                                "format": "xlsx",
                                "sha256": hashlib.sha256(raw).hexdigest(),
                                "receipt_id": str(uuid4()),
                                **_parse_xlsx_summary(raw),
                            }

                        def real_obligation_reader(rel_path: str) -> dict:
                            raw = (tmp_root / rel_path).read_bytes()
                            return {
                                "source": rel_path,
                                "clause_id": "MADDE-12",
                                "sha256": hashlib.sha256(raw).hexdigest(),
                                "receipt_id": str(uuid4()),
                            }

                        runner._source_readers["RESEARCH"] = (real_research_broker_reader, "RESEARCH_BROKER_READER_NOT_CONFIGURED")
                        runner._source_readers["SPREADSHEET"] = (real_spreadsheet_reader, "SPREADSHEET_BROKER_READER_NOT_CONFIGURED")
                        runner._source_readers["OBLIGATION"] = (real_obligation_reader, "OBLIGATION_WEB_READER_NOT_CONFIGURED")

                        for work_type, read_path, expected_sha in (
                            ("RESEARCH", "research_note.txt", research_sha),
                            ("SPREADSHEET", "budget_2026.xlsx", xlsx_sha),
                            ("OBLIGATION", "obligation_2026.html", ob_sha),
                        ):
                            title = f"Broker araçlı {work_type}"
                            page.locator("#office-task-title").fill(title)
                            page.locator("#office-task-work-type").select_option(work_type)
                            page.locator("#office-task-goal").fill(f"{read_path} kaynağını gerçek araç adaptörüyle doğrula.")
                            page.locator("#office-task-read-path").fill(read_path)
                            with page.expect_response(
                                lambda response: response.url.endswith("/api/office-tasks")
                                and response.request.method == "POST"
                            ) as sub_ok:
                                page.locator("#office-task-submit").click()
                            assert sub_ok.value.ok, work_type
                            card = page.locator(".run-card").filter(has_text=title)
                            expect(card.locator(".run-status")).to_have_text("Kabul edildi", timeout=12000)
                            latest = next(r for r in runner.list_runs() if r["title"] == title)
                            assert latest["exec_result"]["broker_read_receipt"]["sha256"] == expected_sha
                            if work_type == "SPREADSHEET":
                                assert latest["exec_result"]["broker_read_receipt"]["cell_count"] == 6
                    assert len(runner.list_runs()) == 6
                    # Verify CEO (MGR-01) auto-delegation & consolidated CEO final report in browser
                    page.locator("#office-task-title").fill("CEO yönetim testi")
                    page.locator("#office-task-work-type").select_option("SOFTWARE")
                    page.locator("#office-task-role").select_option("MGR-01")
                    page.locator("#office-task-read-path").fill("")
                    page.locator("#office-task-goal").fill("CEO hedefi parcalayip uzman ve QA'ya delege etsin.")
                    with page.expect_response(
                        lambda response: response.url.endswith("/api/office-tasks")
                        and response.request.method == "POST"
                    ) as ceo_sub:
                        page.locator("#office-task-submit").click()
                    assert ceo_sub.value.ok
                    ceo_card = page.locator(".run-card").filter(has_text="MGR-01")
                    expect(ceo_card.locator(".run-status")).to_have_text("Kabul edildi", timeout=12000)
                    ceo_card.locator("summary").click()
                    expect(ceo_card.locator(".run-ceo-report")).to_be_visible(timeout=12000)
                    expect(ceo_card.locator(".run-ceo-report")).to_contain_text("CEO (MGR-01) Nihai Özet Raporu")
                    assert len(runner.list_runs()) == 9
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
