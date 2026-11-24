"""Unit tests for local OllamaClient, LiveOfficeTaskRunner, and POST /api/office-tasks."""

from __future__ import annotations

import hashlib
import json
import unittest
from io import BytesIO

from company_os.api.http.app import make_wsgi_app
from company_os.engine.ollama_adapter import OllamaClient, OllamaError, OllamaGenerationResult
from company_os.runtime.live_task_runner import (
    ENGINEER_PILOT_PROMPT,
    ENGINEER_PILOT_VERSION,
    LiveOfficeTaskRunner,
    OfficeTaskValidationError,
    validate_office_task_payload,
)


class _StubOllama:
    def __init__(self, response_text: str, eval_count: int = 42):
        self.response_text = response_text
        self.eval_count = eval_count
        self.calls: list[dict] = []

    def generate(self, prompt: str, *, model: str | None = None, system: str | None = None, temperature: float = 0.2):
        self.calls.append({"prompt": prompt, "model": model, "system": system, "temperature": temperature})
        return OllamaGenerationResult(
            model=model or "qwen2.5-coder:3b",
            response=self.response_text,
            response_sha256=hashlib.sha256(self.response_text.encode("utf-8")).hexdigest(),
            prompt_eval_count=25,
            eval_count=self.eval_count,
            total_duration_ms=120,
        )


class OllamaAdapterTests(unittest.TestCase):
    def test_rejects_non_loopback_base_url(self):
        with self.assertRaises(OllamaError):
            OllamaClient(base_url="https://api.example.com")
        with self.assertRaises(OllamaError):
            OllamaClient(base_url="http://192.168.1.10:11434")

    def test_rejects_empty_prompt(self):
        client = OllamaClient()
        with self.assertRaises(OllamaError):
            client.generate("   ")


class LiveOfficeTaskRunnerTests(unittest.TestCase):
    def test_engineer_pilot_requires_active_matching_catalog_digest(self):
        from unittest.mock import Mock

        stub = _StubOllama("Test çıktısı")
        catalog = Mock()
        entry = {
            "tenant_id": "pilot-tenant",
            "kind": "ROLE",
            "name": "EXP-01",
            "version": ENGINEER_PILOT_VERSION,
            "digest": hashlib.sha256(ENGINEER_PILOT_PROMPT.encode("utf-8")).hexdigest(),
            "active": True,
        }
        runner = LiveOfficeTaskRunner(
            ollama_client=stub,
            registry_tenant_id="pilot-tenant",
            engineer_pilot_catalog=catalog,
        )
        task = {
            "task_id": "pilot-task",
            "title": "Başlık normalizasyonu",
            "goal": "Boş girdiyi koruyan en küçük değişikliği öner.",
            "work_type": "SOFTWARE",
            "role_id": "EXP-01",
        }
        catalog.list_catalog_entries.return_value = [{**entry, "digest": "wrong"}]
        with self.assertRaisesRegex(OfficeTaskValidationError, "CATALOG_PIN"):
            runner._execute_task(task)
        self.assertEqual(stub.calls, [])

        catalog.list_catalog_entries.return_value = [entry]
        result = runner._execute_task(task)
        self.assertEqual(stub.calls[0]["system"], ENGINEER_PILOT_PROMPT)
        self.assertEqual(result["role_profile"]["sha256"], entry["digest"])

    def test_validation_rejects_invalid_fields(self):
        with self.assertRaises(OfficeTaskValidationError):
            validate_office_task_payload({"title": "ab", "goal": "Yeterince uzun bir hedef metni"})
        with self.assertRaises(OfficeTaskValidationError):
            validate_office_task_payload({"title": "Gecerli", "goal": "kisa"})
        with self.assertRaises(OfficeTaskValidationError):
            validate_office_task_payload(
                {"title": "Gecerli", "goal": "Yeterince uzun bir hedef metni", "work_type": "UNKNOWN"}
            )
        with self.assertRaises(OfficeTaskValidationError):
            validate_office_task_payload(
                {"title": "Gecerli", "goal": "Yeterince uzun bir hedef metni", "role_id": "BAD"}
            )

    def test_submit_run_once_accepts_and_emits_events(self):
        stub = _StubOllama("1. Kod incelendi.\n2. Birim testleri ile dogrulandi.\n3. Temiz sonuc hazir.")
        persisted_results = []
        runner = LiveOfficeTaskRunner(
            tenant_id="t1",
            ollama_client=stub,  # type: ignore[arg-type]
            persist_result=lambda rec: persisted_results.append(rec.state),
            poll_interval_seconds=0.0,
        )
        submitted = runner.submit_task(
            {
                "title": "Baslik normalizasyonu analizi",
                "goal": "Baslik normalizasyonu icin adimlari ve test planini cikar.",
                "work_type": "RESEARCH",
                "role_id": "EXP-02",
                "acceptance_criteria": ["En az 2 somut adim icermeli"],
            }
        )
        self.assertEqual(submitted["state"], "QUEUED")
        summary = runner.run_once()
        self.assertIsNotNone(summary)
        self.assertEqual(summary.outcome, "ACCEPTED")
        self.assertEqual(persisted_results, ["ACCEPTED"])
        runs = runner.list_runs()
        self.assertEqual(runs[0]["state"], "ACCEPTED")
        self.assertEqual(runs[0]["verification"]["verified_by"], "INDEPENDENT_LOCAL_VERIFIER")
        event_kinds = [ev.event_type for ev in runner.recent_events()]
        self.assertEqual(event_kinds, ["OfficeTaskQueued", "WorkerTaskClaimed", "WorkerTaskAccepted"])

    def test_short_model_output_is_rejected_by_independent_verifier(self):
        stub = _StubOllama("kisa", eval_count=2)
        runner = LiveOfficeTaskRunner(ollama_client=stub, poll_interval_seconds=0.0)  # type: ignore[arg-type]
        runner.submit_task(
            {
                "title": "Kisa cikti red testi",
                "goal": "Dogrulayici kisa ciktiyi reddetmelidir.",
                "work_type": "SOFTWARE",
                "role_id": "EXP-01",
            }
        )
        summary = runner.run_once()
        self.assertEqual(summary.outcome, "REJECTED")
        self.assertEqual(runner.list_runs()[0]["state"], "REJECTED")

    def test_permission_error_during_persistence_does_not_enqueue(self):
        def _deny(_spec, _bearer):
            raise PermissionError("OWNER_SESSION_TOKEN_REQUIRED")

        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("Yeterince uzun bir yanit metni."),  # type: ignore[arg-type]
            persist_submission=_deny,
        )
        with self.assertRaises(PermissionError):
            runner.submit_task(
                {"title": "Yetkisiz istek", "goal": "Yetkisiz istek kuyruga girmemelidir."}
            )
        self.assertEqual(runner.list_runs(), [])


class OfficeTasksWsgiTests(unittest.TestCase):
    def _call(self, app, method: str, path: str, *, body: bytes = b"", headers: dict[str, str] | None = None):
        status_box = []

        def start_response(status, resp_headers):
            status_box.append((status, dict(resp_headers)))

        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": BytesIO(body),
            "HTTP_HOST": "127.0.0.1:8765",
        }
        for k, v in (headers or {}).items():
            env[k] = v
        out = b"".join(app(env, start_response))
        return status_box[0][0], out

    def test_readonly_app_still_rejects_post_office_tasks_with_405(self):
        app = make_wsgi_app()
        st, _ = self._call(app, "POST", "/api/office-tasks", body=b"{}")
        self.assertTrue(st.startswith("405"))

    def test_office_tasks_post_origin_and_success_flow(self):
        received = {}
        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("Detayli ve dogrulanabilir ajan yaniti hazirlandi."),  # type: ignore[arg-type]
            persist_submission=lambda spec, bearer: (
                received.update({"bearer": bearer, "title": spec["title"]})
                or {"persisted": bool(bearer), "mode": "TEST"}
            ),
        )
        app = make_wsgi_app(
            office_task_submitter=lambda payload, bearer: runner.submit_task(payload, bearer_token=bearer),
            office_tasks_provider=runner.list_runs,
        )

        # Foreign origin rejected
        st_bad, _ = self._call(
            app,
            "POST",
            "/api/office-tasks",
            body=b"{}",
            headers={"CONTENT_TYPE": "application/json", "HTTP_ORIGIN": "https://evil.example"},
        )
        self.assertTrue(st_bad.startswith("403"))

        # Valid submission succeeds
        payload = json.dumps(
            {
                "title": "Canli ofis gorevi",
                "goal": "Ofis ekranindan gonderilen gorevin kuyruga alinmasi.",
                "work_type": "SOFTWARE",
                "role_id": "EXP-01",
            }
        ).encode("utf-8")
        st_ok, body_ok = self._call(
            app,
            "POST",
            "/api/office-tasks",
            body=payload,
            headers={
                "CONTENT_TYPE": "application/json",
                "HTTP_ORIGIN": "http://127.0.0.1:8765",
                "HTTP_AUTHORIZATION": "Bearer test-session-token",
            },
        )
        self.assertTrue(st_ok.startswith("201"))
        data = json.loads(body_ok)
        self.assertEqual(data["status"], "QUEUED")
        self.assertEqual(received["bearer"], "test-session-token")

        # GET /api/office-tasks lists the queued task
        st_list, body_list = self._call(app, "GET", "/api/office-tasks")
        self.assertTrue(st_list.startswith("200"))
        self.assertEqual(len(json.loads(body_list)["runs"]), 1)

    def test_research_task_with_broker_read_path_and_queue_runner(self) -> None:
        from company_os.workflows.queue_adapter import MultiWorkTypeQueueRunner
        from company_os.workflows.templates import WorkType

        queue_runner = MultiWorkTypeQueueRunner(
            executors={
                WorkType.RESEARCH: lambda t: {
                    "summary": "Araştırma özeti",
                    "citations": [{"uri": "https://example.org/doc"}],
                    "read_path": t.get("read_path"),
                }
            },
            allowed_read_paths=frozenset({"task_title.py"}),
        )
        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("Araştırma sonucu Broker üzerinden doğrulandı ve özetlendi."),
            queue_runner=queue_runner,
            research_broker_reader=lambda path: {"relative_path": path, "sha256": "abc123"},
        )
        submitted = runner.submit_task(
            {
                "title": "Araştırma Broker okuma testi",
                "goal": "task_title.py dosyasını Broker üzerinden okuyup özetle.",
                "work_type": "RESEARCH",
                "role_id": "EXP-02",
                "read_path": "task_title.py",
            }
        )
        run_result = runner.run_once()
        self.assertIsNotNone(run_result)
        items = runner.list_runs()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["task_id"], submitted["task_id"])
        self.assertEqual(items[0]["state"], "ACCEPTED")
        self.assertEqual(
            items[0]["exec_result"]["broker_read_receipt"],
            {"relative_path": "task_title.py", "sha256": "abc123"},
        )

    def test_spreadsheet_and_obligation_broker_readers(self) -> None:
        from company_os.workflows.queue_adapter import MultiWorkTypeQueueRunner
        from company_os.workflows.templates import WorkType

        queue_runner = MultiWorkTypeQueueRunner(
            executors={
                WorkType.SPREADSHEET: lambda t: {
                    "post_commit_verified": True,
                    "sheet_digest": "sha256:sheet1",
                    "read_path": t.get("read_path"),
                },
                WorkType.OBLIGATION: lambda t: {
                    "uncertainty": 0.1,
                    "checklist": ["ok"],
                    "read_path": t.get("read_path"),
                },
            },
            allowed_read_paths=frozenset({"budget.xlsx"}),
        )
        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("Tablo ve yükümlülük çıktısı Broker üzerinden doğrulandı."),
            queue_runner=queue_runner,
            spreadsheet_broker_reader=lambda path: {"relative_path": path, "sheet_digest": "sha256:sheet1"},
            obligation_web_reader=lambda path: {"source": path, "uncertainty": 0.1},
        )
        t1 = runner.submit_task(
            {
                "title": "Tablo Broker testi",
                "goal": "budget.xlsx dosyasını Broker üzerinden okuyup özetle.",
                "work_type": "SPREADSHEET",
                "role_id": "EXP-01",
                "read_path": "budget.xlsx",
            }
        )
        t2 = runner.submit_task(
            {
                "title": "Yükümlülük Web/Broker testi",
                "goal": "reg_2026.html kaynağını okuyup yükümlülükleri listele.",
                "work_type": "OBLIGATION",
                "role_id": "EXP-02",
                "read_path": "reg_2026.html",
            }
        )
        runner.run_once()
        runner.run_once()
        runs = {r["task_id"]: r for r in runner.list_runs()}
        self.assertEqual(runs[t1["task_id"]]["state"], "ACCEPTED")
        self.assertEqual(
            runs[t1["task_id"]]["exec_result"]["broker_read_receipt"],
            {"relative_path": "budget.xlsx", "sheet_digest": "sha256:sheet1"},
        )
        self.assertEqual(runs[t2["task_id"]]["state"], "ACCEPTED")
        self.assertEqual(
            runs[t2["task_id"]]["exec_result"]["broker_read_receipt"],
            {"source": "reg_2026.html", "uncertainty": 0.1},
        )


if __name__ == "__main__":
    unittest.main()
