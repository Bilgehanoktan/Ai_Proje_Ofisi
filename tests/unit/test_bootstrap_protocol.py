import unittest
from company_os.bootstrap.bootstrap_protocol import setup_tag, enter_tag, arm, consume
from company_os.bootstrap.provisioning import ProvisioningBlocked
from tests.unit.test_provisioning import fixture


class Cursor:
    def __init__(self, record):
        self.record = record
        self.calls = []

    def execute(self, sql, args=()):
        self.calls.append((sql, args))

    def fetchone(self):
        sql = self.calls[-1][0]
        if 'pg_backend_pid' in sql:
            return (123, '999', 'test-login')
        if 'setup_control_arm' in sql:
            return (self.record['installation_id'],)
        return ({'state': 'SUCCEEDED', 'result_ref': self.record['installation_id']},)


class BootstrapTests(unittest.TestCase):
    def test_arm_and_consume_use_exact_same_connection_context(self):
        r = fixture()
        c = Cursor(r)
        root = arm(c, r, {}, b'x'*32, expected_login='test-login',
                   utc_lower='fixture-lower', utc_upper='fixture-upper')
        result = consume(c, r, b'n'*32, b'x'*32, expected_login='test-login',
                         root_proof_digest=root, manifest_digest='a'*64, correlation_id=r['key_id'])
        self.assertEqual(result['state'], 'SUCCEEDED')
        self.assertEqual(sum('pg_backend_pid' in sql for sql, _ in c.calls), 2)
        self.assertTrue(all('fixture-lower' not in sql for sql, _ in c.calls))

    def test_wrong_login_never_arms(self):
        r = fixture()
        c = Cursor(r)
        with self.assertRaises(ProvisioningBlocked):
            arm(c, r, {}, b'x'*32, expected_login='wrong', utc_lower='', utc_upper='')
        self.assertEqual(len(c.calls), 1)

    def test_raw_bytes_revision_and_domain_are_bound(self):
        r = fixture()
        args = dict(issuer_id=r['issuer_id'], key_id=r['key_id'], revision=1, raw=b'{}')
        one = setup_tag(b'x'*32, **args)
        self.assertNotEqual(one, setup_tag(b'x'*32, **dict(args, raw=b'{ }')))
        self.assertNotEqual(one, setup_tag(b'x'*32, **dict(args, revision=2)))
        self.assertNotEqual(one, enter_tag(b'x'*32, installation_id=r['installation_id'], generation=1, **args))
