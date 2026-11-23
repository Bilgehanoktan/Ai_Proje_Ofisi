import base64,contextlib,json,os,socket,sys,threading,time,unittest
from types import SimpleNamespace
from uuid import uuid4
from company_os.engine.engine_bridge import FrameBuffer, EnginePump, ProducerOutputAdapter, PipeTransport, SocketTransport, Denied, Unknown
from company_os.engine.reply_guard import EngineReplyGuard
from packages.contracts.execution import ToolReply, EngineBinding
def reply():return ToolReply(protocol='company-tool/1',request_id=uuid4(),status='OK',receipt_id=uuid4(),artifact_ids=[],error_code=None)
class Transport:
 def __init__(self,chunks):self.chunks=list(chunks);self.writes=[];self.closed=False;self.reads=0;self.fail=False
 def read(self,size,timeout):
  self.reads+=1
  if not self.chunks:return b''
  chunk=self.chunks.pop(0)
  if len(chunk)>size:self.chunks.insert(0,chunk[size:]);chunk=chunk[:size]
  return chunk
 def write(self,data,timeout):
  self.writes.append(data)
  if self.fail:raise OSError('partial write uncertainty')
 def close(self):self.closed=True
class Handler:
 def __init__(self):self.frames=[];self.answer=reply()
 def handle(self,frame,*,channel):self.frames.append((frame,channel));return self.answer
class PumpTests(unittest.TestCase):
 def setUp(self):self.stops=[];self.events=[]
 @contextlib.contextmanager
 def guard(self,reply):self.events.append('ENTER');yield;self.events.append('COMMIT')
 def pump(self,transport,handler=None,**kwargs):return EnginePump(transport=transport,handler=handler or Handler(),emission_guard=self.guard,stop_request=self.stops.append,lease_remaining=kwargs.pop('lease_remaining',lambda:1),timeout=kwargs.pop('timeout',1),**kwargs)
 def test_fragmented_frames_and_coalesced_lines_preserve_boundaries(self):
  t=Transport([b'{"a"',b':1}\n{"b":',b'2}\n']);h=Handler();outcome=self.pump(t,h).run()
  self.assertEqual([f for f,c in h.frames],[b'{"a":1}\n',b'{"b":2}\n']);self.assertEqual(len(t.writes),2);self.assertEqual(self.events,['ENTER','COMMIT','ENTER','COMMIT']);self.assertTrue(t.closed);self.assertEqual(outcome['outcome'],'EOF_NOT_VERIFIED')
 def test_max_frame_without_newline_halts_before_handler(self):
  t=Transport([b'x'*65536]);h=Handler()
  with self.assertRaises(Unknown):self.pump(t,h).run()
  self.assertEqual(h.frames,[]);self.assertEqual(t.writes,[]);self.assertTrue(t.closed);self.assertEqual(self.stops,['UNKNOWN_RECOVERY'])
 def test_truncated_eof_never_dispatches(self):
  t=Transport([b'{"a":1}']);h=Handler()
  with self.assertRaises(Unknown):self.pump(t,h).run()
  self.assertEqual(h.frames,[])
 def test_denied_reply_has_no_engine_visible_result(self):
  t=Transport([b'{}\n']);h=Handler();h.answer=h.answer.model_copy(update={'status':'DENIED','receipt_id':None})
  with self.assertRaises(Unknown):self.pump(t,h).run()
  self.assertEqual(t.writes,[])
 def test_partial_write_never_resends_or_restarts(self):
  t=Transport([b'{}\n']);t.fail=True;h=Handler();p=self.pump(t,h)
  with self.assertRaises(Unknown):p.run()
  with self.assertRaises(Unknown):p.run()
  self.assertEqual(len(h.frames),1);self.assertEqual(len(t.writes),1)
 def test_expired_lease_does_not_read_or_write(self):
  t=Transport([b'{}\n'])
  with self.assertRaises(Unknown):self.pump(t,lease_remaining=lambda:0).run()
  self.assertEqual(t.reads,0);self.assertEqual(t.writes,[])
 def test_total_deadline_cannot_be_extended_by_fragments(self):
  ticks=iter([0,0.1,0.2,2]);t=Transport([b'{',b'}',b'\n'])
  with self.assertRaises(Unknown):self.pump(t,clock=lambda:next(ticks)).run()
  self.assertEqual(t.writes,[])
 def test_frame_count_limit_stops_without_extra_dispatch(self):
  t=Transport([b'{}\n{}\n']);h=Handler()
  with self.assertRaises(Unknown):self.pump(t,h,max_frames=1).run()
  self.assertEqual(len(h.frames),1)
 def test_current_authorization_failure_releases_zero_bytes(self):
  @contextlib.contextmanager
  def revoked(reply):raise ValueError('revoked');yield
  t=Transport([b'{}\n']);p=self.pump(t);p.emission=revoked
  with self.assertRaises(Unknown):p.run()
  self.assertEqual(t.writes,[])
 def test_configuration_rejects_nonfinite_and_boolean_limits(self):
  for value in [True,0,float('nan'),float('inf'),61]:
   with self.assertRaises(Denied):self.pump(Transport([]),timeout=value)
 @unittest.skipUnless(sys.platform=='linux','Windows sandbox socketpair setup stalled; actual local-wire acceptance not verified')
 def test_real_socketpair_fragmentation_and_bounded_reply(self):
  left,right=socket.socketpair();self.addCleanup(right.close);right.settimeout(2);transport=SocketTransport(left);h=Handler();seen=[]
  def engine():
   right.sendall(b'{');right.sendall(b'}\n');seen.append(right.recv(4096));right.shutdown(socket.SHUT_WR)
  thread=threading.Thread(target=engine);thread.start()
  try:result=self.pump(transport,h).run()
  finally:thread.join(2)
  self.assertFalse(thread.is_alive());self.assertEqual(len(h.frames),1);self.assertEqual(json.loads(seen[0])['status'],'OK');self.assertEqual(result['frames'],1)

class ProducerTests(unittest.TestCase):
 def setUp(self):
  self.calls=[];self.producer=SimpleNamespace(frame=lambda data,sequence:self.calls.append((data,sequence)) or b'company-tool-frame\n');self.broker=SimpleNamespace(sequence=1,handle=lambda f,channel:reply())
 def wire(self,**kwargs):
  value=dict(protocol='company.producer-output/1',action='replace',replacement_base64=base64.b64encode(b'candidate').decode());value.update(kwargs);return json.dumps(value).encode()+b'\n'
 def test_only_replacement_bytes_reach_trusted_stager(self):
  a=ProducerOutputAdapter(producer=self.producer,broker=self.broker);self.assertEqual(a.handle(self.wire(),channel='BOUND_ENGINE_STDOUT').status,'OK');self.assertEqual(self.calls,[(b'candidate',1)])
  with self.assertRaises(Denied):a.handle(self.wire(),channel='BOUND_ENGINE_STDOUT')
 def test_extra_credential_or_approval_fields_are_rejected(self):
  a=ProducerOutputAdapter(producer=self.producer,broker=self.broker)
  with self.assertRaises(Denied):a.handle(self.wire(verified=True),channel='BOUND_ENGINE_STDOUT')
  self.assertEqual(self.calls,[])
 def test_duplicate_json_keys_never_stage(self):
  a=ProducerOutputAdapter(producer=self.producer,broker=self.broker)
  with self.assertRaises(ValueError):a.handle(self.wire().replace(b'"action": "replace"',b'"action":"replace","action":"replace"'),channel='BOUND_ENGINE_STDOUT')
  self.assertEqual(self.calls,[])
 def test_unbound_channel_is_rejected(self):
  a=ProducerOutputAdapter(producer=self.producer,broker=self.broker)
  with self.assertRaises(Denied):a.handle(self.wire(),channel='UNTRUSTED_STDERR')
  self.assertEqual(self.calls,[])

class PipeTests(unittest.TestCase):
 @unittest.skipUnless(sys.platform=='linux','Linux FIFO/selectors acceptance cannot run on Windows')
 def test_actual_pipes_and_ownership_transfer(self):
  cin,pin=os.pipe2(os.O_CLOEXEC);pout,cout=os.pipe2(os.O_CLOEXEC);perr,cerr=os.pipe2(os.O_CLOEXEC)
  observation=dict(state='CREATED_NOT_EXEC_ATTESTED',engine_stdout_fd=pout,engine_stdin_fd=pin,engine_stderr_fd=perr)
  transport=PipeTransport.from_observation(observation)
  try:
   os.write(cout,b'{}\n');self.assertEqual(transport.read(10,1),b'{}\n');transport.write(b'OK\n',1);self.assertEqual(os.read(cin,10),b'OK\n')
   for fd in [pout,pin,perr]:
    with self.assertRaises(OSError):os.fstat(fd)
  finally:
   transport.close()
   for fd in [cin,cout,cerr]:os.close(fd)
if __name__=='__main__':unittest.main()
