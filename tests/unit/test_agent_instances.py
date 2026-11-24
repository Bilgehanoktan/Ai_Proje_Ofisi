"""Unit tests for canonical AgentInstance registry, retry superseding, staleness, and HTTP auth."""

from __future__ import annotations

import hashlib
import json
import unittest
from io import BytesIO
from uuid import uuid4

from company_os.api.http.app import make_wsgi_app
from company_os.engine.ollama_adapter import OllamaGenerationResult
from company_os.runtime.agent_instances import AgentInstanceRegistry, AgentState
from company_os.runtime.live_task_runner import LiveOfficeTaskRunner

TENANT_A = "b7a6faa0-895f-4bdc-8cf7-e4b2c6501d73"
PROJECT_A = "37434287-b083-46ef-97fd-7577ee394509"
PROJECT_B = "99999999-9999-4999-8999-999999999999"


class _FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


class _StubOllama:
    def generate(self, prompt: str, *, model=None, system=None, temperature: float = 0.2):
        text = "1. Gorev tamamlandi.\n2. Kanit ve dogrulama hazirlandi."
        return OllamaGenerationResult(
            model=model or "qwen2.5-coder:3b",
            response=text,
            response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            prompt_eval_count=15,
            eval_count=28,
            total_duration_ms=80,
        )


class AgentInstanceRegistryTests(unittest.TestCase):
    def test_two_agents_same_role_and_retry_supersedes_old_attempt(self):
        clock = _FakeClock()
        reg = AgentInstanceRegistry(clock=clock, stale_after_seconds=60.0)
        e1 = reg.register_agent(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            role_id="EXP-01",
            display_name="Engineer #1",
            worker_principal="worker-eng-01",
        )
        e2 = reg.register_agent(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            role_id="EXP-01",
            display_name="Engineer #2",
            worker_principal="worker-eng-02",
        )
        self.assertNotEqual(e1["agent_instance_id"], e2["agent_instance_id"])

        att1 = str(uuid4())
        att2 = str(uuid4())
        reg.assign_task(
            agent_instance_id=e1["agent_instance_id"],
            task_id="task-42",
            attempt_id=att1,
            task_title="MGT-01",
        )
        # Retry same task on Engineer #2 -> Engineer #1 must be superseded (IDLE, no active task)
        reg.assign_task(
            agent_instance_id=e2["agent_instance_id"],
            task_id="task-42",
            attempt_id=att2,
            task_title="MGT-01 (retry)",
        )

        items = reg.list_authorized(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            allowed_tenant_id=TENANT_A,
            allowed_project_ids=frozenset({PROJECT_A}),
        )
        by_id = {x["agent_instance_id"]: x for x in items}
        self.assertEqual(by_id[e1["agent_instance_id"]]["state"], "IDLE")
        self.assertIsNone(by_id[e1["agent_instance_id"]]["active_task_id"])
        self.assertIsNone(by_id[e1["agent_instance_id"]]["active_attempt_id"])

        self.assertEqual(by_id[e2["agent_instance_id"]]["state"], "RUNNING")
        self.assertEqual(by_id[e2["agent_instance_id"]]["active_task_id"], "task-42")
        self.assertEqual(by_id[e2["agent_instance_id"]]["active_attempt_id"], att2)

        # Stale attempt release is rejected
        with self.assertRaises(ValueError):
            reg.release_task(agent_instance_id=e1["agent_instance_id"], attempt_id=att1)

        # Current attempt release returns Engineer #2 to IDLE
        released = reg.release_task(agent_instance_id=e2["agent_instance_id"], attempt_id=att2)
        self.assertEqual(released["state"], "IDLE")
        self.assertIsNone(released["active_task_id"])

    def test_stale_agent_hides_active_task_and_marks_stale(self):
        clock = _FakeClock(100.0)
        reg = AgentInstanceRegistry(clock=clock, stale_after_seconds=30.0)
        a1 = reg.register_agent(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            role_id="EXP-02",
            display_name="Research #1",
            worker_principal="worker-res-01",
        )
        reg.assign_task(agent_instance_id=a1["agent_instance_id"], task_id="task-9", task_title="Arastirma")

        clock.now = 145.0  # past stale_after_seconds
        items = reg.list_authorized(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            allowed_tenant_id=TENANT_A,
            allowed_project_ids=frozenset({PROJECT_A}),
        )
        self.assertEqual(items[0]["state"], AgentState.STALE.value)
        self.assertIsNone(items[0]["active_task_id"])

    def test_http_agent_instances_enforces_scope_and_runner_lifecycle(self):
        reg = AgentInstanceRegistry()
        a1 = reg.register_agent(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            role_id="EXP-01",
            display_name="Engineer #1",
            worker_principal="worker-eng-01",
        )
        runner = LiveOfficeTaskRunner(
            tenant_id="t1",
            ollama_client=_StubOllama(),  # type: ignore[arg-type]
            agent_registry=reg,
            registry_tenant_id=TENANT_A,
            project_id=PROJECT_A,
            poll_interval_seconds=0.0,
        )
        runner.submit_task(
            {
                "title": "AgentInstance bag testi",
                "goal": "Gorev kosulurken AgentInstance baglanip sonra bosaltilmalidir.",
                "work_type": "SOFTWARE",
                "role_id": "EXP-01",
            }
        )
        summary = runner.run_once()
        self.assertEqual(summary.outcome, "ACCEPTED")
        self.assertEqual(runner.list_runs()[0]["agent_instance_id"], a1["agent_instance_id"])
        ev_types = [ev.event_type for ev in runner.recent_events()]
        self.assertIn("AgentInstanceAssigned", ev_types)
        self.assertIn("AgentInstanceReleased", ev_types)

        app = make_wsgi_app(
            agent_instances_provider=lambda tid, pid: reg.list_authorized(
                tenant_id=tid,
                project_id=pid,
                allowed_tenant_id=TENANT_A,
                allowed_project_ids=frozenset({PROJECT_A}),
            )
        )

        def call_get(query: str):
            box = []
            body = b"".join(
                app(
                    {
                        "REQUEST_METHOD": "GET",
                        "PATH_INFO": "/api/agent-instances",
                        "QUERY_STRING": query,
                        "wsgi.input": BytesIO(),
                    },
                    lambda st, hdrs: box.append((st, hdrs)),
                )
            )
            return box[0][0], json.loads(body.decode("utf-8"))

        # Missing params -> 400
        st_missing, _ = call_get(f"tenant_id={TENANT_A}")
        self.assertTrue(st_missing.startswith("400"))

        # Foreign project -> 403
        st_foreign, _ = call_get(f"tenant_id={TENANT_A}&project_id={PROJECT_B}")
        self.assertTrue(st_foreign.startswith("403"))

        # Authorized scope -> 200
        st_ok, data_ok = call_get(f"tenant_id={TENANT_A}&project_id={PROJECT_A}")
        self.assertTrue(st_ok.startswith("200"))
        self.assertEqual(len(data_ok["agent_instances"]), 1)
        self.assertEqual(data_ok["agent_instances"][0]["state"], "IDLE")


if __name__ == "__main__":
    unittest.main()
