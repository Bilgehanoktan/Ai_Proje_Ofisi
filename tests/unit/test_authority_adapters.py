"""Authority adapters over owning contracts; DB doubles are not native acceptance."""
import copy
import json
from types import SimpleNamespace
import unittest
from uuid import uuid4

from company_os.bootstrap import provisioning as p
from company_os.kernel import command_host
from company_os.bootstrap.bootstrap_readback import read_bootstrap_receipt, BootstrapReadback, FIELDS, QUERY
from tests.unit import test_finality, test_registry_reader


def uid():return str(uuid4())


class RevokeTests(unittest.TestCase):
    def setUp(self):
        self.conn=test_finality.Connection()
        project=uid();target=uid();command=uid()
        self.auth=dict(token='fixture-only',project_id=project,kind='PROJECT',resource_id=project,grant_id=uid())
        self.args=dict(target_grant_id=target,reason='OWNER_REQUEST',tenant_id=uid(),grant_revision=0,
                       revocation_scope_digest='a'*64,idempotency_key='fixture-revoke-0001',correlation_id=uid())
        result=dict(operation='CAP-017.revoke',status='RECORDED',resource_id=target,revision=1,
                    scope_digest='a'*64,descendant_ids=[target],command_receipt_ref=command,
                    result=dict(revocation_receipt_ref=command))
        self.conn.result=dict(command_id=command,state='SUCCEEDED',result_ref=target,result_payload=result)

    def test_general_grant_issuer_never_claims_authority_without_writer(self):
        with self.assertRaisesRegex(p.ProvisioningBlocked,'ENROLLED_NATIVE_GRANT_WRITER_REQUIRED'):
            p.provision_project_grant(self.conn,None,grant_id=uid(),principal_id=uid(),permissions=['fixture'])
        self.assertEqual(self.conn.calls,[])

    def test_real_command_route_scope_revision_digest_and_commit_receipt(self):
        result=p.revoke_project_grant(self.conn,self.auth,**self.args)
        self.assertTrue(self.conn.committed);self.assertTrue(self.conn.closed)
        self.assertEqual(result['snapshot']['project_epoch'],1)
        self.assertEqual(self.conn.epoch,2)
        sql,args=next(call for call in self.conn.calls if 'r53_revoke_project_grant(' in call[0])
        request=json.loads(args[0])
        self.assertEqual(request['payload']['revocation_scope_digest'],'a'*64)
        self.assertEqual(request['expected_revision'],0)
        self.assertEqual(request['resource_id'],self.args['target_grant_id'])
        self.assertNotIn(self.args['target_grant_id'],sql)
        self.assertNotIn('revoked',result) # A receipt is not a current authority/OS stop proof.

    def test_legacy_or_invalid_input_never_executes_db(self):
        cases=[dict(tenant_id=None),dict(grant_revision=True),dict(grant_revision=-1),
               dict(revocation_scope_digest=None),dict(idempotency_key='short'),dict(reason='arbitrary text')]
        for changes in cases:
            with self.subTest(change=changes),self.assertRaises(p.ProvisioningBlocked):
                p.revoke_project_grant(self.conn,self.auth,**dict(self.args,**changes))
        auth=dict(self.auth,kind='ATTEMPT')
        with self.assertRaises(p.ProvisioningBlocked):p.revoke_project_grant(self.conn,auth,**self.args)
        self.assertEqual(self.conn.calls,[])

    def test_lost_commit_ack_is_not_success_or_automatic_retry(self):
        self.conn.fail_commit=True
        with self.assertRaises(command_host.UnknownCommitOutcome):p.revoke_project_grant(self.conn,self.auth,**self.args)
        self.assertEqual(sum('r53_revoke_project_grant(' in sql for sql,args in self.conn.calls),1)
        self.assertEqual(sum(sql=='COMMIT' for sql,args in self.conn.calls),1)

    def test_mismatched_committed_result_requires_independent_readback(self):
        self.conn.result['result_payload']['scope_digest']='b'*64
        with self.assertRaises(p.ProvisioningOutcomeUnknown):p.revoke_project_grant(self.conn,self.auth,**self.args)
        self.assertTrue(self.conn.committed)
        self.assertEqual(sum('r53_revoke_project_grant(' in sql for sql,args in self.conn.calls),1)


class BootstrapReaderTests(unittest.TestCase):
    def setUp(self):
        self.expected={name:('a'*64 if name.endswith('digest') else uid()) for name in FIELDS}
        self.expected['generation']=1
        expected=self.expected
        class Reader(test_registry_reader.Connection):
            def __init__(self):
                super().__init__();self.login='fixture-reader';self.rows=[tuple(expected[name] for name in FIELDS)]
            def fetchone(self):return (self.login,)
        self.c=Reader()

    def read(self,**kw):
        return read_bootstrap_receipt(lambda:self.c,expected=self.expected,expected_login='fixture-reader',**kw)

    def test_exact_committed_witness_read_is_readonly_and_not_authorization(self):
        result=self.read()
        self.assertEqual(result['readback'],'EXACT_COMMITTED_WITNESS_MATCH')
        self.assertEqual(result['authorization'],'NOT_VERIFIED')
        self.assertEqual(result['new_grants'],0)
        self.assertEqual(self.c.calls[0][0],'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertIn((QUERY,(self.expected['installation_id'],1)),self.c.calls)
        self.assertNotIn('COMMIT',[sql for sql,args in self.c.calls])
        self.assertEqual(self.c.calls[-1][0],'ROLLBACK');self.assertTrue(self.c.closed)

    def test_missing_duplicate_wrong_scope_or_digest_never_matches(self):
        original=self.c.rows[0]
        wrong=list(original);wrong[2]=uid()
        changed=list(original);changed[-1]='b'*64
        for rows in ([],[original,original],[tuple(wrong)],[tuple(changed)],[('malformed',)]):
            self.c.rows=rows
            with self.subTest(rows=rows),self.assertRaises(p.ProvisioningBlocked):self.read()

    def test_wrong_login_rejects_before_witness_query(self):
        self.c.login='wrong'
        with self.assertRaises(p.ProvisioningBlocked):self.read()
        self.assertFalse(any(sql==QUERY for sql,args in self.c.calls))

    def test_invalid_inputs_never_connect_or_query(self):
        for value in (0,True,5001):
            with self.assertRaises(p.ProvisioningBlocked):self.read(timeout_ms=value)
        with self.assertRaises(p.ProvisioningBlocked):
            read_bootstrap_receipt(lambda:self.fail('must not connect'),expected=dict(self.expected,generation=True),expected_login='fixture-reader')
        self.assertEqual(self.c.calls,[])

    def test_nonidle_or_autocommit_connection_rejected_and_closed(self):
        self.c.autocommit=True
        with self.assertRaises(p.ProvisioningBlocked):self.read()
        self.assertTrue(self.c.closed)
        self.assertFalse(any(sql==QUERY for sql,args in self.c.calls))

    def test_driver_connection_and_cleanup_errors_are_redacted(self):
        self.c.fail=True
        with self.assertRaisesRegex(p.ProvisioningBlocked,'^BOOTSTRAP_READBACK_FAILED$'):self.read()
        with self.assertRaisesRegex(p.ProvisioningBlocked,'^BOOTSTRAP_READER_CONNECTION_FAILED$'):
            read_bootstrap_receipt(lambda:(_ for _ in ()).throw(OSError('sensitive-driver-detail')),
                expected=self.expected,expected_login='fixture-reader')
        self.c.fail=False
        self.c.rollback=lambda:(_ for _ in ()).throw(OSError('sensitive-driver-detail'))
        with self.assertRaisesRegex(p.ProvisioningBlocked,'^BOOTSTRAP_READER_ROLLBACK_FAILED$'):self.read()
        self.assertTrue(self.c.closed)

    def test_callable_adapter_pins_inputs_without_claiming_enrollment(self):
        port=BootstrapReadback(connect=lambda:self.c,expected=self.expected,expected_login='fixture-reader')
        self.expected['tenant_id']=uid()
        result=port()
        self.assertNotEqual(result['tenant_id'],self.expected['tenant_id'])
        self.assertEqual(result['authorization'],'NOT_VERIFIED')
