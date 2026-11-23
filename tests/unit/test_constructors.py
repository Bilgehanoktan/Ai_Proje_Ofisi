"""Sahte DB/socket regresyonları; gerçek PostgreSQL veya yetki kabulü değildir."""
import json
import unittest
from types import SimpleNamespace
from company_os.kernel import command_host as host

class Cursor:

    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=()):
        self.c.calls.append((sql, args))
        self.c.last = sql

    def fetchone(self):
        sql = self.c.last
        if 'r54_context_enter' in sql:
            return ('nonce',)
        if 'r63_constructor_result' in sql:
            return (self.c.canonical,)
        if 'r58_emission_snapshot' in sql:
            return ({'project_epoch': 1},)
        return (dict(command_id='command', state='SUCCEEDED', result_ref='object'),)

class Connection:

    def __init__(self):
        self.info = SimpleNamespace(transaction_status=0)
        self.calls = []
        self.last = ''
        self.fail = False
        self.closed = False
        self.canonical = dict(command_id='command', state='SUCCEEDED', result_ref='object', result_payload={'objective_id': 'object', 'project_revision': 1})

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.calls.append(('COMMIT', ()))
        if self.fail:
            raise OSError('unknown acknowledgement')

    def rollback(self):
        self.calls.append(('ROLLBACK', ()))

    def close(self):
        self.closed = True

AUTH = dict(token='fixture-not-real', project_id='p', kind='PROJECT', resource_id='p', grant_id='g')

class ConstructorTests(unittest.TestCase):

    def test_three_routes_use_exact_existing_jsonb_sql(self):
        for op, name in [('objectives.create', 'r53_objectives_create'), ('plans.create', 'r54_plans_create'), ('tasks.create', 'r54_tasks_create')]:
            self.assertEqual(host.ROUTES[op], (name, ('jsonb',)))

    def test_payload_readback_is_inside_transaction_before_commit(self):
        c = Connection()
        result = host.execute(c, AUTH, 'objectives.create', ['{}'])
        self.assertEqual(result['result']['objective_id'], 'object')
        self.assertEqual(result['command_receipt']['state'], 'SUCCEEDED')
        sql = [s for s, a in c.calls]
        self.assertLess(next((i for i, s in enumerate(sql) if 'r63_constructor_result' in s)), sql.index('COMMIT'))
        self.assertTrue(c.closed)

    def test_unknown_commit_does_not_deliver_constructor_result(self):
        c = Connection()
        c.fail = True
        with self.assertRaises(host.UnknownCommitOutcome):
            host.execute(c, AUTH, 'plans.create', ['{}'])
        self.assertEqual(sum((s == 'COMMIT' for s, a in c.calls)), 1)

    def test_missing_payload_rolls_back_without_success(self):
        c = Connection()
        c.canonical = {'state': 'SUCCEEDED', 'command_id': 'x'}
        with self.assertRaises(host.Blocked):
            host.execute(c, AUTH, 'tasks.create', ['{}'])
        self.assertIn(('ROLLBACK', ()), c.calls)
        self.assertNotIn(('COMMIT', ()), c.calls)
