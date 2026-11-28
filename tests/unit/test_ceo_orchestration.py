"""Unit tests for MGR-01 CEO dynamic pilot role selection, auto-revision, and decision report."""

from __future__ import annotations

import unittest

from company_os.runtime.live_task_runner import LiveOfficeTaskRunner, OfficeTaskRecord


class CeoOrchestrationTests(unittest.TestCase):
    def test_select_ceo_pilot_role_by_intent(self) -> None:
        self.assertEqual(
            LiveOfficeTaskRunner._select_ceo_pilot_role("Güvenlik denetimi", "RLS kontrolü"),
            "SEC-QA-AUDITOR-01",
        )
        self.assertEqual(
            LiveOfficeTaskRunner._select_ceo_pilot_role("Kod inceleme", "Patch review"),
            "CODE-REVIEWER-01",
        )
        self.assertEqual(
            LiveOfficeTaskRunner._select_ceo_pilot_role("Dokümantasyon", "README kılavuzu"),
            "TECH-WRITER-01",
        )
        self.assertIsNone(LiveOfficeTaskRunner._select_ceo_pilot_role("Genel iş", "Basit hesaplama"))

    def test_auto_revision_and_structured_decision_report(self) -> None:
        runner = LiveOfficeTaskRunner(ollama_client=None)
        parent = OfficeTaskRecord(
            task_id="ceo-1",
            tenant_id="tenant-1",
            title="Sistem Kontrolü",
            goal="Güvenlik ve kalite kontrolü",
            work_type="SOFTWARE",
            role_id="MGR-01",
            acceptance_criteria=["Kabul ölçütü sağlanmalı"],
            model="qwen2.5-coder:3b",
            state="ACCEPTED",
            delegated_task_ids=["c-1", "c-2"],
        )
        c1 = OfficeTaskRecord(
            task_id="c-1",
            tenant_id="tenant-1",
            title="[CEO→EXP-01] Sistem Kontrolü",
            goal="Uygulama",
            work_type="SOFTWARE",
            role_id="EXP-01",
            acceptance_criteria=["Kabul ölçütü sağlanmalı"],
            model="qwen2.5-coder:3b",
            state="REJECTED",
            parent_task_id="ceo-1",
            verification={"reason": "Eksik kontrol listesi"},
        )
        c2 = OfficeTaskRecord(
            task_id="c-2",
            tenant_id="tenant-1",
            title="[CEO→QA-01] Kalite",
            goal="QA",
            work_type="RESEARCH",
            role_id="QA-01",
            acceptance_criteria=["QA ölçütü sağlanmalı"],
            model="qwen2.5-coder:3b",
            state="ACCEPTED",
            parent_task_id="ceo-1",
            exec_result={"response": "QA kontrol listesi tamamlandı."},
        )
        runner._tasks = {"ceo-1": parent, "c-1": c1, "c-2": c2}

        # First call dispatches 1 auto-revision task and returns None
        first_res = runner._maybe_synthesize_ceo_report("ceo-1")
        self.assertIsNone(first_res)
        self.assertEqual(len(parent.delegated_task_ids), 3)
        rev_id = parent.delegated_task_ids[2]
        rev_task = runner._tasks[rev_id]
        self.assertIn("[CEO→REVİZYON]", rev_task.title)

        # Complete revision task -> structured CEO decision report is synthesized
        rev_task.state = "ACCEPTED"
        rev_task.exec_result = {"response": "Revizyon tamamlandı ve kabul ölçütleri sağlandı."}
        report = runner._maybe_synthesize_ceo_report("ceo-1")
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["synthesized_by"], "MGR-01")
        self.assertIn("Karar:", report["summary"])
        self.assertIn("Sıradaki Adım:", report["summary"])


if __name__ == "__main__":
    unittest.main()
