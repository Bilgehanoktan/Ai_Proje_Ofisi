"""Canonical launch -> pilot -> independent stop -> verifier composition.

Supervisor-only ports. No enrollment, synthetic defaults, service startup or
fallback execution. Injected observation/verification adapters require their
own OS qualification; source tests cannot establish that trust.
"""
import copy
import inspect
import threading
from uuid import uuid4

from . import command_host as host
from .composition import PilotSession
from .supervisor_handles import LaunchObservationCloser
from .execution_protocol import Denied, Unknown, reconcile_unknown
from packages.contracts.execution import EngineBinding


def _digest(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise Denied('EXACT_WORKFLOW_DIGEST_REQUIRED')
    return value


def _command(connect, auth, operation, args):
    envelope = host.execute(connect(), auth, operation, args)
    if (type(envelope.get('command_receipt')) is not dict
            or envelope['command_receipt'].get('state') != 'SUCCEEDED'
            or type(envelope.get('result')) is not dict):
        raise Unknown('WORKFLOW_COMMAND_COMMIT_NOT_CONFIRMED')
    return envelope['result']


def _ingest(connect, auth, signer, profile, binding):
    identity, raw, tag = signer.sign(profile, binding)
    result = _command(connect, auth, 'evidence.attestation_ingest',
                      [identity, str(signer.issuer), str(signer.key_id), signer.revision,
                       profile, raw, tag, 'workflow-proof:' + identity, str(uuid4())])
    if result.get('receipt_id') != identity:
        raise Unknown('WORKFLOW_ATTESTATION_READBACK_MISMATCH')
    return identity


class LaunchActivation:
    """Commit observed launch and exact engine binding through existing routes."""
    def __init__(self, *, connect, auth, callback_signer, engine_signer,
                 observer, observation_validator):
        if callback_signer.issuer != engine_signer.issuer:
            raise Denied('ONE_LAUNCH_CONTROLLER_REQUIRED')
        if callback_signer.key_id == engine_signer.key_id:
            raise Denied('DISTINCT_LAUNCH_AND_ENGINE_KEYS_REQUIRED')
        self.connect = connect
        self.auth = copy.deepcopy(auth)
        self.callback_signer = callback_signer
        self.engine_signer = engine_signer
        self.observer = observer
        self.validator = observation_validator

    def activate(self, *, dispatch, launch_tuple, binding):
        observation = dispatch['observation']
        expected = dict(process_id=launch_tuple['process_id'],
                        capability_id=dispatch['capability_id'], tuple_digest=dispatch['tuple_digest'],
                        host_boot_id=launch_tuple['host_boot_id'],
                        controller_generation=launch_tuple['controller_generation'],
                        cgroup_inode=observation['cgroup_inode'])
        measured = self.observer.observe(expected=copy.deepcopy(expected),
                                         observation=copy.deepcopy(observation))
        if self.validator.validate(measured, expected=copy.deepcopy(expected)) is not True:
            raise Denied('ENROLLED_LAUNCH_OBSERVATION_REQUIRED')
        if (type(measured) is not dict or measured.get('identity') != expected
                or measured.get('outcome') != 'RUNNING'):
            raise Denied('EXACT_RUNNING_LAUNCH_MEASUREMENT_REQUIRED')
        process_digest = _digest(measured.get('process_identity_digest'))
        isolation_digest = _digest(measured.get('isolation_digest'))
        callback = dict(capability_id=expected['capability_id'], tuple_digest=expected['tuple_digest'],
                        controller_generation=expected['controller_generation'],
                        host_boot_id=expected['host_boot_id'], process_identity_digest=process_digest,
                        isolation_digest=isolation_digest, cgroup_inode=expected['cgroup_inode'], outcome='RUNNING')
        proof = _ingest(self.connect, self.auth, self.callback_signer, 'r58.launch-callback.v1', callback)
        result = _command(self.connect, self.auth, 'process.launch_callback',
                          [expected['capability_id'], proof, 'workflow-callback:' + proof, str(uuid4())])
        required = dict(process_id=expected['process_id'], capability_id=expected['capability_id'],
                        outcome='RUNNING', process_identity_digest=process_digest,
                        isolation_digest=isolation_digest, callback_attestation_id=proof,
                        respawn_permitted=False)
        if result != required:
            raise Unknown('LAUNCH_CALLBACK_READBACK_MISMATCH')
        proof = _ingest(self.connect, self.auth, self.engine_signer, 'r60.engine-binding.v1',
                        dict(engine_session_id=str(binding.engine_session_id),
                             process_id=expected['process_id'], task_revision=binding.revision,
                             tool_manifest_digest=binding.tool_manifest_digest))
        result = _command(self.connect, self.auth, 'engine.bind',
                          [proof, 'workflow-engine:' + proof, str(uuid4())])
        if result != dict(engine_session_id=str(binding.engine_session_id), next_sequence=1):
            raise Unknown('ENGINE_BIND_READBACK_MISMATCH')
        return dict(expected, process_identity_digest=process_digest)


class ProcessReconciler:
    """Independent observation -> signed Kernel reconciliation, never release."""
    def __init__(self, *, connect, auth, signer, observer, observation_validator,
                 producer_id, controller_id):
        if signer.issuer in {producer_id, controller_id}:
            raise Denied('INDEPENDENT_STOP_OBSERVER_REQUIRED')
        self.connect = connect
        self.auth = copy.deepcopy(auth)
        self.signer = signer
        self.observer = observer
        self.validator = observation_validator
        self.producer = producer_id
        self.controller = controller_id

    def reconcile(self, *, expected):
        observation = self.observer.observe(expected=copy.deepcopy(expected))
        if self.validator.validate(observation, expected=copy.deepcopy(expected)) is not True:
            raise Denied('ENROLLED_STOP_OBSERVATION_REQUIRED')
        state = reconcile_unknown(expected=expected, observation=observation,
                                  producer_id=self.producer, controller_id=self.controller,
                                  enrolled_verifier_id=self.signer.issuer)
        if state['state'] != 'STOPPED_RECONCILED':
            raise Unknown('WORKER_STILL_RUNNING_NO_VERIFICATION')
        if observation['outcome'] != 'EXITED':
            raise Denied('RUNNING_CALLBACK_REQUIRES_EXITED_OBSERVATION')
        payload = dict(expected, observer_id=self.signer.issuer,
                       **{k: observation[k] for k in ('outcome', 'cgroup_populated',
                          'workspace_fenced', 'no_respawn_intent', 'usage_zero')})
        proof = _ingest(self.connect, self.auth, self.signer, 'r60.process-observation.v1', payload)
        result = _command(self.connect, self.auth, 'process.reconcile',
                          [expected['process_id'], proof, 'workflow-stop:' + proof, str(uuid4())])
        if result != dict(process_id=expected['process_id'], observation=observation['outcome'],
                          respawn_permitted=False, release_performed=False):
            raise Unknown('PROCESS_RECONCILIATION_READBACK_MISMATCH')
        return result


class PilotWorkflow:
    """One-shot composition. Any uncertain phase requires external reconciliation."""
    def __init__(self, *, dispatcher, activation, lease_registry, pilot_ports,
                 reconciler, runtime_verifier, verification_pipeline,
                 close_observation=None, expected_host_boot_id, expected_cgroup_inode):
        self.dispatcher = dispatcher
        self.activation = activation
        self.registry = lease_registry
        self.ports = dict(pilot_ports)
        # Copy auth/models; preserve enrolled OS, signer and callback identities.
        for key in ('worker_auth', 'controller_auth'):
            self.ports[key] = copy.deepcopy(self.ports[key])
        self.ports['binding'] = EngineBinding.model_validate(self.ports['binding'].model_dump())
        inspect.signature(PilotSession).bind(transport=None, lease_state=None, **self.ports)
        self.reconciler = reconciler
        self.verifier = runtime_verifier
        self.pipeline = verification_pipeline
        self.close_observation = (LaunchObservationCloser(
            expected_host_boot_id=expected_host_boot_id,
            expected_cgroup_inode=expected_cgroup_inode)
            if close_observation is None else close_observation)
        self.boot = expected_host_boot_id
        self.cgroup = expected_cgroup_inode
        self.used = False
        self.lock = threading.Lock()
        # No spawn may happen with missing downstream trusted ports.
        for method in (dispatcher.dispatch, activation.activate, reconciler.reconcile,
                       runtime_verifier.verify, verification_pipeline.seal_and_accept,
                       self.close_observation, self.ports['stop_request']):
            if not callable(method):
                raise Denied('EXPLICIT_WORKFLOW_PORTS_REQUIRED')
        if verification_pipeline.receipt_validator is None:
            raise Denied('ENROLLED_VERIFIER_RECEIPT_VALIDATOR_REQUIRED')
        if not callable(verification_pipeline.receipt_validator.validate):
            raise Denied('ENROLLED_VERIFIER_RECEIPT_VALIDATOR_REQUIRED')
        self.stop_attempted = False
        self.stop_failed = False
        self.stop_lock = threading.Lock()
        self.stop_port = self.ports['stop_request']
        self.ports['stop_request'] = self._stop

    def _stop(self, reason):
        with self.stop_lock:
            if self.stop_failed:
                raise Unknown('WORKFLOW_STOP_UNCONFIRMED_NO_RETRY')
            if self.stop_attempted:
                return
            self.stop_attempted = True
            try:
                self.stop_port(reason)
            except Exception:
                self.stop_failed = True
                raise

    def run(self, *, wire, expected_task_revision, profile_digest, build_digest,
            acceptance_criteria_digest):
        with self.lock:
            if self.used:
                raise Unknown('WORKFLOW_CANNOT_RETRY_OR_RESPAWN')
            self.used = True
        for value in (profile_digest, build_digest, acceptance_criteria_digest):
            _digest(value)
        if type(expected_task_revision) is not int or expected_task_revision < 1:
            raise Denied('EXACT_TASK_REVISION_REQUIRED')
        # Verify the authenticated tuple before dispatch, then require the same
        # tuple after dispatch. CommittedController revalidates under Kernel locks.
        ticket = self.dispatcher.codec.verify(wire, audience=self.dispatcher.audience,
                                               now=self.dispatcher.clock())
        launch_tuple = ticket['result']['tuple']
        process = self.ports['process_id']
        binding = self.ports['binding']
        auth = self.ports['worker_auth']
        if (launch_tuple['process_id'] != process or launch_tuple['task_id'] != auth['task_id']
                or launch_tuple['attempt_id'] != str(binding.attempt_id)
                or launch_tuple['fencing_epoch'] != binding.fencing_epoch
                or launch_tuple['controller_id'] != self.ports['controller_id']
                or launch_tuple['host_boot_id'] != self.boot):
            raise Denied('WORKFLOW_LAUNCH_SCOPE_MISMATCH')
        for signer in (self.pipeline.verifier_signer, self.pipeline.evidence_signer):
            if signer.issuer in {launch_tuple['worker_id'], launch_tuple['controller_id']}:
                raise Denied('INDEPENDENT_WORKFLOW_VERIFIERS_REQUIRED')
        dispatched = None
        session = None
        handoff = {}
        try:
            dispatched = self.dispatcher.dispatch(wire)
            register = getattr(self.close_observation, 'register', None)
            if register is not None:
                register(dispatched['observation'])
            if (dispatched['capability_id'] != ticket['result']['capability_id']
                    or dispatched['tuple_digest'] != ticket['result']['tuple_digest']
                    or dispatched['observation']['cgroup_inode'] != self.cgroup
                    or dispatched['observation']['host_boot_id'] != self.boot
                    or dispatched['observation']['state'] != 'CREATED_NOT_EXEC_ATTESTED'):
                raise Denied('WORKFLOW_DISPATCH_BINDING_MISMATCH')
            identity = self.activation.activate(dispatch=dispatched, launch_tuple=launch_tuple, binding=binding)
            lease = self.registry.states[process]
            ports = dict(self.ports, lease_state=lease)
            session = PilotSession.from_launch_observation(
                observation=dispatched['observation'], expected_host_boot_id=self.boot,
                expected_cgroup_inode=self.cgroup, handoff_state=handoff, **ports)
            result = session.run()  # Includes stop request and transport cleanup.
            self.reconciler.reconcile(expected=identity)
            patch = result['patch_receipt']
            expected = dict(task_id=result['task_id'], attempt_id=result['attempt_id'],
                            fence=result['fencing_epoch'], expected_task_revision=expected_task_revision,
                            patch_id=patch['patch_id'], head_digest=patch['result_head'],
                            profile_digest=profile_digest, build_digest=build_digest,
                            acceptance_criteria_digest=acceptance_criteria_digest)
            report = self.verifier.verify(expected=copy.deepcopy(expected))
            accepted = self.pipeline.seal_and_accept(**expected, oracle_report=report)
            decision = accepted.get('acceptance', {})
            if (decision.get('state') != 'ACCEPTED' or decision.get('task_id') != expected['task_id']
                    or decision.get('attempt_id') != expected['attempt_id']):
                raise Unknown('WORKFLOW_ACCEPTANCE_READBACK_MISMATCH')
            return dict(outcome='KERNEL_ACCEPTANCE_RECORDED', pilot=result,
                        verification=accepted, human_acceptance='NOT_CLAIMED', g0='OPEN')
        except Exception:
            # Controller dispatch may have spawned before losing its DB/transport
            # acknowledgement. Stop even when no observation was returned.
            if session is None:
                try:
                    self.ports['stop_request']('WORKFLOW_SETUP_OR_DISPATCH_FAILED')
                except Exception:
                    raise Unknown('WORKFLOW_STOP_UNCONFIRMED_NO_RETRY') from None
            raise
        finally:
            if dispatched is not None:
                # pidfd always remains supervisor-owned. Before handoff the
                # supervisor also owns pipes; after handoff only pidfd is closed.
                try:
                    self.close_observation(dispatched['observation'],
                                           pipes_transferred=handoff.get('pipes_transferred') is True)
                except Exception:
                    raise Unknown('WORKFLOW_OBSERVATION_CLOSE_UNCONFIRMED') from None
