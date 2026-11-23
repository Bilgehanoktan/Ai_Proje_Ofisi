"""Sahte DB/socket regresyonları; gerçek PostgreSQL veya yetki kabulü değildir."""
import json
import unittest
from types import SimpleNamespace
from company_os.kernel import command_host as host

AUTH = dict(token='offline-fixture', project_id='p', kind='PROJECT', resource_id='p', grant_id='g')

class Cursor:

    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        self.c.calls.append((sql, args))
        self.c.last = sql
        if 'r53_revoke_project_grant(' in sql:
            self.c.epoch += 1

    def fetchone(self):
        c = self.c
        if 'r54_context_enter' in c.last:
            return ('nonce',)
        if 'r58_emission_snapshot' in c.last:
            if c.epoch != 1:
                raise ValueError('old context no longer authorized')
            return ({'project_epoch': c.epoch},)
        if 'r58_emission_check' in c.last:
            return (json.loads(c.calls[-1][1][0])['project_epoch'] == c.epoch,)
        return (c.result,)

class Connection:

    def __init__(self, epoch=1):
        self.epoch = epoch
        self.calls = []
        self.last = ''
        self.closed = False
        self.fail_commit = False
        self.committed = False
        self.info = SimpleNamespace(transaction_status=0)
        self.result = dict(command_id='c', state='SUCCEEDED', result_ref='g', result_payload={'revision': 2})

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.calls.append(('COMMIT', ()))
        self.committed = True
        if self.fail_commit:
            raise OSError('lost acknowledgement')

    def rollback(self):
        self.calls.append(('ROLLBACK', ()))

    def close(self):
        self.closed = True

class Socket:

    def __init__(self):
        self.data = []

    def settimeout(self, t):
        pass

    def sendall(self, b):
        self.data.append(b)

class FinalityTests(unittest.TestCase):

    def test_self_revoke_commits_with_pre_cut_snapshot(self):
        c = Connection()
        e = host.execute(c, AUTH, 'CAP-017.revoke', ['{}'])
        self.assertTrue(c.committed)
        self.assertTrue(c.closed)
        self.assertEqual(e['snapshot']['project_epoch'], 1)
        self.assertEqual(c.epoch, 2)
        snapshots = [i for i, (s, a) in enumerate(c.calls) if 'emission_snapshot' in s]
        cut = next((i for i, (s, a) in enumerate(c.calls) if 'r53_revoke_project_grant' in s))
        self.assertEqual(len(snapshots), 1)
        self.assertLess(snapshots[0], cut)

    def test_revoked_snapshot_cannot_emit_any_bytes(self):
        e = host.execute(Connection(), AUTH, 'CAP-017.revoke', ['{}'])
        c = Connection(epoch=2)
        s = Socket()
        with self.assertRaises(host.UnknownCommitOutcome):
            host.emit(c, AUTH, e, s, 1)
        self.assertEqual(s.data, [])
        self.assertFalse(c.committed)
        self.assertTrue(c.closed)

    def test_lost_commit_ack_never_returns_or_retries(self):
        c = Connection()
        c.fail_commit = True
        with self.assertRaises(host.UnknownCommitOutcome):
            host.execute(c, AUTH, 'CAP-017.revoke', ['{}'])
        self.assertEqual(sum(('r53_revoke_project_grant(' in s for s, a in c.calls)), 1)
        self.assertEqual(sum((s == 'COMMIT' for s, a in c.calls)), 1)

    def test_legacy_success_without_canonical_payload_is_blocked(self):
        c = Connection()
        c.result = {'state': 'SUCCEEDED', 'command_id': 'old', 'result_ref': 'g'}
        with self.assertRaises(host.Blocked):
            host.execute(c, AUTH, 'CAP-017.revoke', ['{}'])
        self.assertFalse(c.committed)
        self.assertIn(('ROLLBACK', ()), c.calls)

    def test_qualification_route_cannot_flip_decision(self):
        for operation, value in [('qualification.activate', True), ('qualification.revoke', False), ('qualification.revoke', 1)]:
            c = Connection()
            with self.assertRaises(host.Blocked):
                host.execute(c, AUTH, operation, ['q', 0, 't', 'a', 'd', value, 'key', 'corr'])
            self.assertFalse(any(('r54_qualification_decide(' in s for s, a in c.calls)))

    def test_qualification_parameter_binding_and_sealed_result(self):
        for operation, value in [('qualification.activate', False), ('qualification.revoke', True)]:
            c = Connection()
            args = ['q', 0, 't', 'a', 'd', value, "key');DROP TABLE company.commands;--", 'corr']
            e = host.execute(c, AUTH, operation, args)
            call = next(((s, a) for s, a in c.calls if 'r54_qualification_decide(' in s))
            self.assertNotIn('DROP', call[0])
            self.assertEqual(call[1], tuple(args))
            self.assertEqual(e['result'], {'revision': 2})

    def test_non_cut_operations_capture_snapshot_after_native(self):
        c = Connection()
        host.execute(c, AUTH, 'e0.setup_mandate_consume', ['i', 'corr'])
        calls = [s for s, a in c.calls]
        self.assertLess(next((i for i, s in enumerate(calls) if 'r54_e0_setup_mandate_consume' in s)), next((i for i, s in enumerate(calls) if 'emission_snapshot' in s)))
