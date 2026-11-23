import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from company_os.bootstrap.provisioning import ProvisioningBlocked
from company_os.adapters.secrets.secret_adapter import SecretUnavailable
from company_os.composition.workflow_trust import check_workflow_trust
from tests.unit import test_consent_binding


class WorkflowTrustTests(unittest.TestCase):
    def trial_main(self):
        # Compile only the real entry function. Importing the trial would require
        # psycopg on Windows; none of its DB/OS setup is needed for these guards.
        root = Path(__file__).resolve().parents[2]
        path = root / 'scripts/verification/disposable_e2e_workflow_trial.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        namespace = dict(Path=Path, ROOT=root, __file__=str(path), json=json,
                         CANONICAL_WORKSPACE='fixture-workspace',
                         check_workflow_trust=check_workflow_trust,
                         connect_adapted=Mock(side_effect=AssertionError('no DB connection')))
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace

    def test_entry_requires_external_trust_before_any_db_connection(self):
        namespace = self.trial_main()
        # Even once all signature/runtime blockers are cleared, missing trust
        # or a changed document must stop before connecting to PostgreSQL.
        with patch('scripts.verification.workflow_preflight.check_workflow',
                   return_value={'status': 'SOURCE_CALLS_COMPATIBLE', 'runtime_blockers': []}), \
             patch('builtins.print'):
            self.assertEqual(namespace['main'](), 2)
            with tempfile.TemporaryDirectory() as directory:
                args = self.inputs(Path(directory) / 'consent.json')
                args['consent_sha256'] = '0'*64
                with self.assertRaises(ProvisioningBlocked):
                    namespace['main'](trust_inputs=args)
        namespace['connect_adapted'].assert_not_called()

    def inputs(self, path):
        _, raw, _, record = test_consent_binding.ConsentTests().setup_binding()
        path.write_bytes(raw)
        return dict(consent_path=path, consent_sha256=hashlib.sha256(raw).hexdigest(),
                    human_id=record['actual_human_id'],
                    canonical_workspace='fixture-workspace', root_record=record,
                    secret_directory_fd=42, secret_name='clock_obs.key', secret_owner_uid=999)

    def test_exact_supervisor_inputs_and_no_enrollment_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.inputs(Path(directory) / 'consent.json')
            with patch('company_os.composition.workflow_trust.read_secret_bytes', return_value=b'x'*32) as read:
                consent, secret = check_workflow_trust(**args)
            read.assert_called_once_with(42, 'clock_obs.key', owner_uid=999)
            self.assertTrue(consent.matched)
            self.assertFalse(consent.authority_granted)
            self.assertEqual(consent.independent_identity, 'NOT_VERIFIED')
            self.assertEqual(secret, b'x'*32)

    def test_changed_document_or_binding_never_reads_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'consent.json'
            args = self.inputs(path)
            for change in ({'consent_sha256': '0'*64},
                           {'human_id': args['root_record']['issuer_id']},
                           {'canonical_workspace': 'wrong-workspace'}):
                with self.subTest(change=change), \
                     patch('company_os.composition.workflow_trust.read_secret_bytes') as read:
                    with self.assertRaises(ProvisioningBlocked):
                        check_workflow_trust(**dict(args, **change))
                    read.assert_not_called()
            path.write_bytes(path.read_bytes() + b' ')
            with patch('company_os.composition.workflow_trust.read_secret_bytes') as read:
                with self.assertRaises(ProvisioningBlocked):
                    check_workflow_trust(**args)
                read.assert_not_called()

    def test_path_bypass_and_key_failure_propagate_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.inputs(Path(directory) / 'consent.json')
            with self.assertRaisesRegex(SecretUnavailable, 'ENROLLED_DIRECTORY_DESCRIPTOR_REQUIRED'):
                check_workflow_trust(**dict(args, secret_directory_fd=directory))
            with patch('company_os.composition.workflow_trust.read_secret_bytes',
                       side_effect=SecretUnavailable('ENROLLED_KEY_UNAVAILABLE')) as read:
                with self.assertRaisesRegex(SecretUnavailable, 'ENROLLED_KEY_UNAVAILABLE'):
                    check_workflow_trust(**args)
                self.assertEqual(read.call_count, 1)
