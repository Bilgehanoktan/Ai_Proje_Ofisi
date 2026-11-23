import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from company_os.projections.progress import load_progress, render_progress_html, render_markdown, ROOT


class ProgressTests(unittest.TestCase):
    def test_full_architecture_and_evidence_references_are_preserved(self):
        data=load_progress()
        self.assertEqual({m for a in data['areas'] for m in a['modules']},
                         {f'MOD-{i:03}' for i in range(1,17)})
        for area in data['areas']:
            for evidence in area['evidence']:
                self.assertTrue((ROOT/evidence).is_file(),evidence)
            self.assertIn(area['real_acceptance'],{'NOT_VERIFIED','ACCEPTED_BY_HUMAN_20261123'})
        self.assertEqual((ROOT/'progress/ILERLEME_TABLOSU.md').read_text('utf-8'),render_markdown())

    def test_progress_is_escaped_and_does_not_infer_completion(self):
        data=copy.deepcopy(load_progress())
        data['areas'][0]['ready']='<script>alert(1)</script>'
        with patch('company_os.projections.progress.load_progress',return_value=data):
            rendered=render_progress_html()
        self.assertIn('&lt;script&gt;',rendered)
        self.assertNotIn('<script>alert',rendered)
        self.assertIn('Yüzdeler kaba geliştirme tahminidir',rendered)
        self.assertIn('İlk gerçek iş akışının kabulü: %100 (13/13)',rendered)
