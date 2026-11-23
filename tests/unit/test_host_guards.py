import contextlib,unittest
from types import SimpleNamespace
from uuid import uuid4
from company_os.kernel import command_host as host
from company_os.engine.reply_guard import EngineReplyGuard
from packages.contracts.execution import EngineBinding, ToolReply
from tests.unit.test_pipeline import Harness, Connection
AUTH=dict(token='offline-fixture',project_id='p',kind='PROJECT',resource_id='p',grant_id='g')
class Cursor:
 def __init__(self,c):self.c=c
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def execute(self,s,a=()):self.c.calls.append((s,a));self.c.last=s
 def fetchone(self):
  if 'r54_context_enter(' in self.c.last:return ('nonce',)
  if 'r58_emission_snapshot' in self.c.last:return ({'epoch':1},)
  return (dict(command_id='c',state='SUCCEEDED',result_ref='q',result_payload={'qualified':False}),)
class C:
 def __init__(self):self.info=SimpleNamespace(transaction_status=0);self.calls=[];self.last='';self.closed=False
 def cursor(self):return Cursor(self)
 def commit(self):self.calls.append(('COMMIT',()))
 def rollback(self):self.calls.append(('ROLLBACK',()))
 def close(self):self.closed=True
class HostTests(unittest.TestCase):
 def test_all_command_timeouts_precede_context_entry(self):
  c=C();host.execute(c,AUTH,'e0.setup_mandate_consume',['i','corr'])
  enter=next(i for i,(s,a) in enumerate(c.calls) if 'r54_context_enter' in s)
  settings=[a for s,a in c.calls[:enter] if 'set_config' in s]
  self.assertEqual({x[0] for x in settings},{'statement_timeout','lock_timeout','idle_in_transaction_session_timeout'});self.assertTrue(all(x[1]=='2000ms' for x in settings));self.assertTrue(c.closed)
 def test_invalid_route_and_nonidle_connection_are_closed(self):
  for operation,status in [('unregistered',0),('e0.setup_mandate_consume',1)]:
   c=C();c.info.transaction_status=status
   with self.assertRaises(host.Blocked):host.execute(c,AUTH,operation,['i','corr'])
   self.assertTrue(c.closed);self.assertNotIn(('COMMIT',()),c.calls)
 def test_timeout_values_are_finite_bounded_integers(self):
  for value in [True,0,5001,float('nan')]:
   c=C()
   with self.assertRaises(host.Blocked):host.execute(c,AUTH,'e0.setup_mandate_consume',['i','corr'],timeout_ms=value)
   self.assertTrue(c.closed)
 def test_reply_guard_holds_authority_until_send_finishes(self):
  engine=str(uuid4());attempt=str(uuid4());request=str(uuid4());receipt=str(uuid4());events=[]
  binding=EngineBinding(engine_session_id=engine,attempt_id=attempt,fencing_epoch=1,revision=0,tool_manifest_digest='a'*64)
  class Scope:
   @contextlib.contextmanager
   def open(self,operation):
    self.operation=operation;events.append('BEGIN');yield self;events.append('COMMIT')
   def execute(self,sql,args):self.sql=sql;self.args=args
   def fetchone(self):return ({'receipt_id':receipt,'request_id':request,'engine_session_id':engine},)
  scope=Scope();guard=EngineReplyGuard(scope=scope,binding=binding);reply=ToolReply(protocol='company-tool/1',request_id=request,status='OK',receipt_id=receipt,artifact_ids=[],error_code=None)
  with guard(reply):events.append('SEND')
  self.assertEqual(events,['BEGIN','SEND','COMMIT']);self.assertEqual(scope.operation,'candidate.r58.artifacts.read');self.assertEqual(scope.args,(receipt,))
if __name__=='__main__':unittest.main()


class ConstructorReadbackTests(unittest.TestCase):
 def test_native_readback_does_not_execute_constructor(self):
  command_id=str(uuid4())
  class ReaderCursor(Cursor):
   def fetchone(self):
    if 'r63_constructor_result(' in self.c.last:
     return (dict(command_id=command_id,state='SUCCEEDED',result_payload={'id':'fixture'}),)
    return super().fetchone()
  class ReaderConnection(C):
   def cursor(self):return ReaderCursor(self)
  c=ReaderConnection()
  result=host.execute(c,AUTH,'objectives.create',[],read_command_id=command_id)
  self.assertEqual(result['command_receipt']['command_id'],command_id)
  self.assertFalse(any('r53_objectives_create(' in sql for sql,_ in c.calls))
  self.assertEqual(sum('r63_constructor_result(' in sql for sql,_ in c.calls),1)
  self.assertTrue(c.closed)
 def test_readback_invalid_operation_id_or_args_closes_before_sql(self):
  for operation,args,identifier in [('worker.claim',[],str(uuid4())),('objectives.create',[],'bad'),('tasks.create',['injected'],str(uuid4()))]:
   c=C()
   with self.subTest(operation=operation),self.assertRaises(host.Blocked):
    host.execute(c,AUTH,operation,args,read_command_id=identifier)
   self.assertTrue(c.closed)
   self.assertFalse(any('context_enter' in sql for sql,_ in c.calls))
 def test_emission_preflight_errors_close_connection_without_sql_or_send(self):
  for payload in ({'operation':'unregistered'}, {'operation':'objectives.create','result':{'bad':object()},'snapshot':{}}):
   c=C()
   with self.assertRaises((host.Blocked,TypeError)):
    host.emit(c,AUTH,payload,None,1)
   self.assertTrue(c.closed)
   self.assertEqual(c.calls,[])


class ReceiptEmissionFailureTests(unittest.TestCase):
 def test_revocation_before_send_closes_and_never_sends_bytes(self):
  class RevokedCursor(Cursor):
   def fetchone(self):
    if 'r58_emission_check(' in self.c.last:return (False,)
    return super().fetchone()
  class RevokedConnection(C):
   def cursor(self):return RevokedCursor(self)
  class Socket:
   def settimeout(self,value):pass
   def sendall(self,value):raise AssertionError('Revoked response must not be sent')
  c=RevokedConnection()
  envelope=dict(operation='objectives.create',result={'id':'fixture'},snapshot={'epoch':1})
  with self.assertRaises(host.UnknownCommitOutcome):host.emit(c,AUTH,envelope,Socket(),1)
  self.assertTrue(c.closed)
  self.assertIn(('ROLLBACK',()),c.calls)
 def test_wrong_native_command_id_never_releases_readback(self):
  c=C()
  with self.assertRaises(host.Blocked):
   host.execute(c,AUTH,'objectives.create',[],read_command_id=str(uuid4()))
  self.assertTrue(c.closed)
  self.assertNotIn(('COMMIT',()),c.calls)
 def test_per_operation_grant_ids_binding_and_missing_operation_rejected(self):
  auth=dict(AUTH,grant_ids={'e0.setup_mandate_consume':'grant-op-1'})
  c=C()
  host.execute(c,auth,'e0.setup_mandate_consume',['i','corr'])
  enter_args=next(a for s,a in c.calls if 'r54_context_enter' in s)
  self.assertEqual(enter_args[-1],'grant-op-1')
  self.assertTrue(c.closed)
  c_missing=C()
  with self.assertRaises(host.Blocked):
   host.execute(c_missing,auth,'plans.create',['{}'])
  self.assertTrue(c_missing.closed)
  self.assertNotIn(('COMMIT',()),c_missing.calls)
  c_bad=C()
  with self.assertRaises(host.Blocked):
   host.execute(c_bad,dict(AUTH,grant_ids='not-a-dict'),'plans.create',['{}'])
  self.assertTrue(c_bad.closed)
