"""Canonical assembly for an already-enrolled pilot, never a launcher/enroller.

All credentials, pinned source measurements, lease and stop ports come from the
trusted supervisor. Construction starts no DB/model/service. Domain writes use
CommandHost, file effects use Broker; verification/acceptance stay separate.
"""
import copy
import inspect
import os
import stat
import sys
import threading
from uuid import UUID

from packages.contracts.execution import EngineBinding
from .execution_protocol import Denied, Unknown
from .kernel_adapters import DbScope
from .patch_pipeline import PatchProposalProducer, PatchReceiptRecorder, ToolKernel
from .tool_executor import LinuxSingleFileExecutor, ToolIntentJournal
from .tool_broker import Broker
from .engine_bridge import EnginePump, ProducerOutputAdapter, PipeTransport
from .reply_guard import EngineReplyGuard


class CgroupStopRequest:
    def __init__(self, *, cgroup_fd, expected_inode):
        if sys.platform != 'linux' or os.geteuid() == 0:
            raise Denied('ROOTLESS_LINUX_STOP_REQUIRED')
        st = os.fstat(cgroup_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_ino != expected_inode:
            raise Denied('EXACT_ENROLLED_CGROUP_REQUIRED')
        self.fd = os.dup(cgroup_fd)
        self.inode = expected_inode
        self.used = False
        self.failed = False
        self.lock = threading.Lock()

    def __call__(self, reason):
        with self.lock:
            if self.failed:
                raise Unknown('CGROUP_STOP_OUTCOME_RECONCILE_REQUIRED')
            if self.used:
                return
            self.used = True
            try:
                if os.fstat(self.fd).st_ino != self.inode:
                    raise Denied('CGROUP_IDENTITY_CHANGED')
                fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW, dir_fd=self.fd)
                try:
                    if os.write(fd, b'1') != 1:
                        raise OSError('CGROUP_STOP_REQUEST_FAILED')
                finally:
                    os.close(fd)
            except Exception:
                self.failed = True
                raise
            finally:
                try:
                    os.close(self.fd)
                except Exception:
                    self.failed = True
                    raise
        # A kill request is not an independent quiescence/settlement proof.


class _OwnedTransport:
    """Single ownership even when pump and setup cleanup both close the stream."""
    def __init__(self, transport):
        self.port = transport
        self.closed = False
        self.failure = False

    def read(self, size, timeout):
        return self.port.read(size, timeout)

    def write(self, data, timeout):
        return self.port.write(data, timeout)

    def close(self):
        if self.failure:
            raise Unknown('PILOT_TRANSPORT_CLOSE_UNCONFIRMED')
        if self.closed:
            return
        self.closed = True
        try:
            self.port.close()
        except Exception:
            self.failure = True
            raise


def _canonical_uuid(value):
    try:
        text = str(value)
        if str(UUID(text)) != text:
            raise ValueError()
        return text
    except (ValueError, TypeError, AttributeError):
        raise Denied('CANONICAL_PILOT_ID_REQUIRED') from None


class PilotSession:
    @classmethod
    def from_launch_observation(cls, *, observation, expected_host_boot_id,
                                expected_cgroup_inode, **ports):
        """Connect the existing launcher's parent pipes to the canonical session.

        Supervisor-only API. Metadata comparison is not enrollment/exec proof.
        On metadata rejection the caller retains pipe/pidfd ownership and must
        reconcile the requested stop. On transfer, PipeTransport consumes only
        the three pipe descriptors; pidfd remains with the independent observer.
        """
        stop = ports.get('stop_request')
        try:
            # A Python argument-binding error must not occur after pipe transfer.
            inspect.signature(cls).bind(transport=None, **ports)
            if (type(observation) is not dict or 'transport' in ports
                    or type(expected_cgroup_inode) is not int or expected_cgroup_inode <= 0
                    or observation.get('state') != 'CREATED_NOT_EXEC_ATTESTED'
                    or observation.get('host_boot_id') != _canonical_uuid(expected_host_boot_id)
                    or observation.get('cgroup_inode') != expected_cgroup_inode
                    or type(observation.get('pid')) is not int or observation['pid'] <= 0
                    or type(observation.get('pidfd')) is not int or observation['pidfd'] < 3
                    or ports['lease_state'].identity.get('host_boot_id') != expected_host_boot_id):
                raise Denied('EXACT_PILOT_LAUNCH_HANDOFF_REQUIRED')
            descriptors = [observation.get(k) for k in
                           ('engine_stdout_fd', 'engine_stdin_fd', 'engine_stderr_fd')]
            if (any(type(fd) is not int or fd < 3 for fd in descriptors)
                    or len(set(descriptors + [observation['pidfd']])) != 4):
                raise Denied('DISTINCT_PILOT_PARENT_DESCRIPTORS_REQUIRED')
        except Exception:
            try:
                if not callable(stop):
                    raise TypeError('EXPLICIT_STOP_PORT_REQUIRED')
                stop('PILOT_LAUNCH_HANDOFF_REJECTED')
            except Exception:
                raise Unknown('PILOT_HANDOFF_STOP_UNCONFIRMED') from None
            raise
        try:
            transport = PipeTransport.from_observation(observation)
        except Exception:
            try:
                stop('PILOT_PIPE_TRANSFER_FAILED')
            except Exception:
                raise Unknown('PILOT_HANDOFF_STOP_UNCONFIRMED') from None
            raise
        session = cls(transport=transport, **ports)
        session.launch_metadata = {key: observation[key] for key in
                                   ('pid', 'host_boot_id', 'cgroup_inode', 'state')}
        return session

    def __init__(self, *, connect, worker_auth, controller_auth, controller_id,
                 process_id, binding, proposal_signer, effect_signer, patch_signer,
                 directory_fd, measure_head, source_snapshot, journal, transport,
                 stop_request, lease_state, timeout):
        # Ownership of the supplied process ports begins here, including on setup
        # failure. The supervisor retains responsibility for independent stop proof.
        self.transport = _OwnedTransport(transport)
        self.stop_port = stop_request
        self.executor = None
        self.recorder = None
        self.closed = False
        self.used = False
        self.stop_attempted = False
        self.stop_failed = False
        self.lock = threading.Lock()
        try:
            if not all(callable(p) for p in (connect, measure_head, source_snapshot, stop_request,
                                             journal.reserve, lease_state.remaining)):
                raise Denied('EXPLICIT_PILOT_PORTS_REQUIRED')
            if type(directory_fd) is not int or directory_fd < 0:
                raise Denied('PILOT_DIRECTORY_DESCRIPTOR_REQUIRED')
            # Revalidate rather than trust a model_copy/model_construct bypass.
            self.binding = EngineBinding.model_validate(binding.model_dump(mode='python'))
            self.process = _canonical_uuid(process_id)
            controller = _canonical_uuid(controller_id)
            signers = [proposal_signer, effect_signer, patch_signer]
            if (any(_canonical_uuid(s.issuer) != controller for s in signers)
                    or len({_canonical_uuid(s.key_id) for s in signers}) != 3):
                raise Denied('THREE_EXPLICIT_CONTROLLER_PROFILE_KEYS_REQUIRED')
            projects = {(_canonical_uuid(s.tenant), _canonical_uuid(s.project)) for s in signers}
            if len(projects) != 1:
                raise Denied('ONE_SIGNER_TENANT_PROJECT_REQUIRED')
            tenant, project = next(iter(projects))
            self.worker = copy.deepcopy(worker_auth)
            self.controller = copy.deepcopy(controller_auth)
            tasks = set()
            for auth in (self.worker, self.controller):
                if (auth.get('kind') != 'ATTEMPT'
                        or _canonical_uuid(auth.get('attempt_id')) != str(self.binding.attempt_id)
                        or _canonical_uuid(auth.get('resource_id')) != str(self.binding.attempt_id)
                        or type(auth.get('fence')) is not int
                        or auth['fence'] != self.binding.fencing_epoch):
                    raise Denied('EXACT_COMPOSITION_ATTEMPT_REQUIRED')
                if _canonical_uuid(auth.get('project_id')) != project:
                    raise Denied('SIGNER_PROJECT_SCOPE_REQUIRED')
                if 'tenant_id' in auth and _canonical_uuid(auth['tenant_id']) != tenant:
                    raise Denied('SIGNER_TENANT_SCOPE_REQUIRED')
                if type(auth.get('token')) is not str or not auth['token']:
                    raise Denied('EXPLICIT_PILOT_SESSION_REQUIRED')
                _canonical_uuid(auth.get('grant_id'))
                tasks.add(_canonical_uuid(auth.get('task_id')))
            if len(tasks) != 1:
                raise Denied('ONE_PILOT_TASK_REQUIRED')
            if (self.worker['token'] == self.controller['token']
                    or self.worker['grant_id'] == self.controller['grant_id']):
                raise Denied('DISTINCT_WORKER_CONTROLLER_SESSIONS_REQUIRED')
            self.task = next(iter(tasks))
            self.lease = lease_state
            self.lease_identity = copy.deepcopy(lease_state.identity)
            identity = self.lease_identity
            if (type(identity) is not dict
                    or identity.get('process_id') != self.process
                    or identity.get('attempt_id') != str(self.binding.attempt_id)
                    or type(identity.get('fencing_epoch')) is not int
                    or identity['fencing_epoch'] != self.binding.fencing_epoch):
                raise Denied('EXACT_PILOT_WATCHDOG_IDENTITY_REQUIRED')
            self._remaining_seconds()
            self.executor = LinuxSingleFileExecutor(directory_fd=directory_fd, measure_head=measure_head)
            self.recorder = PatchReceiptRecorder(connect=connect, controller_auth=self.controller,
                                                 worker_auth=self.worker, patch_signer=patch_signer)
            scope = DbScope(connect, self.controller, timeout_ms=2000)
            kernel = ToolKernel(connect=connect, worker_auth=self.worker, controller_scope=scope,
                                process_id=self.process, signer=effect_signer, patch_recorder=self.recorder)
            self.broker = Broker(binding=self.binding, kernel=kernel,
                                 journal=ToolIntentJournal(journal), executor=self.executor)
            producer = PatchProposalProducer(connect=connect, controller_auth=self.controller,
                                             signer=proposal_signer, binding=self.binding,
                                             process_id=self.process, source_snapshot=source_snapshot)
            handler = ProducerOutputAdapter(producer=producer, broker=self.broker)
            self.pump = EnginePump(transport=self.transport, handler=handler,
                                   emission_guard=EngineReplyGuard(scope=scope, binding=self.binding),
                                   stop_request=self._request_stop,
                                   lease_remaining=self._remaining_seconds, timeout=timeout, max_frames=1)
        except Exception:
            self.closed = True
            self._cleanup('PILOT_SETUP_FAILED')
            raise

    def _remaining_seconds(self):
        if self.lease.identity != self.lease_identity:
            raise Denied('PILOT_WATCHDOG_IDENTITY_CHANGED')
        ns = self.lease.remaining()
        if type(ns) is not int or ns <= 0:
            raise Denied('ENROLLED_BOOTTIME_LEASE_EXPIRED')
        return ns / 1_000_000_000

    def _request_stop(self, reason):
        with self.lock:
            if self.stop_failed:
                raise Unknown('PILOT_STOP_OUTCOME_RECONCILE_REQUIRED')
            if self.stop_attempted:
                return
            self.stop_attempted = True
            try:
                self.stop_port(reason)
            except Exception:
                self.stop_failed = True
                raise

    def _cleanup(self, reason):
        failed = False
        try:
            self._request_stop(reason)
        except Exception:
            failed = True
        try:
            self.transport.close()
        except Exception:
            failed = True
        if self.executor is not None:
            executor, self.executor = self.executor, None
            try:
                executor.close()
            except Exception:
                failed = True
        if failed:
            raise Unknown('PILOT_CLEANUP_OUTCOME_RECONCILE_REQUIRED')

    def run(self):
        with self.lock:
            if self.closed or self.used:
                raise Denied('PILOT_SESSION_ALREADY_USED_OR_CLOSED')
            self.used = True
        try:
            result = self.pump.run()
            if (result != dict(outcome='PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED', frames=1)
                    or self.recorder.confirmed is None):
                raise Unknown('PILOT_HAS_NO_COMMITTED_PATCH_RECEIPT')
            return dict(result, task_id=self.task, attempt_id=str(self.binding.attempt_id),
                        fencing_epoch=self.binding.fencing_epoch, process_id=self.process,
                        engine_session_id=str(self.binding.engine_session_id),
                        patch_receipt=copy.deepcopy(self.recorder.confirmed),
                        quiescence='NOT_OBSERVED', verification='NOT_RUN')
        finally:
            self.closed = True
            self._cleanup('PILOT_SESSION_FINISHED')

    def close(self):
        with self.lock:
            if self.used and not self.closed:
                raise Denied('PILOT_RUNNING_USE_SUPERVISOR_STOP_PORT')
            self.closed = True
        self._cleanup('PILOT_CANCELLED_BEFORE_RUN')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
