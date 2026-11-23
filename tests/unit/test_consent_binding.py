import hashlib
import json
import unittest
import tempfile
from pathlib import Path
from company_os.bootstrap.consent_binding import OwnerConsentBinding, verify_owner_installation_consent
from company_os.bootstrap.provisioning import ProvisioningBlocked
from tests.unit.test_provisioning import fixture


class ConsentTests(unittest.TestCase):
    def setup_binding(self):
        c = {'canonical_workspace': 'fixture-workspace', 'installation_consent': 'EXPLICITLY_GRANTED',
             'source': 'DIRECT_USER_STATEMENT_IN_CURRENT_CHAT', 'statement': 'fixture consent',
             'statement_sha256': hashlib.sha256(b'fixture consent').hexdigest()}
        raw = json.dumps(c).encode()
        digest = hashlib.sha256(raw).hexdigest()
        r = fixture()
        r['r56_human_consent_evidence_digest'] = digest
        b = OwnerConsentBinding(consent_sha256=digest, human_id=r['actual_human_id'], workspace='fixture-workspace')
        return b, raw, c, r

    def test_matching_consent_does_not_authorize_enrollment(self):
        b, raw, c, r = self.setup_binding()
        result = b.check(raw, c, r)
        self.assertFalse(result['enrollment_authorized'])
        self.assertEqual(result['independent_identity'], 'NOT_VERIFIED')
        self.assertFalse(hasattr(b, 'verify_root'))

    def test_changed_bytes_or_wrong_human_rejected(self):
        b, raw, c, r = self.setup_binding()
        with self.assertRaises(ProvisioningBlocked):
            b.check(raw + b' ', c, r)
        r['actual_human_id'] = r['issuer_id']
        with self.assertRaises(ProvisioningBlocked):
            b.check(raw, c, r)

    def test_helper_preserves_human_workspace_pin_and_no_authority_boundary(self):
        _, raw, consent, record = self.setup_binding()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'consent.json'
            path.write_bytes(raw)
            args = dict(expected_human_id=record['actual_human_id'],
                        expected_document_sha256=hashlib.sha256(raw).hexdigest(),
                        expected_workspace='fixture-workspace', root_record=record)
            result = verify_owner_installation_consent(path, **args)
            self.assertTrue(result.matched)
            self.assertFalse(result.authority_granted)
            self.assertEqual(result.independent_identity, 'NOT_VERIFIED')
            for changes in ({'expected_human_id': record['issuer_id']},
                            {'expected_workspace': 'other-workspace'},
                            {'expected_document_sha256': '0'*64}):
                with self.subTest(changes=changes), self.assertRaises(ProvisioningBlocked):
                    verify_owner_installation_consent(path, **dict(args, **changes))

    def test_helper_rejects_duplicate_keys_and_oversized_document(self):
        _, raw, consent, record = self.setup_binding()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'consent.json'
            for body in (b'{"a":1,"a":2}', b' '*65537):
                path.write_bytes(body)
                with self.assertRaises(ProvisioningBlocked):
                    verify_owner_installation_consent(
                        path, expected_human_id=record['actual_human_id'],
                        expected_document_sha256=hashlib.sha256(body).hexdigest(),
                        expected_workspace='fixture-workspace', root_record=record)
