"""Unit tests for local OllamaClient, LiveOfficeTaskRunner, and POST /api/office-tasks."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from company_os.api.http.app import make_wsgi_app
from company_os.engine.ollama_adapter import OllamaClient, OllamaError, OllamaGenerationResult
from company_os.runtime.live_task_runner import (
    ENGINEER_PILOT_PROMPT,
    ENGINEER_PILOT_VERSION,
    LiveOfficeTaskRunner,
    OfficeTaskValidationError,
    validate_office_task_payload,
    verify_office_task_output,
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
    def test_persisted_read_uses_kernel_attempt_for_independent_confirmation(self):
        seen = []

        def read(scope):
            seen.append(scope)
            return {"attempt_id": "native-attempt", "receipt_id": "native-receipt",
                    "relative_path": scope["read_path"], "sha256": "1" * 64}

        def confirm(scope, receipt):
            return scope == {**seen[0], "attempt_id": "native-attempt"} and receipt == "native-receipt"

        runner = LiveOfficeTaskRunner(
            ollama_client=_StubOllama("Kapsamlı görev için örnek araştırma çıktısı."),
            persist_submission=lambda spec, token: {"persisted": True, "task_id": "native-task"},
            registry_tenant_id="native-tenant", project_id="native-project",
            kernel_research_read=read, research_receipt_readback=confirm,
        )
        runner.submit_task({"work_type": "RESEARCH", "role_id": "EXP-02",
                            "title": "Kaynak doğrulama", "goal": "Kaynak makbuzunu kontrol et.",
                            "read_path": "task_title.py"})
        runner.run_once()
        result = runner.list_runs()[0]
        self.assertEqual(result["state"], "ACCEPTED")
        self.assertEqual(result["attempt_id"], "native-attempt")
        self.assertEqual(seen, [{"tenant_id": "native-tenant", "project_id": "native-project",
                                 "task_id": "native-task", "read_path": "task_title.py"}])

    def test_persisted_research_acceptance_requires_confirmed_receipt(self):
        task = {
            "tenant_id": "tenant-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "work_type": "RESEARCH",
            "read_path": "research_note.txt",
            "db_persisted": True,
        }
        result = {"broker_read_receipt": {"receipt_id": "receipt-1"}}
        for confirms in (False, True):
            with self.subTest(confirms=confirms):
                calls = []

                def readback(scope, receipt_id):
                    calls.append((scope, receipt_id))
                    return confirms

                runner = LiveOfficeTaskRunner(
                    persist_submission=lambda payload, bearer: {},
                    project_id="project-1",
                    verifier=lambda submitted, output: {"accepted": True},
                    research_receipt_readback=readback,
                )
                verdict = runner._verify_task(task, result)
                self.assertIs(verdict["accepted"], confirms)
                expected_scope = {
                    key: task[key] for key in ("tenant_id", "task_id", "attempt_id", "read_path")
                }
                expected_scope["project_id"] = "project-1"
                self.assertEqual(calls, [(expected_scope, "receipt-1")])

    def test_research_receipt_must_match_requested_file(self):
        task = {"work_type": "RESEARCH", "read_path": "research_note.txt"}
        response = "Araştırmanın beklenen örnek çıktısı."
        result = {
            "response": response,
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "eval_count": 1,
        }
        for receipt in ({}, {"relative_path": "other_note.txt"}, {"source": task["read_path"]}):
            with self.subTest(receipt=receipt):
                verdict = verify_office_task_output(task, dict(result, broker_read_receipt=receipt))
                self.assertFalse(verdict["accepted"])
                self.assertEqual(verdict["reason"], "FAILED_BROKER_READ_RECEIPT_SOURCE_MATCH")
        verdict = verify_office_task_output(
            task, dict(result, broker_read_receipt={"relative_path": task["read_path"]})
        )
        self.assertTrue(verdict["accepted"])

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

    def test_research_real_tool_broker_read_and_out_of_scope_denial(self) -> None:
        import json
        import tempfile
        from contextlib import contextmanager
        from pathlib import Path
        from uuid import uuid4
        from company_os.broker.tool_broker import Broker

        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_file = Path(tmpdir) / "research_note.txt"
            allowed_content = b"Sentetik RESEARCH bulgusu: MADDE-42 dogrulandi.\n"
            allowed_file.write_bytes(allowed_content)
            expected_digest = hashlib.sha256(allowed_content).hexdigest()

            class _InMemoryJournal:
                def __init__(self) -> None:
                    self.reserved: dict[str, dict] = {}

                def reserve(self, key: str, payload: dict) -> None:
                    self.reserved[key] = payload

            class _InMemoryKernel:
                def __init__(self) -> None:
                    self.receipt_id = uuid4()

                def consume(self, request, *, frame_digest: str, frame: bytes) -> dict:
                    return {
                        "effect_permitted": True,
                        "frame_digest": frame_digest,
                        "consume_id": str(uuid4()),
                    }

                @contextmanager
                def effect_scope(self, consume_id, request, *, frame_digest: str):
                    receipt_id = self.receipt_id

                    class _Tx:
                        def complete(self_tx, c_id, result):
                            return {
                                "status": "SUCCEEDED",
                                "consume_id": str(c_id),
                                "frame_digest": frame_digest,
                                "receipt_id": str(receipt_id),
                                "artifact_ids": [],
                            }

                    yield _Tx()

            class _SyntheticReadExecutor:
                def execute(self, call, *, transaction):
                    raw = (Path(tmpdir) / call.arguments.relative_path).read_bytes()
                    return {
                        "kind": "READ",
                        "content_digest": hashlib.sha256(raw).hexdigest(),
                        "bytes_read": len(raw),
                    }

            from packages.contracts.execution import EngineBinding, ToolRequest

            binding_obj = EngineBinding(
                engine_session_id=uuid4(),
                attempt_id=uuid4(),
                fencing_epoch=1,
                revision=1,
                tool_manifest_digest="a" * 64,
            )

            broker = Broker(
                kernel=_InMemoryKernel(),
                journal=_InMemoryJournal(),
                executor=_SyntheticReadExecutor(),
                binding=binding_obj,
                allowed_read_paths=frozenset({"research_note.txt"}),
            )

            def broker_reader(relative_path: str) -> dict:
                req = ToolRequest.model_validate(
                    {
                        "protocol": "company-tool/1",
                        "request_id": str(uuid4()),
                        "engine_session_id": str(binding_obj.engine_session_id),
                        "attempt_id": str(binding_obj.attempt_id),
                        "fencing_epoch": binding_obj.fencing_epoch,
                        "expected_revision": binding_obj.revision,
                        "sequence": broker.sequence,
                        "tool_manifest_digest": binding_obj.tool_manifest_digest,
                        "call": {
                            "tool_id": "workspace.read",
                            "arguments": {"relative_path": relative_path, "max_bytes": 4096},
                        },
                    }
                )
                frame = (req.model_dump_json() + "\n").encode("utf-8")
                reply = broker.handle(frame, channel="BOUND_ENGINE_STDOUT")
                if reply.status != "OK":
                    raise PermissionError(reply.error_code or "BROKER_DENIED")
                return {
                    "relative_path": relative_path,
                    "receipt_id": str(reply.receipt_id),
                    "content_digest": expected_digest,
                }

            runner = LiveOfficeTaskRunner(
                ollama_client=_StubOllama("MADDE-42 sentetik araştırma dosyası doğrulandı."),
                research_broker_reader=broker_reader,
            )
            ok_task = runner.submit_task(
                {
                    "title": "Sentetik RESEARCH Broker okuma",
                    "goal": "research_note.txt dosyasını Broker üzerinden oku.",
                    "work_type": "RESEARCH",
                    "role_id": "EXP-02",
                    "read_path": "research_note.txt",
                }
            )
            runner.run_once()
            runs = {r["task_id"]: r for r in runner.list_runs()}
            self.assertEqual(runs[ok_task["task_id"]]["state"], "ACCEPTED", runs[ok_task["task_id"]].get("error"))
            self.assertEqual(
                runs[ok_task["task_id"]]["exec_result"]["broker_read_receipt"]["content_digest"],
                expected_digest,
            )

            with self.assertRaises(PermissionError) as ctx:
                broker_reader("secret.txt")
            self.assertEqual(str(ctx.exception), "PILOT_PATH_OUT_OF_SCOPE")
            self.assertTrue(broker.halted)

    def test_spreadsheet_and_obligation_synthetic_validation_and_denial(self) -> None:
        import csv
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            sheet_path = Path(tmpdir) / "budget_2026.csv"
            sheet_path.write_text("kalem,tutar\nLisans,1200\nSunucu,800\n", encoding="utf-8")
            corrupt_path = Path(tmpdir) / "corrupt.csv"
            corrupt_path.write_text("kalem,tutar\nLisans,NOT_A_NUMBER\n", encoding="utf-8")

            obligation_path = Path(tmpdir) / "reg_2026.txt"
            obligation_path.write_text("MADDE-7: Aylik yedekleme raporu saklanir.\n", encoding="utf-8")

            def spreadsheet_reader(relative_path: str) -> dict:
                target = Path(tmpdir) / relative_path
                if not target.exists():
                    raise FileNotFoundError("SHEET_NOT_FOUND")
                total = 0
                with target.open("r", encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        total += int(row["tutar"])
                return {
                    "relative_path": relative_path,
                    "formula_result": total,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }

            def obligation_reader(relative_path: str) -> dict:
                allowed = {"reg_2026.txt"}
                if relative_path not in allowed:
                    raise PermissionError("OBLIGATION_SOURCE_OUT_OF_SCOPE")
                text = (Path(tmpdir) / relative_path).read_text(encoding="utf-8")
                if "MADDE-7:" not in text:
                    raise ValueError("OBLIGATION_CLAUSE_MISSING")
                return {
                    "source": relative_path,
                    "clause_id": "MADDE-7",
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }

            runner = LiveOfficeTaskRunner(
                ollama_client=_StubOllama("Sentetik tablo ve yükümlülük çıktısı doğrulandı."),
                spreadsheet_broker_reader=spreadsheet_reader,
                obligation_web_reader=obligation_reader,
            )
            t_sheet = runner.submit_task(
                {
                    "title": "Sentetik SPREADSHEET doğrulama",
                    "goal": "budget_2026.csv toplam tutarını hesapla.",
                    "work_type": "SPREADSHEET",
                    "role_id": "EXP-01",
                    "read_path": "budget_2026.csv",
                }
            )
            t_ob = runner.submit_task(
                {
                    "title": "Sentetik OBLIGATION doğrulama",
                    "goal": "reg_2026.txt MADDE-7 yükümlülüğünü çıkar.",
                    "work_type": "OBLIGATION",
                    "role_id": "EXP-02",
                    "read_path": "reg_2026.txt",
                }
            )
            runner.run_once()
            runner.run_once()
            runs = {r["task_id"]: r for r in runner.list_runs()}
            self.assertEqual(runs[t_sheet["task_id"]]["state"], "ACCEPTED")
            self.assertEqual(
                runs[t_sheet["task_id"]]["exec_result"]["broker_read_receipt"]["formula_result"],
                2000,
            )
            self.assertEqual(runs[t_ob["task_id"]]["state"], "ACCEPTED")
            self.assertEqual(
                runs[t_ob["task_id"]]["exec_result"]["broker_read_receipt"]["clause_id"],
                "MADDE-7",
            )

            with self.assertRaises(ValueError):
                spreadsheet_reader("corrupt.csv")
            with self.assertRaises(PermissionError) as ctx:
                obligation_reader("unauthorized_reg.txt")
            self.assertEqual(str(ctx.exception), "OBLIGATION_SOURCE_OUT_OF_SCOPE")

    def test_multi_file_patch_regression_enforces_scope_and_atomicity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "b.py").write_text("y = 2\n", encoding="utf-8")
            allowed = frozenset({"a.py", "b.py"})

            def apply_multi_file_patch(patches: list[tuple[str, str]]) -> dict[str, str]:
                resolved_targets: list[tuple[str, Path, str]] = []
                for rel_path, new_content in patches:
                    norm = rel_path.replace("\\", "/").lstrip("/")
                    if norm not in allowed:
                        raise PermissionError(f"PATCH_SCOPE_DENIED:{norm}")
                    target = (root / norm).resolve()
                    if root not in target.parents:
                        raise ValueError(f"PATCH_PATH_ESCAPE:{norm}")
                    resolved_targets.append((norm, target, new_content))
                digests: dict[str, str] = {}
                for norm, target, new_content in resolved_targets:
                    target.write_text(new_content, encoding="utf-8")
                    digests[norm] = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
                return digests

            result = apply_multi_file_patch([("a.py", "x = 10\n"), ("b.py", "y = 20\n")])
            self.assertEqual(len(result), 2)
            self.assertEqual((root / "a.py").read_text(encoding="utf-8"), "x = 10\n")
            self.assertEqual((root / "b.py").read_text(encoding="utf-8"), "y = 20\n")
            with self.assertRaises(PermissionError):
                apply_multi_file_patch([("a.py", "x = 99\n"), ("../outside.py", "bad\n")])
            self.assertEqual((root / "a.py").read_text(encoding="utf-8"), "x = 10\n")


if __name__ == "__main__":
    unittest.main()
