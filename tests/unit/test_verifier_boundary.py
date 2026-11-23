"""Security regressions; source tests never assert real OS isolation."""
import json
import tempfile
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from independent_verifier import verifier_runner as verifier
from company_os.kernel.execution_protocol import Denied

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / 'verifier/public-fixtures/mgt01/check_title.py'


class VerifierBoundaryTests(unittest.TestCase):
    def evaluate(self, source, **limits):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / 'candidate.py'
            candidate.write_text(source, encoding='utf-8')
            with (patch.multiple(verifier, **limits) if limits else nullcontext()):
                return verifier.run_source_title_oracle(candidate, ORACLE)

    def test_runtime_refuses_candidate_before_any_execution(self):
        with patch.object(verifier, 'BoundedCandidate') as launcher:
            with self.assertRaisesRegex(Denied, 'ENROLLED_ISOLATED_VERIFIER_REQUIRED'):
                verifier.run_title_oracle(Path('candidate.py'), ORACLE)
            launcher.assert_not_called()

    def test_source_pass_has_no_acceptance_authority_and_pins_harness(self):
        report = verifier.run_source_title_oracle(
            ROOT / 'verifier/public-fixtures/mgt01/reference_title.py', ORACLE)
        self.assertEqual(report['outcome'], 'PASS')
        self.assertFalse(report['acceptance_eligible'])
        self.assertEqual(report['execution_class'], 'SOURCE_TEST')
        self.assertEqual(report['isolation'], 'NOT_ESTABLISHED')
        self.assertEqual(len(report['runner_sha256']), 64)
        self.assertEqual(len(report['harness_sha256']), 64)

    def test_ready_without_newline_is_cut_off_before_candidate_sleep_ends(self):
        start = time.monotonic()
        report = self.evaluate(
            'import sys,time\nsys.stdout.write("READY");sys.stdout.flush()\ntime.sleep(1.5)\n',
            READY_TIMEOUT_SECONDS=0.1)
        self.assertLess(time.monotonic()-start, 1.0)
        self.assertEqual(report['passed'], 0)

    def test_stderr_flood_and_oversized_unterminated_stdout_are_rejected(self):
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream):
                start = time.monotonic()
                report = self.evaluate(
                    f'import sys,time\nsys.{stream}.write("x"*70000);sys.{stream}.flush()\ntime.sleep(1.5)\n',
                    READY_TIMEOUT_SECONDS=0.2)
                self.assertEqual(report['passed'], 0)
                self.assertLess(time.monotonic()-start, 1.0)

    def test_malformed_json_response_is_fail_closed(self):
        for response in ('[]', 'null', '{"id":"wrong","status":"SUCCESS","value":"x"}'):
            with self.subTest(response=response):
                source = ('import sys,os\nprint("READY",flush=True)\nsys.stdin.readline()\n'
                          f'print({response!r},flush=True)\nos._exit(0)\n')
                self.assertEqual(self.evaluate(source)['passed'], 0)

    def test_case_response_without_newline_is_bounded(self):
        source = ('import sys,time\nprint("READY",flush=True)\nsys.stdin.readline()\n'
                  'sys.stdout.write("{");sys.stdout.flush()\ntime.sleep(1.5)\n')
        start = time.monotonic()
        report = self.evaluate(source, TOTAL_TIMEOUT_SECONDS=0.2)
        self.assertLess(time.monotonic()-start, 1.0)
        self.assertEqual(report['passed'], 0)

    def test_oversized_candidate_is_rejected_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'large.py'
            path.write_bytes(b'#' * 65)
            with patch.object(verifier, 'MAX_CANDIDATE_BYTES', 64), \
                 patch.object(verifier, 'BoundedCandidate') as launcher:
                with self.assertRaisesRegex(Denied, 'VERIFIER_SOURCE_BYTE_LIMIT'):
                    verifier.run_source_title_oracle(path, ORACLE)
                launcher.assert_not_called()

    def test_direct_source_read_attack_cannot_obtain_runtime_acceptance(self):
        # Same-identity SOURCE_TEST intentionally does not claim confidentiality.
        # Keep this exploit executable so sys.path changes cannot "prove" isolation.
        source = '''import sys,json,os,__main__
from pathlib import Path
text=(Path(__main__.__file__).parent/'verifier_runner.py').read_text(encoding='utf-8')
cases=eval(text.split('CASES = ',1)[1].split('EXPECTED_CASE_IDS',1)[0])
print('READY',flush=True)
for line in sys.stdin:
 if line.strip()=='DONE': break
 req=json.loads(line)
 case=next(c for c in cases if type(c[1]) is type(req['value']) and c[1]==req['value'])
 resp={'id':req['id'],'status':'ERROR','error_type':case[3]} if case[3] else {'id':req['id'],'status':'SUCCESS','value':case[2]}
 print(json.dumps(resp),flush=True)
os._exit(0)
'''
        report = self.evaluate(source)
        self.assertEqual(report['passed'], 13)
        self.assertFalse(report['acceptance_eligible'])
        self.assertEqual(report['isolation'], 'NOT_ESTABLISHED')

