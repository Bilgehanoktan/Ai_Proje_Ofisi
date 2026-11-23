import unittest
from datetime import datetime, timezone
from company_os.session_provisioning import issue_owner_session, issue_principal_session
from company_os.provisioning import ProvisioningBlocked


class Cursor:
    def __init__(self, kind='HUMAN'):
        self.calls = []
        self.kind = kind

    def execute(self, sql, args=()):
        self.calls.append((sql, args))

    def fetchone(self):
        sql = self.calls[-1][0]
        if 'root_bounds' in sql:
            return ({'fixture': True},)
        if 'bootstrap_receipts' in sql and 'p.kind,' in sql:
            return ('tenant', 'project', 'principal', self.kind, datetime.now(timezone.utc))
        if 'bootstrap_receipts' in sql:
            return ('tenant', 'project', 'human', datetime.now(timezone.utc))
        return (3,)

    def fetchall(self):
        return [(1,), (2,)]


class SessionTests(unittest.TestCase):
    def test_token_is_hashed_and_no_grant_is_created(self):
        c = Cursor()
        token = 'synthetic-session-token-' * 3
        result = issue_owner_session(c, installation_id='fixture', token=token)
        self.assertEqual(result['new_grants'], 0)
        for sql, args in c.calls:
            self.assertNotIn(token, str(args))
            self.assertNotIn('INSERT INTO company.project_grants', sql)
        self.assertTrue(any('OwnerSessionIssued' in sql for sql, _ in c.calls))

    def test_invalid_ttl_or_token_never_queries(self):
        c = Cursor()
        with self.assertRaises(ProvisioningBlocked):
            issue_owner_session(c, installation_id='fixture', token='short')
        self.assertEqual(c.calls, [])

    def test_principal_session_enforces_role_and_hashes_token(self):
        c = Cursor(kind='WORKER')
        token = 'synthetic-worker-token-' * 3
        result = issue_principal_session(
            c, installation_id='fixture', principal_id='principal', role='WORKER', token=token
        )
        self.assertEqual(result['new_grants'], 0)
        self.assertEqual(result['role'], 'WORKER')
        for sql, args in c.calls:
            self.assertNotIn(token, str(args))
            self.assertNotIn('INSERT INTO company.project_grants', sql)
        self.assertTrue(any('PrincipalSessionIssued' in sql for sql, _ in c.calls))

    def test_principal_session_rejects_mismatched_kind_or_role(self):
        c = Cursor(kind='WORKER')
        token = 'synthetic-worker-token-' * 3
        with self.assertRaises(ProvisioningBlocked):
            issue_principal_session(
                c, installation_id='fixture', principal_id='principal', role='VERIFIER', token=token
            )
        with self.assertRaises(ProvisioningBlocked):
            issue_principal_session(
                c, installation_id='fixture', principal_id='principal', role='ADMIN', token=token
            )
