import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.workflow_preflight import check_workflow, ROOT
from tools import run_disposable_e2e_workflow as wrapper


class WorkflowPreflightTests(unittest.TestCase):
    def test_preserved_legacy_wiring_is_reported_without_executing_workflow(self):
        result = check_workflow(ROOT / 'evidence/CODEX_WORKFLOW_20261112_BACKUP/tools__disposable_e2e_workflow_trial.py')
        symbols = {row['symbol'] for row in result['findings']}
        self.assertTrue({'LinuxLauncher', 'PipeTransport', 'EnginePump',
                         'EngineReplyGuard', 'PilotSession', 'Broker'} <= symbols)
        self.assertFalse(result['runtime_ready'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_active_canonical_entry_and_adapters_are_checked_without_runtime_approval(self):
        result = check_workflow()
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['status'], 'SOURCE_CALLS_COMPATIBLE')
        self.assertEqual(len(result['scanned_files']), 10)
        self.assertGreaterEqual(result['checked_calls'], 5)
        self.assertFalse(result['runtime_ready'])

    def test_valid_constructor_signature_is_not_runtime_approval(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests/unit') as directory:
            path = Path(directory) / 'fixture.py'
            path.write_text('from company_os.engine_bridge import FrameBuffer\n'
                            'def never_execute():\n    FrameBuffer(max_frame_bytes=1024)\n',
                            encoding='utf-8')
            result = check_workflow(path)
            self.assertEqual(result['status'], 'SOURCE_CALLS_COMPATIBLE')
            self.assertEqual(result['checked_calls'], 1)
            self.assertFalse(result['runtime_ready'])
            self.assertTrue(result['runtime_blockers'])

    def test_wrapper_blocks_before_mount_db_or_any_command(self):
        with patch('subprocess.run', side_effect=AssertionError('no OS command')), \
             patch('builtins.print'):
            self.assertEqual(wrapper.main(), 2)
