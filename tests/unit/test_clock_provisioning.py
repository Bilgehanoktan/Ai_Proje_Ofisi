import unittest
from uuid import uuid4
from company_os.bootstrap.clock_provisioning import DEFAULT_CLOCK_POLICY, activate_clock_policy, clock_observation_tag, clock_policy_tag, persist_clock_sample, register_clock_epoch, validate_clock_policy
from company_os.bootstrap.provisioning import ProvisioningBlocked


class ClockCursor:
    def __init__(self, login, epoch_id=None):
        self.login = login
        self.epoch_id = epoch_id
        self.calls = []

    def execute(self, sql, args=()):
        self.calls.append((sql, args))

    def fetchone(self):
        sql = self.calls[-1][0]
        if 'pg_backend_pid()' in sql:
            return (4242, '99', self.login)
        if 'r58_clock_policy_write' in sql:
            return ({'outcome': 'ACTIVATE', 'revision': 1, 'receipt_digest': 'a' * 64},)
        if 'r55_cp_clock_epoch_register' in sql:
            return (self.epoch_id,)
        if 'r55_cp_clock_sample_persist' in sql:
            return ({'status': 'SAMPLE_PERSISTED_NO_LIVE_CUT', 'source_sequence': 1},)
        return None


class ClockProvisioningTests(unittest.TestCase):
    def test_validate_clock_policy_requires_nine_positive_ordered_keys(self):
        valid = validate_clock_policy(DEFAULT_CLOCK_POLICY)
        self.assertEqual(len(valid), 9)
        bad = dict(DEFAULT_CLOCK_POLICY, first_alert_ms=90000)
        with self.assertRaises(ProvisioningBlocked):
            validate_clock_policy(bad)
        with self.assertRaises(ProvisioningBlocked):
            validate_clock_policy({'poll_ms': 1000})

    def test_activate_clock_policy_binds_context_and_hmac(self):
        cur = ClockCursor('aipof-dbtest')
        record = {
            'installation_id': str(uuid4()),
            'issuer_id': str(uuid4()),
            'key_id': str(uuid4()),
            'enrollment_revision': 1,
        }
        # Test missing policy raises ProvisioningBlocked
        with self.assertRaises(ProvisioningBlocked):
            activate_clock_policy(
                cur, record, b'k' * 32, consent_id=str(uuid4()),
                expected_login='aipof-dbtest', policy=None,
            )

        res = activate_clock_policy(
            cur,
            record,
            b'k' * 32,
            consent_id=str(uuid4()),
            expected_login='aipof-dbtest',
            policy=DEFAULT_CLOCK_POLICY,
        )
        self.assertEqual(res['outcome'], 'ACTIVATE')
        self.assertTrue(any('r58_clock_policy_write' in s for s, _ in cur.calls))

    def test_epoch_and_sample_writers_require_exact_login_and_proof_tags(self):
        epoch_id = str(uuid4())
        cur = ClockCursor('company_clock_runtime_r55', epoch_id=epoch_id)
        got_epoch = register_clock_epoch(
            cur,
            tenant_id=str(uuid4()),
            project_id=str(uuid4()),
            epoch_id=epoch_id,
            issuer_id=str(uuid4()),
            key_id=str(uuid4()),
            revision=1,
            secret=b's' * 32,
            host_id=str(uuid4()),
            host_revision=1,
            host_generation=1,
            host_boot_id=str(uuid4()),
            policy=DEFAULT_CLOCK_POLICY,
            policy_digest='b' * 64,
            current_boottime_ns=1000,
            valid_until_boottime_ns=2000,
            utc_lower_bound='2026-11-08T00:00:00Z',
            utc_upper_bound='2026-11-08T00:00:01Z',
        )
        self.assertEqual(got_epoch, epoch_id)
        # Missing source_sync_state raises ProvisioningBlocked
        with self.assertRaises(ProvisioningBlocked):
            persist_clock_sample(
                cur, tenant_id=str(uuid4()), project_id=str(uuid4()),
                epoch_id=epoch_id, sample_id=str(uuid4()), issuer_id=str(uuid4()),
                key_id=str(uuid4()), revision=1, secret=b's' * 32,
                host_id=str(uuid4()), host_revision=1, host_generation=1,
                host_boot_id=str(uuid4()), source_sequence=1,
                sample_boottime_ns=1000, current_boottime_ns=1100,
                valid_until_boottime_ns=5000, sampled_at='2026-11-08T00:00:00.500Z',
                utc_lower_bound='2026-11-08T00:00:00Z', utc_upper_bound='2026-11-08T00:00:01Z',
                source_sync_state=None,
            )

        sample_res = persist_clock_sample(
            cur,
            tenant_id=str(uuid4()),
            project_id=str(uuid4()),
            epoch_id=epoch_id,
            sample_id=str(uuid4()),
            issuer_id=str(uuid4()),
            key_id=str(uuid4()),
            revision=1,
            secret=b's' * 32,
            host_id=str(uuid4()),
            host_revision=1,
            host_generation=1,
            host_boot_id=str(uuid4()),
            source_sequence=1,
            sample_boottime_ns=1000,
            current_boottime_ns=1100,
            valid_until_boottime_ns=5000,
            sampled_at='2026-11-08T00:00:00.500Z',
            utc_lower_bound='2026-11-08T00:00:00Z',
            utc_upper_bound='2026-11-08T00:00:01Z',
            source_sync_state='SYNC',
        )
        self.assertEqual(sample_res['status'], 'SAMPLE_PERSISTED_NO_LIVE_CUT')

    def test_invalid_wire_or_sequence_rejected(self):
        with self.assertRaises(ProvisioningBlocked):
            clock_policy_tag(b'short', consent_id='c', issuer_id='i', key_id='k', revision=1, raw=b'{}')
        with self.assertRaises(ProvisioningBlocked):
            clock_observation_tag(b'short', issuer_id='i', key_id='k', revision=1, raw=b'{}')
