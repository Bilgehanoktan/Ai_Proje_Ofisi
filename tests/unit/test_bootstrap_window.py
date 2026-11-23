"""Fake-driver protocol tests; positive authority requires native enrollment."""
import copy
import unittest
from uuid import uuid4

from company_os.bootstrap.bootstrap_window import inspect_current_bootstrap_window, FIELDS, QUERY, LOGIN
from company_os.bootstrap.provisioning import ProvisioningBlocked
from tests.unit.test_registry_reader import Connection


class WindowConnection(Connection):
    def __init__(self, pins):
        super().__init__()
        self.context=(123,'999',LOGIN)
        self.result=dict(pins,utc_lower='2026-11-13T10:00:00+00:00',
            utc_upper='2026-11-13T10:00:01+00:00',boottime_ns=100,
            backend_pid=123,transaction_id='999',db_login=LOGIN,
            authorization='BOOTSTRAP_WINDOW_ONLY_NOT_RUNTIME',new_grants=0)
    def fetchone(self):
        return (copy.deepcopy(self.result),) if self.calls[-1][0]==QUERY else self.context
    def commit(self): raise AssertionError('must never commit')


def pins():
    return dict(installation_id=str(uuid4()),generation=1,
        enrollment_digest='a'*64,host_boot_id=str(uuid4()))


class BootstrapWindowTests(unittest.TestCase):
    def test_bound_native_function_only_and_rollback_not_commit(self):
        expected=pins();c=WindowConnection(expected)
        result=inspect_current_bootstrap_window(lambda:c,expected=expected)
        self.assertEqual(result,c.result)
        self.assertIn((QUERY,tuple(expected[n] for n in FIELDS)),c.calls)
        self.assertEqual(c.calls[0][0],'BEGIN ISOLATION LEVEL REPEATABLE READ')
        self.assertEqual(c.calls[-1][0],'ROLLBACK')
        self.assertTrue(c.closed)

    def test_invalid_pins_never_open_connection(self):
        for change in ({'generation':True},{'generation':0},{'generation':2**53},
                       {'enrollment_digest':'bad'},{'host_boot_id':'bad'},{'extra':1}):
            with self.subTest(change=change),self.assertRaises(ProvisioningBlocked):
                inspect_current_bootstrap_window(lambda:self.fail('must not connect'),expected=dict(pins(),**change))

    def test_wrong_context_and_transaction_block_before_native_call(self):
        for change in ('login','pid','xid','autocommit','busy'):
            expected=pins();c=WindowConnection(expected)
            if change=='login':c.context=(123,'999','wrong')
            elif change=='pid':c.context=(True,'999',LOGIN)
            elif change=='xid':c.context=(123,999,LOGIN)
            elif change=='autocommit':c.autocommit=True
            else:c.info.transaction_status=2
            with self.subTest(change=change),self.assertRaises(ProvisioningBlocked):
                inspect_current_bootstrap_window(lambda:c,expected=expected)
            self.assertFalse(any(sql==QUERY for sql,_ in c.calls))
            self.assertTrue(c.closed)

    def test_changed_scope_context_or_ambiguous_time_never_succeeds(self):
        for key,value in (('generation',True),('generation',2),('host_boot_id',str(uuid4())),
                ('enrollment_digest','b'*64),('backend_pid',124),('transaction_id','1000'),
                ('new_grants',True),('new_grants',1),('boottime_ns',True),
                ('authorization','RUNTIME_APPROVED'),('utc_lower','infinity'),
                ('utc_upper','2020-01-01T00:00:00+00:00'),('utc_upper','2026-11-13T10:00:01')):
            expected=pins();c=WindowConnection(expected);c.result[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ProvisioningBlocked):
                inspect_current_bootstrap_window(lambda:c,expected=expected)
            self.assertTrue(c.closed)

    def test_driver_failure_is_redacted_no_clock_or_query_fallback(self):
        expected=pins();c=WindowConnection(expected);c.fail=True
        with self.assertRaisesRegex(ProvisioningBlocked,'^CURRENT_BOOTSTRAP_WINDOW_UNAVAILABLE$'):
            inspect_current_bootstrap_window(lambda:c,expected=expected)
        self.assertTrue(c.closed)
        self.assertFalse(any('r55_setup_root' in sql for sql,_ in c.calls))

    def test_input_mutation_during_connect_cannot_change_pins(self):
        expected=pins();c=WindowConnection(expected)
        def connect():
            expected['generation']=2
            return c
        self.assertEqual(inspect_current_bootstrap_window(connect,expected=expected)['generation'],1)
