import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from company_os.provisioning import FIELDS, ProvisioningBlocked, root_insert
from company_os.provisioning import enroll_root, ProvisioningOutcomeUnknown
from company_os.provisioning import read_root
from .test_registry_reader import Connection


class ProvisionConnection(Connection):
    def fetchone(self):
        if 'scope_lock_registry' in self.calls[-1][0]:
            return (0, {'kind': 'INSTALLATION_BOOTSTRAP', 'installation_id': self.installation})
        return ('test-provisioner',)

    def commit(self):
        self.calls.append(('COMMIT', ()))
        if self.fail:
            raise OSError('lost ack')


class FixtureVerifier:
    # Test double only; not a real identity verifier.
    def verify_root(self, record):
        return record


def fixture():
    now = datetime.now(timezone.utc)
    r = dict.fromkeys(FIELDS, 'a' * 64)
    for n in ('installation_id', 'issuer_id', 'key_id', 'actual_human_id', 'custodian_id', 'host_boot_id'):
        r[n] = str(uuid4())
    r.update(generation=1, enrollment_revision=1, lock_id=1,
             not_after_boottime_ns=20, r56_anchor_boottime_ns=10,
             allowed_operations=['e0.setup_mandate_consume'], not_before=now,
             not_after=now + timedelta(minutes=1), r56_anchor_utc_lower=now,
             r56_anchor_utc_upper=now, r56_issuer_class='PROVISIONING_SERVICE')
    r['custodian_id'] = r['actual_human_id']
    return r


class ProvisioningTests(unittest.TestCase):
    def test_writer_verifies_then_commits_without_bootstrap_claim(self):
        c = ProvisionConnection()
        record = fixture()
        c.installation = record['installation_id']
        result = enroll_root(lambda: c, FixtureVerifier(), record, expected_login='test-provisioner')
        self.assertEqual(result['bootstrap'], 'NOT_ARMED')
        self.assertEqual(result['independent_readback'], 'NOT_RUN')
        self.assertTrue(c.closed)
        self.assertEqual(sum(sql == 'COMMIT' for sql, _ in c.calls), 1)

    def test_wrong_login_or_failed_verifier_blocks_write(self):
        c = ProvisionConnection()
        with self.assertRaises(ProvisioningBlocked):
            enroll_root(lambda: c, FixtureVerifier(), fixture(), expected_login='wrong')
        self.assertFalse(any(sql.startswith('INSERT') for sql, _ in c.calls))
        with self.assertRaises(ProvisioningBlocked):
            enroll_root(lambda: self.fail('must not connect'), object(), fixture(), expected_login='test')

    def test_commit_ack_loss_is_unknown_without_retry(self):
        class LostAck(ProvisionConnection):
            def commit(self):
                self.calls.append(('COMMIT', ()))
                raise OSError('lost ack')
        c = LostAck()
        record = fixture()
        c.installation = record['installation_id']
        with self.assertRaises(ProvisioningOutcomeUnknown):
            enroll_root(lambda: c, FixtureVerifier(), record, expected_login='test-provisioner')
        self.assertEqual(sum(sql.startswith('INSERT') for sql, _ in c.calls), 1)
        self.assertTrue(c.closed)

    def test_exact_readback_and_revocation(self):
        record = fixture()
        class Reader(ProvisionConnection):
            def fetchone(self):
                if 'r55_setup_root_enrollments' in self.calls[-1][0]:
                    return self.row
                return super().fetchone()
        for revoked in (None, datetime.now(timezone.utc)):
            c = Reader()
            c.row = tuple(record[n] for n in FIELDS) + (revoked, None)
            if revoked is None:
                self.assertEqual(read_root(lambda: c, record, expected_login='test-provisioner')['readback'], 'MATCH')
            else:
                with self.assertRaises(ProvisioningBlocked):
                    read_root(lambda: c, record, expected_login='test-provisioner')
            self.assertTrue(c.closed)

    def test_parameters_not_interpolated_and_no_approval_claim(self):
        r = fixture()
        sql, args = root_insert(r)
        self.assertNotIn(r['actual_human_id'], sql)
        self.assertEqual(len(args), len(FIELDS))
        self.assertNotIn('ON CONFLICT', sql)

    def test_missing_evidence_and_scope_expansion_rejected(self):
        for field, value in [('verified_identity_evidence_digest', None),
                             ('allowed_operations', ['objectives.create']),
                             ('generation', True), ('not_after_boottime_ns', 5),
                             ('r56_issuer_class', 'AGENT')]:
            r = fixture()
            r[field] = value
            with self.subTest(field=field), self.assertRaises(ProvisioningBlocked):
                root_insert(r)

    def test_self_issued_human_is_rejected(self):
        r = fixture()
        r['issuer_id'] = r['actual_human_id']
        with self.assertRaises(ProvisioningBlocked):
            root_insert(r)
