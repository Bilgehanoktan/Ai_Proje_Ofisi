import hashlib
import unittest
from company_os.bootstrap.bootstrap_transaction import install
from company_os.bootstrap.provisioning import ProvisioningBlocked, ProvisioningOutcomeUnknown
from tests.unit.test_bootstrap_protocol import Cursor
from tests.unit.test_provisioning import fixture
from tests.unit.test_registry_reader import Connection


class BootstrapConnection(Connection):
    def __init__(self, record):
        super().__init__()
        self.record = record

    def fetchone(self):
        if 'encode(sha256' in self.calls[-1][0]:
            return (self.record['r56_approved_manifest_digest'],)
        return Cursor.fetchone(self)

    def execute(self, sql, args=()):
        self.calls.append((sql, args))

    def commit(self):
        self.calls.append(('COMMIT', ()))
        if self.fail:
            raise OSError('lost commit ack')


class BootstrapTransactionTests(unittest.TestCase):
    def run_fixture(self, fail=False):
        r = fixture()
        r['key_fingerprint'] = hashlib.sha256(b'x'*32).hexdigest()
        r['r56_approved_nonce_hash'] = hashlib.sha256(b'n'*32).hexdigest()
        c = BootstrapConnection(r)
        c.fail = fail
        return c, lambda: install(lambda: c, lambda: b'x'*32, r, {}, b'n'*32,
                                 expected_login='test-login', utc_lower='', utc_upper='', correlation_id=r['key_id'])

    def test_result_is_only_released_after_commit(self):
        c, call = self.run_fixture()
        self.assertEqual(call()['state'], 'SUCCEEDED')
        self.assertEqual(c.calls[-1][0], 'COMMIT')
        self.assertTrue(c.closed)

    def test_lost_ack_never_retries_consume(self):
        c, call = self.run_fixture(fail=True)
        with self.assertRaises(ProvisioningOutcomeUnknown):
            call()
        self.assertEqual(sum('r56_bootstrap_consume(' in sql for sql, _ in c.calls), 1)

    def test_wrong_nonce_never_opens_connection(self):
        r = fixture()
        with self.assertRaises(ProvisioningBlocked):
            install(lambda: self.fail('must not connect'), lambda: b'x'*32, r, {}, b'n'*32,
                    expected_login='test-login', utc_lower='', utc_upper='', correlation_id=r['key_id'])
