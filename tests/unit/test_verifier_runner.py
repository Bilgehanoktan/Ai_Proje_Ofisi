import hashlib
import json
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from company_os.kernel.execution_protocol import Denied
from company_os.kernel.kernel_adapters import ProofSigner
from independent_verifier.verifier_runner import IndependentVerificationPipeline, run_source_title_oracle as run_title_oracle
from independent_verifier.verifier_runner import run_title_oracle as run_runtime_title_oracle

ROOT = Path(__file__).resolve().parents[2]
ORACLE_PATH = ROOT / 'verifier/public-fixtures/mgt01/check_title.py'
PRODUCER_FIXTURE = ROOT / 'tests/fixtures/producer/mgt01/task_title.py'
REFERENCE_FIXTURE = ROOT / 'verifier/public-fixtures/mgt01/reference_title.py'


class FakeCursor:
    def __init__(self, conn):
        self.c = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=()):
        self.c.h.calls.append((sql, args))
        self.c.last = sql

    def fetchone(self):
        sql = self.c.last
        if 'r54_context_enter' in sql:
            return ('nonce',)
        if 'r58_emission_snapshot' in sql:
            return ({'project_epoch': 1},)
        if 'r58_attestation_ingest' in sql:
            return ({'command_id': str(uuid4()), 'state': 'SUCCEEDED', 'result_ref': str(uuid4()), 'result_payload': {'ok': True}},)
        if 'r58_verification_final_seal' in sql:
            return ({
                'command_id': str(uuid4()),
                'state': 'SUCCEEDED',
                'result_ref': self.c.h.verification_id,
                'result_payload': {
                    'verification_id': self.c.h.verification_id,
                    'seal_digest': 'c' * 64,
                    'head_digest': 'h' * 64,
                    'patch_id': self.c.h.patch_id,
                },
            },)
        if 'r58_evidence_provenance' in sql:
            return ({
                'command_id': str(uuid4()),
                'state': 'SUCCEEDED',
                'result_ref': self.c.h.evidence_id,
                'result_payload': {
                    'evidence_id': self.c.h.evidence_id,
                    'verification_id': self.c.h.verification_id,
                    'seal_digest': 'c' * 64,
                    'head_digest': 'h' * 64,
                },
            },)
        if 'r58_verification_accept' in sql:
            return ({
                'command_id': str(uuid4()),
                'state': 'SUCCEEDED',
                'result_ref': self.c.h.task_id,
                'result_payload': {
                    'task_id': self.c.h.task_id,
                    'attempt_id': self.c.h.attempt_id,
                    'acceptance_id': self.c.h.acceptance_id,
                    'state': 'ACCEPTED',
                    'task_revision': 3,
                },
            },)
        return ({},)


class FakeConn:
    def __init__(self, h):
        self.h = h
        self.info = SimpleNamespace(transaction_status=0)
        self.last = ''

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class VerifierRunnerTests(unittest.TestCase):
    def test_baseline_fails_5_cases_and_valid_candidate_passes_13(self):
        baseline = run_title_oracle(PRODUCER_FIXTURE, ORACLE_PATH)
        self.assertEqual(baseline['outcome'], 'FAIL')
        self.assertEqual(baseline['passed'], 8)
        self.assertEqual(baseline['total'], 13)

        valid = run_title_oracle(REFERENCE_FIXTURE, ORACLE_PATH)
        self.assertEqual(valid['outcome'], 'PASS')
        self.assertEqual(valid['passed'], 13)
        self.assertEqual(valid['total'], 13)

    def test_mutant_is_rejected_by_pipeline(self):
        root = Path(__file__).resolve().parent / 'test-tmp'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            mutant = Path(tmp) / 'task_title.py'
            mutant.write_text(
                'def normalize_title(v):\n    return "ok"\n',
                encoding='utf-8',
            )
            rep = run_title_oracle(mutant, ORACLE_PATH)
            self.assertEqual(rep['outcome'], 'FAIL')

    def test_forged_exit_code_and_forged_output_rejected(self):
        root = Path(__file__).resolve().parent / 'test-tmp'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            tmp_path = Path(tmp)
            cand = tmp_path / 'cand.py'
            cand.write_text('# no normalize_title\n', encoding='utf-8')

            # 1. Mutant/forged oracle exiting with 7 despite outputting PASS
            forged_oracle = tmp_path / 'forged_oracle.py'
            forged_oracle.write_text(
                'import json, os, sys\n'
                'checks = [{"id": f"c{i}", "result": "PASS"} for i in range(13)]\n'
                'sys.stdout.write(json.dumps({"checks": checks}))\n'
                'sys.stdout.flush()\n'
                'os._exit(7)\n',
                encoding='utf-8'
            )
            try:
                run_title_oracle(cand, forged_oracle)
                self.fail("Should have raised Denied")
            except Denied as exc:
                self.assertTrue('UNPINNED_ORACLE_REJECTED' in str(exc) or 'ORACLE_PROCESS_EXIT_MISMATCH' in str(exc) or 'ORACLE_UNKNOWN_OR_INVALID_CASE_ID' in str(exc), f"Unexpected message: {exc}")

            # 2. Forged oracle exiting 0 but with wrong/forged case IDs
            forged_oracle2 = tmp_path / 'forged_oracle2.py'
            forged_oracle2.write_text(
                'import json, sys\n'
                'checks = [{"id": f"forged_{i}", "result": "PASS"} for i in range(13)]\n'
                'print(json.dumps({"checks": checks}))\n'
                'sys.exit(0)\n',
                encoding='utf-8'
            )
            with self.assertRaises(Denied) as ctx:
                run_title_oracle(cand, forged_oracle2)
            self.assertTrue('UNPINNED_ORACLE_REJECTED' in str(ctx.exception) or 'ORACLE_UNKNOWN_OR_INVALID_CASE_ID' in str(ctx.exception))

            # 3. Forged oracle exceeding output byte limit
            forged_oracle3 = tmp_path / 'forged_oracle3.py'
            forged_oracle3.write_text(
                'import json, sys\n'
                'sys.stdout.write("x" * 70000)\n'
                'sys.exit(0)\n',
                encoding='utf-8'
            )
            with self.assertRaises(Denied) as ctx:
                run_title_oracle(cand, forged_oracle3)
            self.assertTrue('UNPINNED_ORACLE_REJECTED' in str(ctx.exception) or 'ORACLE_OUTPUT_LIMIT_EXCEEDED' in str(ctx.exception))

            # 4. F03 False-pass attack regression: Candidate writes forged 13 PASS to stdout and os._exit(0)
            false_pass_cand = tmp_path / 'false_pass_cand.py'
            false_pass_cand.write_text(
                'import os,sys\n'
                'sys.stdout.write(\'{"checks": [{"id": "boundary", "result": "PASS"}, {"id": "collapse", "result": "PASS"}, {"id": "empty", "result": "PASS"}, {"id": "mixed", "result": "PASS"}, {"id": "nbsp", "result": "PASS"}, {"id": "normalized_length", "result": "PASS"}, {"id": "numeric", "result": "PASS"}, {"id": "only_space", "result": "PASS"}, {"id": "plain", "result": "PASS"}, {"id": "too_long", "result": "PASS"}, {"id": "trim", "result": "PASS"}, {"id": "unicode", "result": "PASS"}, {"id": "wrong_type", "result": "PASS"}]}\')\n'
                'sys.stdout.flush()\n'
                'os._exit(0)\n',
                encoding='utf-8'
            )
            fp_rep = run_title_oracle(false_pass_cand, ORACLE_PATH)
            self.assertEqual(fp_rep['outcome'], 'FAIL')
            self.assertEqual(fp_rep['passed'], 0)

    def test_independent_pipeline_enforces_distinct_principals_and_seals(self):
        tenant = str(uuid4())
        project = str(uuid4())
        v_id = str(uuid4())
        e_id = str(uuid4())
        v_signer = ProofSigner(issuer_id=v_id, key_id=str(uuid4()), revision=1, key=b'v' * 32, tenant_id=tenant, project_id=project)
        e_signer = ProofSigner(issuer_id=e_id, key_id=str(uuid4()), revision=1, key=b'e' * 32, tenant_id=tenant, project_id=project)
        same_signer = ProofSigner(issuer_id=v_id, key_id=str(uuid4()), revision=1, key=b's' * 32, tenant_id=tenant, project_id=project)
        auth = dict(token='t' * 32, project_id=project, kind='ATTEMPT', resource_id=str(uuid4()), task_id=str(uuid4()), attempt_id=str(uuid4()), fence=1, grant_id=str(uuid4()))

        with self.assertRaises(Denied):
            IndependentVerificationPipeline(
                connect=lambda: None,
                verifier_auth=auth,
                verifier_signer=v_signer,
                evidence_auth=auth,
                evidence_signer=same_signer,
                human_auth=auth,
            )

        self.calls = []
        self.verification_id = str(uuid4())
        self.evidence_id = str(uuid4())
        self.acceptance_id = str(uuid4())
        self.patch_id = str(uuid4())
        self.task_id = str(uuid4())
        self.attempt_id = str(uuid4())

        pipe = IndependentVerificationPipeline(
            connect=lambda: FakeConn(self),
            verifier_auth=auth,
            verifier_signer=v_signer,
            evidence_auth=auth,
            evidence_signer=e_signer,
            human_auth=auth,
        )
        report = run_title_oracle(REFERENCE_FIXTURE, ORACLE_PATH)
        arguments = dict(
            task_id=self.task_id,
            attempt_id=self.attempt_id,
            fence=1,
            expected_task_revision=2,
            patch_id=self.patch_id,
            head_digest='h' * 64,
            profile_digest='p' * 64,
            build_digest='b' * 64,
            acceptance_criteria_digest='a' * 64,
            oracle_report=report,
        )
        with self.assertRaisesRegex(Denied, 'RUNTIME_VERIFICATION_RECEIPT_REQUIRED'):
            pipe.seal_and_accept(**arguments)
        self.assertEqual(self.calls, [])
        # A claimed runtime class alone is still untrusted: no validator, no SQL.
        runtime_fixture = dict(report, execution_class='ACTUAL_RUNTIME', acceptance_eligible=True)
        runtime_fixture['report_digest'] = hashlib.sha256(json.dumps({k:v for k,v in runtime_fixture.items() if k != 'report_digest'}, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        arguments['oracle_report'] = runtime_fixture
        with self.assertRaisesRegex(Denied, 'ENROLLED_VERIFIER_RECEIPT_VALIDATOR_REQUIRED'):
            pipe.seal_and_accept(**arguments)
        self.assertEqual(self.calls, [])
        # Explicit fake-driver validator only tests the native command wiring.
        # It is not an enrolled receipt or runtime isolation acceptance.
        expected_calls = []
        class FakeReceiptValidator:
            def validate(self, report, *, expected):
                expected_calls.append(expected)
                return report is runtime_fixture
        pipe.receipt_validator = FakeReceiptValidator()
        for changed in (dict(runtime_fixture, passed=True),
                        dict(runtime_fixture, checks=[]),
                        dict(runtime_fixture, report_digest='0'*64)):
            arguments['oracle_report'] = changed
            with self.assertRaises(Denied):
                pipe.seal_and_accept(**arguments)
            self.assertEqual(self.calls, [])
        # Even a structurally valid receipt must pass the trusted validator.
        arguments['oracle_report'] = dict(runtime_fixture)
        with self.assertRaisesRegex(Denied, 'VERIFIER_RECEIPT_BINDING_REJECTED'):
            pipe.seal_and_accept(**arguments)
        self.assertEqual(self.calls, [])
        arguments['oracle_report'] = runtime_fixture
        out = pipe.seal_and_accept(**arguments)
        self.assertEqual(expected_calls[-1]['patch_id'], self.patch_id)
        self.assertEqual(out['acceptance']['state'], 'ACCEPTED')
        sql_list = [s for s, _ in self.calls]
        self.assertTrue(any('r58_verification_final_seal' in s for s in sql_list))
        self.assertTrue(any('r58_evidence_provenance' in s for s in sql_list))
        self.assertTrue(any('r58_verification_accept' in s for s in sql_list))

    def test_r2_01_candidate_cannot_impersonate_by_reading_oracle_cases(self):
        root = Path(__file__).resolve().parent / "test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            cand = Path(tmp) / "cand_r2_01.py"
            cand.write_text(
                "import sys,os,json\n"
                "from pathlib import Path\n"
                "import __main__\n"
                "sys.path.insert(0,str(Path(__main__.__file__).resolve().parents[1]))\n"
                "try:\n"
                "    from independent_verifier.verifier_runner import CASES\n"
                "    expected={c[0]:c for c in CASES}\n"
                "except Exception:\n"
                "    expected={}\n"
                "print(\"READY\",flush=True)\n"
                "for line in sys.stdin:\n"
                " if line.strip()==\"DONE\": os._exit(0)\n"
                " req=json.loads(line)\n"
                " if req[\"id\"] in expected:\n"
                "  c=expected[req[\"id\"]]\n"
                "  out={\"status\":\"ERROR\",\"error_type\":c[3]} if c[3] else {\"status\":\"SUCCESS\",\"value\":c[2]}\n"
                " else:\n"
                "  out={\"status\":\"FAIL\",\"value\":\"none\"}\n"
                " print(json.dumps(out,ensure_ascii=False),flush=True)\n"
                "os._exit(0)\n",
                encoding="utf-8",
            )
            rep = run_title_oracle(cand, ORACLE_PATH)
            self.assertEqual(rep["outcome"], "FAIL")
            self.assertEqual(rep["passed"], 0)

    def test_r2_02_unpinned_oracle_is_rejected(self):
        root = Path(__file__).resolve().parent / "test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            unpinned = Path(tmp) / "fake_oracle.py"
            unpinned.write_text("print(\"fake\")\n", encoding="utf-8")
            with self.assertRaises(Denied) as ctx:
                run_title_oracle(REFERENCE_FIXTURE, unpinned)
            self.assertIn("UNPINNED_ORACLE_REJECTED", str(ctx.exception))

    def test_r2_03_ready_timeout_deadline_enforced(self):
        root = Path(__file__).resolve().parent / "test-tmp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            sleepy_cand = Path(tmp) / "sleepy_cand.py"
            sleepy_cand.write_text("import time\ntime.sleep(3.0)\n", encoding="utf-8")
            start = time.monotonic()
            rep = run_title_oracle(sleepy_cand, ORACLE_PATH)
            elapsed = time.monotonic() - start
            self.assertEqual(rep["outcome"], "FAIL")
            self.assertEqual(rep["passed"], 0)
            self.assertLess(elapsed, 4.0)

