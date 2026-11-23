"""Offline adapter tests. DB-API doubles are never PostgreSQL acceptance."""
import base64,contextlib,copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from company_os.kernel import command_host as host, kernel_adapters as adapters
from company_os.workspace import patch_pipeline as pipeline
from company_os.broker import tool_broker
from packages.contracts.execution import EngineBinding, parse_tool_request
def uid():return str(uuid4())
def digest(raw):return hashlib.sha256(raw).hexdigest()
SOURCE=b'def normalize_title(value):\n    return value.strip()\n'
CANDIDATE=b'def normalize_title(value):\n    return " ".join(value.split())\n'
class Cursor:
 def __init__(self,c):self.c=c
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def execute(self,sql,args=()):
  c=self.c;h=c.h;h.events.append((c.id,sql,args));c.row={}
  if 'r54_context_enter(' in sql:c.operation=args[1];c.row='nonce';return
  if 'r58_emission_snapshot' in sql:c.row={'project_epoch':1};return
  if 'r58_attestation_ingest(' in sql:
   identity,issuer,key,revision,profile,raw,tag,*_=args
   statement=json.loads(raw);h.statements[identity]=statement
   h.stage_calls+=1;c.row=h.sealed({'receipt_id':identity},identity);return
  if 'r58_tool_authorize_final(' in sql:
   h.kernel_request=uid();c.row=h.sealed({'request_id':h.kernel_request});return
  if 'r60_tool_consume(' in sql:
   frame=args[1];h.request=json.loads(frame);h.frame_digest=digest(frame);h.frame=frame;h.consume=uid()
   c.row=h.sealed(dict(consume_id=h.consume,effect_permitted=True,frame_digest=h.frame_digest));return
  if 'r65_effect_guard(' in sql:
   fb64=base64.b64encode(h.frame).decode()
   if h.wrap_frame_b64:fb64='\n'.join(fb64[i:i+76] for i in range(0,len(fb64),76))+'\n'
   h.guard=dict(consume_id=h.consume,frame_digest=h.frame_digest,frame_base64=fb64,process_id=h.process,base_head=digest(SOURCE),task_id=h.task,attempt_id=h.attempt,fencing_epoch=1,engine_session_id=h.engine,tool_manifest_digest='a'*64,sequence=1,request_id=h.request['request_id'],kernel_request_id=h.kernel_request)
   c.row=h.guard;return
  if 'r65_patch_artifact_read(' in sql:
   h.reader_connection=c.id;h.reader_operation=c.operation
   statement=h.statements[args[1]];p=statement['binding'];raw=base64.b64decode(p['artifact_base64']);v=json.loads(raw)
   c.row=dict(artifact_id=args[1],consume_id=h.consume,frame_digest=h.frame_digest,kind='BOUND_PATCH_PROPOSAL_NOT_VERIFICATION',content_base64=p['artifact_base64'],sha256=p['artifact_digest'],base_content_digest=v['base_content_digest'],replacement_content_digest=digest(base64.b64decode(v['replacement_base64'])))
   if h.tamper_read:c.row['frame_digest']='f'*64
   return
  if 'r60_effect_finish(' in sql:
   h.effect_connection=c.id;h.effect_id=args[1];h.effect=json.loads(args[4]);h.effect_writes+=1
   c.row=h.sealed(dict(status='SUCCEEDED',receipt_id=h.effect_id,consume_id=h.consume,frame_digest=h.frame_digest,artifact_ids=[h.effect_id]));return
  if 'r58_patch_receipt(' in sql:
   if not h.effect_committed:raise AssertionError('patch receipt before effect commit')
   h.patch_writes+=1
   patch=h.statements[args[3]]['binding']
   c.row=h.sealed(dict(patch_id=args[3],result_head=digest(CANDIDATE),patch_digest=patch['patch_digest'],attestation=args[3]));return
 def fetchone(self):return (self.c.row,)
class Connection:
 def __init__(self,h):self.h=h;h.next_id+=1;self.id=h.next_id;self.info=SimpleNamespace(transaction_status=0);self.operation=None;self.row=None;self.closed=False
 def cursor(self):return Cursor(self)
 def commit(self):
  self.h.events.append((self.id,'COMMIT',self.operation))
  if self.operation=='tool.effect':self.h.effect_committed=True
  if self.operation=='patch.receipt':self.h.patch_committed=True
  if self.h.fail_commit==self.operation:raise OSError('lost commit acknowledgement')
 def rollback(self):self.h.events.append((self.id,'ROLLBACK',self.operation))
 def close(self):self.closed=True
class PortableFixtureExecutor:
 """Test-only file effect; has no production Linux isolation claim."""
 def __init__(self,h,root):self.h=h;self.root=Path(root);(self.root/'task_title.py').write_bytes(SOURCE)
 def execute(self,call,*,transaction):
  artifact=transaction.read_patch(call.patch_artifact_id);base,data=pipeline.replacement(artifact['raw'],artifact['sha256'])
  file=self.root/'task_title.py';old=file.read_bytes()
  if digest(old)!=base:raise ValueError('CAS failed')
  stage=self.root/'candidate.stage';stage.write_bytes(data);stage.replace(file);self.h.file_writes+=1
  return dict(kind='PATCH',base_head=digest(old),result_head=digest(data),base_content_digest=base,result_content_digest=digest(data),patch_digest=artifact['sha256'])
class Harness:
 def __init__(self,root):
  self.tenant=uid();self.project=uid();self.task=uid();self.attempt=uid();self.engine=uid();self.process=uid();self.controller=uid()
  self.binding=EngineBinding(engine_session_id=self.engine,attempt_id=self.attempt,fencing_epoch=1,revision=0,tool_manifest_digest='a'*64)
  self.auth=dict(token='fixture-only-not-real-credential',project_id=self.project,kind='ATTEMPT',resource_id=self.attempt,task_id=self.task,attempt_id=self.attempt,fence=1,grant_id=uid())
  self.events=[];self.next_id=0;self.statements={};self.stage_calls=0;self.effect_writes=0;self.patch_writes=0;self.file_writes=0;self.effect_committed=False;self.patch_committed=False;self.fail_commit=None;self.tamper_read=False;self.wrap_frame_b64=False
  def signer():return adapters.ProofSigner(issuer_id=self.controller,key_id=uid(),revision=1,key=b'x'*32,tenant_id=self.tenant,project_id=self.project)
  self.proposal_signer=signer();self.effect_signer=signer();self.patch_signer=signer()
  self.producer=pipeline.PatchProposalProducer(connect=self.connect,controller_auth=self.auth,signer=self.proposal_signer,binding=self.binding,process_id=self.process,source_snapshot=lambda:dict(head_digest=digest(SOURCE),source_bytes=SOURCE))
  recorder=pipeline.PatchReceiptRecorder(connect=self.connect,controller_auth=self.auth,worker_auth=self.auth,patch_signer=self.patch_signer)
  self.kernel=pipeline.ToolKernel(connect=self.connect,worker_auth=self.auth,controller_scope=adapters.DbScope(self.connect,self.auth),process_id=self.process,signer=self.effect_signer,patch_recorder=recorder)
  self.executor=PortableFixtureExecutor(self,root);self.intents=set()
  self.broker=tool_broker.Broker(binding=self.binding,kernel=self.kernel,journal=self,executor=self.executor)
 def connect(self):return Connection(self)
 def sealed(self,payload,target=None):return dict(command_id=uid(),state='SUCCEEDED',result_ref=target or uid(),result_payload=payload)
 def reserve(self,key,record):
  if key in self.intents:raise FileExistsError()
  self.intents.add(key)
 def run(self):return self.broker.handle(self.producer.frame(CANDIDATE,sequence=1),channel='BOUND_ENGINE_STDOUT')
class PipelineTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parent/'test-tmp';root.mkdir(exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup);self.h=Harness(self.temp.name)
 def test_stage_consume_same_transaction_read_effect_commit_then_patch_receipt(self):
  h=self.h;reply=h.run();self.assertEqual(reply.status,'OK');self.assertTrue(h.patch_committed)
  self.assertEqual(h.reader_operation,'tool.effect');self.assertEqual(h.reader_connection,h.effect_connection)
  self.assertEqual((Path(self.temp.name)/'task_title.py').read_bytes(),CANDIDATE)
  self.assertEqual((h.effect_writes,h.patch_writes,h.file_writes),(1,1,1));self.assertEqual(h.broker.sequence,2)
  order=[sql for _,sql,_ in h.events]
  finish=next(i for i,s in enumerate(order) if 'r60_effect_finish' in s);receipt=next(i for i,s in enumerate(order) if 'r58_patch_receipt' in s)
  self.assertTrue(any(order[i]=='COMMIT' for i in range(finish+1,receipt)))
 def test_lost_effect_commit_ack_halts_without_patch_record_or_second_write(self):
  h=self.h;h.fail_commit='tool.effect';reply=h.run();self.assertEqual(reply.status,'UNKNOWN_RECOVERY');self.assertTrue(h.broker.halted)
  self.assertEqual((h.file_writes,h.patch_writes),(1,0))
  with self.assertRaises(tool_broker.RecoveryRequired):h.broker.handle(h.frame,channel='BOUND_ENGINE_STDOUT')
  self.assertEqual(h.file_writes,1)
 def test_lost_patch_receipt_ack_never_reapplies_file(self):
  h=self.h;h.fail_commit='patch.receipt';reply=h.run();self.assertEqual(reply.status,'UNKNOWN_RECOVERY');self.assertEqual(h.file_writes,1);self.assertEqual(h.patch_writes,1)
 def test_forged_patch_readback_stops_before_filesystem_write(self):
  h=self.h;h.tamper_read=True;reply=h.run();self.assertEqual(reply.status,'UNKNOWN_RECOVERY');self.assertEqual(h.file_writes,0);self.assertEqual(h.effect_writes,0)
 def test_stage_uncertainty_cannot_retry(self):
  h=self.h;h.fail_commit='evidence.attestation_ingest'
  with self.assertRaises(pipeline.Unknown):h.producer.frame(CANDIDATE,sequence=1)
  with self.assertRaises(pipeline.Unknown):h.producer.frame(CANDIDATE,sequence=1)
  self.assertEqual(h.stage_calls,1);self.assertEqual(h.file_writes,0)
 def test_source_binary_oversize_and_invalid_utf8_do_not_stage(self):
  for raw in [b'\0',b'x'*16385,b'\xff']:
   with self.assertRaises((pipeline.Denied,UnicodeError)):self.h.producer.frame(raw,sequence=1)
  self.assertEqual(self.h.stage_calls,0)
 def test_proposal_is_exact_request_stream_and_head_bound(self):
  h=self.h;frame=h.producer.frame(CANDIDATE,sequence=1);request=parse_tool_request(frame,binding=h.binding,expected_sequence=1,channel='BOUND_ENGINE_STDOUT')
  p=h.statements[str(request.call.patch_artifact_id)]['binding']
  self.assertEqual(p['request_id'],str(request.request_id));self.assertEqual(p['expected_source_digest'],digest(SOURCE));self.assertEqual(p['engine_session_id'],h.engine)
  self.assertNotIn('oracle',json.dumps(p));self.assertEqual(p['artifact_digest'],digest(base64.b64decode(p['artifact_base64'])))
 def test_patch_receipt_signed_self_reference_and_separate_profile(self):
  h=self.h;h.run();proof=[(k,v) for k,v in h.statements.items() if v['profile']=='r58.patch.v1']
  self.assertEqual(len(proof),1);identity,statement=proof[0];self.assertEqual(identity,statement['binding']['receipt_artifact_id']);self.assertEqual(statement['binding']['tool_request_id'],h.kernel_request)
 def test_invalid_frame_halts_before_any_kernel_command(self):
  h=self.h
  with self.assertRaises(tool_broker.RecoveryRequired):h.broker.handle(b'bad\n',channel='BOUND_ENGINE_STDOUT')
  self.assertTrue(h.broker.halted);self.assertEqual(h.events,[])
 def test_expired_transaction_reader_is_unusable(self):
  tx=pipeline.PatchEffectTransaction(None,{},None,object());tx.active=False
  with self.assertRaises(pipeline.Denied):tx.read_patch(uid())
 def test_uncommitted_transaction_cannot_record_patch(self):
  tx=pipeline.PatchEffectTransaction(None,{},None,self.h.kernel)
  with self.assertRaises(pipeline.Denied):self.h.kernel.finalize_patch(tx)
 def test_relative_imports_ignore_ambient_command_host(self):
  with patch.dict(sys.modules,{'command_host':SimpleNamespace(execute=lambda *a:None)}):
   self.assertIs(adapters.host,host);self.assertIs(pipeline.host,host)
 def test_model_output_through_pump_to_file_and_recorded_patch(self):
  from company_os.engine.engine_bridge import ProducerOutputAdapter, EnginePump
  h=self.h;wire=json.dumps(dict(protocol='company.producer-output/1',action='replace',replacement_base64=base64.b64encode(CANDIDATE).decode())).encode()+b'\n';events=[]
  class Transport:
   def __init__(self):self.chunks=[wire[:15],wire[15:]];self.writes=[];self.closed=False
   def read(self,size,timeout):return self.chunks.pop(0) if self.chunks else b''
   def write(self,data,timeout):
    if not h.patch_committed:raise AssertionError('engine reply before patch commit')
    events.append('SEND');self.writes.append(data)
   def close(self):self.closed=True
  @contextlib.contextmanager
  def emission(reply):events.append('AUTH_BEGIN');yield;events.append('AUTH_COMMIT')
  transport=Transport();handler=ProducerOutputAdapter(producer=h.producer,broker=h.broker)
  pump=EnginePump(transport=transport,handler=handler,emission_guard=emission,stop_request=lambda reason:events.append(reason),lease_remaining=lambda:2,timeout=2,max_frames=1)
  result=pump.run()
  self.assertEqual(result['outcome'],'PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED');self.assertEqual(events,['AUTH_BEGIN','SEND','AUTH_COMMIT','PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED'])
  self.assertEqual(json.loads(transport.writes[0])['status'],'OK');self.assertTrue(transport.closed);self.assertEqual(h.file_writes,1)
 def test_model_output_unknown_patch_commit_has_no_engine_reply(self):
  from company_os.engine.engine_bridge import ProducerOutputAdapter, EnginePump
  h=self.h;h.fail_commit='patch.receipt';wire=json.dumps(dict(protocol='company.producer-output/1',action='replace',replacement_base64=base64.b64encode(CANDIDATE).decode())).encode()+b'\n';sent=[];stops=[]
  class Transport:
   def read(self,size,timeout):return wire
   def write(self,data,timeout):sent.append(data)
   def close(self):pass
  @contextlib.contextmanager
  def emission(reply):yield
  pump=EnginePump(transport=Transport(),handler=ProducerOutputAdapter(producer=h.producer,broker=h.broker),emission_guard=emission,stop_request=stops.append,lease_remaining=lambda:2,timeout=2,max_frames=1)
  with self.assertRaises(pipeline.Unknown):pump.run()
  self.assertEqual(sent,[]);self.assertEqual(h.file_writes,1);self.assertEqual(stops,['UNKNOWN_RECOVERY'])
 def test_pg_multiline_base64_frame_in_effect_guard_is_accepted(self):
  h=self.h;h.wrap_frame_b64=True;reply=h.run()
  self.assertEqual(reply.status,'OK');self.assertTrue(h.patch_committed);self.assertEqual(h.file_writes,1)
if __name__=='__main__':unittest.main()
