"""Session writer protocol doubles; not physical identity/enrollment proof."""
import copy
import unittest
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from company_os.kernel.session_provisioning import issue_owner_session, issue_principal_session, OWNER_BINDING_SQL, PRINCIPAL_BINDING_SQL
from company_os.bootstrap.provisioning import ProvisioningBlocked


class Cursor:
    def __init__(self,kind='HUMAN'):
        self.calls=[];self.kind=kind
        self.installation,self.tenant,self.project,self.human,self.principal,self.boot=[str(uuid4()) for _ in range(6)]
        self.now=datetime(2026,11,14,12,tzinfo=timezone.utc)
        self.bounds=dict(installation_id=self.installation,generation=1,host_boot_id=self.boot,
            utc_lower=self.now.isoformat(),utc_upper=(self.now+timedelta(seconds=1)).isoformat(),
            boottime_ns=100,backend_pid=123,transaction_id='999',db_login='physical-fixture')
        self.missing=False;self.second_generation=None;self.roots=0;self.expired=False;self.bad_lock=False
    def execute(self,sql,args=()):self.calls.append((sql,args))
    def fetchone(self):
        sql=self.calls[-1][0]
        if sql.startswith('SELECT pg_backend_pid'):return (123,'999','physical-fixture')
        if sql.startswith('SELECT company_private.r56_root_bounds'):
            self.roots+=1;value=copy.deepcopy(self.bounds)
            if self.roots==2 and self.second_generation is not None:value['generation']=self.second_generation
            return (value,)
        if 'FROM company_private.bootstrap_receipts' in sql:
            if self.missing:return None
            expires=self.now if self.expired else self.now+timedelta(seconds=30)
            if sql.startswith(PRINCIPAL_BINDING_SQL):return (self.tenant,self.project,self.principal,self.kind,expires)
            return (self.tenant,self.project,self.human,expires)
        return (3,)
    def fetchall(self):
        locks=[(1,0,{'kind':'TENANT','tenant_id':self.tenant}),
               (2,1,{'kind':'PROJECT','tenant_id':self.tenant,'project_id':self.project})]
        if self.bad_lock:locks[1]=(2,1,{'kind':'PROJECT','tenant_id':self.tenant,'project_id':str(uuid4())})
        return locks


class SessionTests(unittest.TestCase):
    def owner(self,c,**kwargs):return issue_owner_session(c,installation_id=c.installation,token='fixture-session-token-'*3,**kwargs)
    def principal(self,c,role='WORKER'):return issue_principal_session(c,installation_id=c.installation,
        principal_id=c.principal,role=role,token='fixture-session-token-'*3)
    def assert_no_writes(self,c):self.assertFalse(any(sql.startswith('INSERT') for sql,_ in c.calls))
    def test_token_is_hashed_and_no_grant_is_created(self):
        c=Cursor();result=self.owner(c)
        self.assertEqual((result['new_grants'],result['new_memberships']),(0,0))
        for sql,args in c.calls:
            self.assertNotIn('fixture-session-token-',str(args))
            self.assertNotIn('INSERT INTO company.project_grants',sql)
        self.assertTrue(any('OwnerSessionIssued' in args for _,args in c.calls))
    def test_invalid_ttl_token_or_id_never_queries(self):
        c=Cursor()
        for kwargs in ({'token':'short'},{'ttl_seconds':True},{'ttl_seconds':0},{'installation_id':'fixture'}):
            args=dict(installation_id=c.installation,token='fixture-token-'*4);args.update(kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(ProvisioningBlocked):issue_owner_session(c,**args)
        self.assertEqual(c.calls,[])
    def test_principal_session_enforces_existing_role_and_hashes_token(self):
        c=Cursor(kind='WORKER');result=self.principal(c)
        self.assertEqual(result['role'],'WORKER');self.assertEqual(result['new_memberships'],0)
        self.assertTrue(any('PrincipalSessionIssued' in args for _,args in c.calls))
    def test_session_issue_does_not_assign_membership(self):
        c=Cursor(kind='WORKER');self.principal(c)
        self.assertFalse(any('INSERT INTO company.memberships' in sql for sql,_ in c.calls))
        self.assertIn('m.role=%s',PRINCIPAL_BINDING_SQL)
    def test_missing_membership_never_creates_session_or_role(self):
        for kind in ('HUMAN','WORKER'):
            c=Cursor(kind);c.missing=True
            with self.subTest(kind=kind),self.assertRaises(ProvisioningBlocked):
                self.owner(c) if kind=='HUMAN' else self.principal(c)
            self.assert_no_writes(c)
        self.assertIn("m.role='OWNER'",OWNER_BINDING_SQL)
    def test_principal_session_rejects_mismatched_kind_or_role(self):
        for role in ('VERIFIER','ADMIN'):
            c=Cursor(kind='WORKER')
            with self.subTest(role=role),self.assertRaises(ProvisioningBlocked):self.principal(c,role)
            self.assert_no_writes(c)
    def test_root_scope_context_and_generation_must_be_exact(self):
        for key,value in (('installation_id',str(uuid4())),('generation',True),('backend_pid',124),
                ('transaction_id','other'),('host_boot_id','bad'),('utc_upper','infinity')):
            c=Cursor();c.bounds[key]=value
            with self.subTest(key=key),self.assertRaises(ProvisioningBlocked):self.owner(c)
            self.assert_no_writes(c)
    def test_changed_generation_after_lock_never_issues_session(self):
        c=Cursor();c.second_generation=2
        with self.assertRaises(ProvisioningBlocked):self.owner(c)
        self.assert_no_writes(c)
    def test_lock_identity_cannot_alias_another_project(self):
        c=Cursor();c.bad_lock=True
        with self.assertRaises(ProvisioningBlocked):self.owner(c)
        self.assert_no_writes(c)
        self.assertFalse(any('pg_advisory_xact_lock' in sql for sql,_ in c.calls))
    def test_ambiguous_expiry_never_issues_session(self):
        c=Cursor();c.expired=True
        with self.assertRaises(ProvisioningBlocked):self.owner(c)
        self.assert_no_writes(c)
    def test_root_clock_is_refreshed_after_scope_locks_no_wall_clock_fallback(self):
        c=Cursor();self.owner(c)
        self.assertEqual(c.roots,2)
        locks=[i for i,(sql,_) in enumerate(c.calls) if 'pg_advisory_xact_lock' in sql]
        roots=[i for i,(sql,_) in enumerate(c.calls) if sql.startswith('SELECT company_private.r56_root_bounds')]
        self.assertLess(roots[0],locks[0]);self.assertGreater(roots[1],locks[-1])
        self.assertNotIn('clock_timestamp()',OWNER_BINDING_SQL+PRINCIPAL_BINDING_SQL)
        self.assertTrue(any(sql.endswith('FOR SHARE OF b,d,p,m,c') for sql,_ in c.calls))
