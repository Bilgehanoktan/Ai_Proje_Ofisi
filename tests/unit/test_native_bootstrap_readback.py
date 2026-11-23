"""Narrow native function adapter; DB doubles do not prove actual role enrollment."""
import copy
import unittest
from uuid import uuid4
from company_os.bootstrap.bootstrap_readback import read_native_bootstrap_receipt, NativeBootstrapReadback, FIELDS, NATIVE_QUERY, QUERY
from company_os.bootstrap.provisioning import ProvisioningBlocked
from tests.unit import test_registry_reader


class NativeReaderTests(unittest.TestCase):
    def setUp(self):
        self.expected={name:('a'*64 if name.endswith('digest') else str(uuid4())) for name in FIELDS}
        self.expected['generation']=1
        expected=self.expected
        class Reader(test_registry_reader.Connection):
            def __init__(self):
                super().__init__();self.result=dict(expected,readback='EXACT_COMMITTED_WITNESS_MATCH',authorization='NOT_VERIFIED',new_grants=0)
            def fetchone(self):
                if self.calls[-1][0]=='SELECT session_user':return ('company_provisioning_runtime_r55',)
                return (copy.deepcopy(self.result),)
        self.c=Reader()

    def test_function_only_parameter_binding_and_readonly_cleanup(self):
        result=read_native_bootstrap_receipt(lambda:self.c,expected=self.expected)
        self.assertEqual(result['authorization'],'NOT_VERIFIED')
        self.assertIn((NATIVE_QUERY,tuple(self.expected[name] for name in FIELDS)),self.c.calls)
        self.assertFalse(any(sql==QUERY for sql,args in self.c.calls))
        self.assertTrue(self.c.closed)
        self.assertEqual(self.c.calls[-1][0],'ROLLBACK')

    def test_native_legacy_partial_changed_or_boolean_metadata_rejected(self):
        base=copy.deepcopy(self.c.result)
        for change in (dict(generation=True),dict(new_grants=False),dict(authorization='VERIFIED'),
                       dict(tenant_id=str(uuid4())),dict(readback=None)):
            self.c.result=dict(base,**change)
            with self.subTest(change=change),self.assertRaises(ProvisioningBlocked):
                read_native_bootstrap_receipt(lambda:self.c,expected=self.expected)
        self.c.result={}
        with self.assertRaises(ProvisioningBlocked):read_native_bootstrap_receipt(lambda:self.c,expected=self.expected)

    def test_other_login_rejected_before_connect_without_fallback_table_read(self):
        with self.assertRaises(ProvisioningBlocked):
            read_native_bootstrap_receipt(lambda:self.fail('no connection'),expected=self.expected,expected_login='other')
        self.c.fail=True
        with self.assertRaisesRegex(ProvisioningBlocked,'^BOOTSTRAP_READBACK_FAILED$'):
            read_native_bootstrap_receipt(lambda:self.c,expected=self.expected)
        self.assertFalse(any(sql==QUERY for sql,args in self.c.calls))

    def test_callable_native_port_matches_supervisor_contract(self):
        port=NativeBootstrapReadback(connect=lambda:self.c,expected=self.expected,expected_login='company_provisioning_runtime_r55')
        self.assertEqual(port()['readback'],'EXACT_COMMITTED_WITNESS_MATCH')
