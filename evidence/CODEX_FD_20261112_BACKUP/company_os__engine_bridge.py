"""Bounded engine transport. No process launch, DB connection or provider call.

The Linux parent receives pipes only from the enrolled launcher. TCP/socketpair
transport exists for offline wire tests; it is not OS isolation evidence.
"""
import base64,json,math,os,selectors,socket,stat,sys,time
from .execution_protocol import Denied,Unknown,canonical,exact
from packages.contracts.execution import no_duplicate_keys

class FrameBuffer:
 def __init__(self,max_frame_bytes=65536):
  if type(max_frame_bytes) is not int or not 1<=max_frame_bytes<=65536:raise Denied('FINITE_FRAME_LIMIT_REQUIRED')
  self.limit=max_frame_bytes;self.pending=bytearray()
 def append(self,chunk):
  if type(chunk) is not bytes or not chunk:raise Denied('NONEMPTY_BYTES_REQUIRED')
  # One bounded frame is buffered; callers read at most remaining room.
  if len(self.pending)+len(chunk)>self.limit:raise Denied('ENGINE_FRAME_TOO_LARGE')
  self.pending.extend(chunk)
 def pop(self):
  index=self.pending.find(b'\n')
  if index<0:
   if len(self.pending)==self.limit:raise Denied('UNTERMINATED_FRAME_LIMIT')
   return None
  result=bytes(self.pending[:index+1]);del self.pending[:index+1];return result
 def eof(self):
  if self.pending:raise Denied('TRUNCATED_ENGINE_FRAME')

class SocketTransport:
 """An explicitly supplied connected stream; no network socket is created."""
 def __init__(self,stream):self.stream=stream
 def read(self,size,timeout):self.stream.settimeout(timeout);return self.stream.recv(size)
 def write(self,data,timeout):self.stream.settimeout(timeout);self.stream.sendall(data)
 def close(self):self.stream.close()

class PipeTransport:
 @classmethod
 def from_observation(cls,observation):
  """Transfer only parent pipe ownership from a trusted launcher observation."""
  keys=['engine_stdout_fd','engine_stdin_fd','engine_stderr_fd'];fds=[observation[k] for k in keys]
  if observation.get('state')!='CREATED_NOT_EXEC_ATTESTED' or len(set(fds))!=3 or any(type(fd) is not int or fd<3 for fd in fds):raise Denied('EXACT_PARENT_PIPE_OBSERVATION_REQUIRED')
  try:return cls(stdout_fd=fds[0],stdin_fd=fds[1],stderr_fd=fds[2])
  finally:
   for fd in fds:os.close(fd)
 def __init__(self,*,stdout_fd,stdin_fd,stderr_fd,max_stderr_bytes=16384):
  if sys.platform!='linux':raise Denied('LINUX_PIPE_TRANSPORT_REQUIRED')
  if type(max_stderr_bytes) is not int or not 0<=max_stderr_bytes<=16384:raise Denied('FINITE_STDERR_LIMIT_REQUIRED')
  self.fds=[];self.stderr_bytes=0;self.stderr_limit=max_stderr_bytes;self.stderr_eof=False
  try:
   for fd in [stdout_fd,stdin_fd,stderr_fd]:
    if type(fd) is not int or fd<0 or not stat.S_ISFIFO(os.fstat(fd).st_mode):raise Denied('ENROLLED_PIPE_FD_REQUIRED')
    duplicate=os.dup(fd);self.fds.append(duplicate);os.set_blocking(duplicate,False)
   if len({(os.fstat(fd).st_dev,os.fstat(fd).st_ino) for fd in self.fds})!=3:raise Denied('DISTINCT_ENGINE_PIPES_REQUIRED')
  except Exception:self.close();raise
 def _ready(self,event,timeout):
  with selectors.DefaultSelector() as selector:
   selector.register(self.fds[0] if event==selectors.EVENT_READ else self.fds[1],event,'primary')
   if not self.stderr_eof:selector.register(self.fds[2],selectors.EVENT_READ,'stderr')
   ready=selector.select(timeout)
   if not ready:raise TimeoutError('ENGINE_PIPE_DEADLINE')
   primary=False
   for key,mask in ready:
    if key.data=='primary':primary=True
    else:
     data=os.read(self.fds[2],min(4096,self.stderr_limit-self.stderr_bytes+1))
     self.stderr_bytes+=len(data)
     if self.stderr_bytes>self.stderr_limit:raise Denied('ENGINE_STDERR_LIMIT')
     if not data:self.stderr_eof=True
   return primary
 def read(self,size,timeout):
  deadline=time.monotonic()+timeout
  while True:
   left=deadline-time.monotonic()
   if left<=0:raise TimeoutError('ENGINE_PIPE_DEADLINE')
   if self._ready(selectors.EVENT_READ,left):
    try:return os.read(self.fds[0],size)
    except BlockingIOError:pass
 def write(self,data,timeout):
  deadline=time.monotonic()+timeout;view=memoryview(data)
  while view:
   left=deadline-time.monotonic()
   if left<=0:raise TimeoutError('ENGINE_PIPE_DEADLINE')
   if self._ready(selectors.EVENT_WRITE,left):
    try:
     n=os.write(self.fds[1],view)
     if n<=0:raise BrokenPipeError('ENGINE_PIPE_CLOSED')
     view=view[n:]
    except BlockingIOError:pass
 def close(self):
  for fd in getattr(self,'fds',[]):
   try:os.close(fd)
   except OSError:pass
  self.fds=[]

class ProducerOutputAdapter:
 """First pilot: one bounded replacement proposal from the model, no oracle.

 The trusted adapter stages the bytes and creates company-tool/1 binding fields.
 The model cannot choose artifact UUIDs, attempt IDs, fences or credentials.
 """
 def __init__(self,*,producer,broker):self.producer=producer;self.broker=broker;self.used=False
 def handle(self,frame,*,channel):
  if self.used or channel!='BOUND_ENGINE_STDOUT':raise Denied('ONE_BOUND_PRODUCER_OUTPUT_REQUIRED')
  self.used=True
  if type(frame) is not bytes or len(frame)>32768 or not frame.endswith(b'\n') or b'\n' in frame[:-1]:raise Denied('PRODUCER_FRAME_LIMIT')
  value=json.loads(frame.decode('utf-8'),object_pairs_hook=no_duplicate_keys,parse_constant=lambda _:(_ for _ in ()).throw(Denied('NONFINITE_JSON')))
  exact(value,{'protocol','action','replacement_base64'})
  if value['protocol']!='company.producer-output/1' or value['action']!='replace' or type(value['replacement_base64']) is not str:raise Denied('PILOT_PRODUCER_FORMAT')
  raw=base64.b64decode(value['replacement_base64'],validate=True)
  if base64.b64encode(raw).decode()!=value['replacement_base64']:raise Denied('CANONICAL_BASE64_REQUIRED')
  request=self.producer.frame(raw,sequence=self.broker.sequence)
  return self.broker.handle(request,channel='BOUND_ENGINE_STDOUT')

class EnginePump:
 """No automatic retry on malformed output, uncertain effects or partial writes.

 Replies pass an emission guard that holds the current authorization scope
 across the bounded write. This does not retract previously transmitted bytes.
 """
 def __init__(self,*,transport,handler,emission_guard,stop_request,lease_remaining,timeout,max_frames=16,clock=time.monotonic):
  if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=60:raise Denied('FINITE_PUMP_TIMEOUT_REQUIRED')
  if type(max_frames) is not int or not 1<=max_frames<=16:raise Denied('FINITE_FRAME_COUNT_REQUIRED')
  self.transport=transport;self.handler=handler;self.emission=emission_guard;self.stop=stop_request;self.lease=lease_remaining;self.clock=clock;self.deadline=clock()+timeout;self.max_frames=max_frames;self.used=False
 def remaining(self):
  lease=self.lease()
  if type(lease) not in (int,float) or not math.isfinite(lease) or lease<=0:raise Denied('ENGINE_LEASE_EXPIRED')
  remaining=min(self.deadline-self.clock(),lease)
  if remaining<=0:raise TimeoutError('TOTAL_ENGINE_DEADLINE')
  return remaining
 def run(self):
  if self.used:raise Unknown('PUMP_CANNOT_RESUME_OR_RESEND')
  self.used=True;buffer=FrameBuffer();count=0;outcome='UNKNOWN_RECOVERY'
  try:
   while count<self.max_frames:
    frame=buffer.pop()
    if frame is None:
     data=self.transport.read(min(4096,buffer.limit-len(buffer.pending)),self.remaining())
     if not data:buffer.eof();outcome='EOF_NOT_VERIFIED';return dict(outcome=outcome,frames=count)
     buffer.append(data);continue
    self.remaining();reply=self.handler.handle(frame,channel='BOUND_ENGINE_STDOUT');count+=1
    encoded=canonical(reply.model_dump(mode='json'))+b'\n'
    if len(encoded)>65536:raise Denied('REPLY_FRAME_LIMIT')
    if reply.status=='OK':
     with self.emission(reply):self.transport.write(encoded,min(1.0,self.remaining()))
    else:
     # No result bytes escape on denied/stale/unknown output; supervisor reconciles.
     raise Unknown('ENGINE_RESULT_NOT_RELEASED')
    if isinstance(self.handler,ProducerOutputAdapter):
     outcome='PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED';return dict(outcome=outcome,frames=count)
   raise Denied('ENGINE_FRAME_COUNT_LIMIT')
  except Exception:raise Unknown('ENGINE_CHANNEL_OUTCOME_RECONCILE_NO_RETRY') from None
  finally:
   try:
    try:self.stop(outcome)
    except Exception:raise Unknown('ENGINE_STOP_REQUEST_NOT_CONFIRMED') from None
   finally:self.transport.close()

from .reply_guard import EngineReplyGuard

class PumpLimits:
    def __init__(self, *, max_frame_bytes=16384, max_frames=1, idle_timeout_ms=5000, total_timeout_ms=10000):
        self.max_frame_bytes = max_frame_bytes
        self.max_frames = max_frames
        self.idle_timeout_ms = idle_timeout_ms
        self.total_timeout_ms = total_timeout_ms
