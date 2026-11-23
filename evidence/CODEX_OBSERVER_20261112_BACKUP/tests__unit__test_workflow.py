"""Canonical end-to-end ports with DB/OS doubles; never isolation acceptance."""
import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools import disposable_e2e_workflow_trial as entry

from company_os import workflow, composition, verifier_runner, command_host
from company_os.execution_protocol import (TicketCodec, CommittedController, IntentJournal,
                                           LeaseRegistry, Denied, Unknown, canonical)
from company_os.launch_controller import Controller, FIELDS
from company_os.kernel_adapters import ProofSigner
from . import test_composition as fixtures
from .test_pipeline import Cursor, uid, digest, SOURCE, CANDIDATE


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        f = self.f = fixtures.CompositionTests('runTest')
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.h = h = f.h
        self.events = []
        self.foreign = False
        self.running = False
        self.bad_stop = False
        self.reject_receipt = False
        self.source_report = False
        self.callback_changed = False
        self.closed = []
        self.verifier_calls = []
        self.producer = uid()
        self.observer_id = uid()
        self.verification_id = uid()
        self.evidence_id = uid()
        self.boot = f.lease.identity['host_boot_id']
        self.observation = dict(pid=999, pidfd=10, host_boot_id=self.boot, cgroup_inode=111,
                                state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=11,
                                engine_stdin_fd=12, engine_stderr_fd=13)
        self.journal = IntentJournal(Path(f.tmp.name)/'workflow.sqlite')
        self.registry = LeaseRegistry(journal=self.journal, clock=lambda:100)
        t = {key: uid() for key in FIELDS}
        t.update(tenant_id=h.tenant, project_id=h.project, task_id=h.task, attempt_id=h.attempt,
                 fencing_epoch=1, worker_id=self.producer, controller_id=h.controller,
                 process_id=h.process, host_boot_id=self.boot, host_revision=1,
                 host_generation=1, controller_generation=1, lease_policy_revision=1,
                 not_after_boottime_ns=2_000_000_000, binding_digest='a'*64,
                 head_digest=digest(SOURCE), executable_digest='b'*64, argv=['worker'],
                 claims=['fixture-claim'])
        self.tuple = t
        raw = canonical(t).decode()
        result = dict(spawn_permitted=True, release_only_after_commit=True, tuple_raw=raw,
                      tuple_digest=digest(raw.encode()), tuple=t, capability_id=t['capability_id'])
        receipt = dict(state='SUCCEEDED', result_ref=t['capability_id'], command_id=uid())
        envelope = dict(operation='process.launch_consume', result=result,
                        command_receipt=receipt, snapshot={'project_epoch':1})
        audience = {k:t[k] for k in ('controller_id','controller_generation','host_boot_id')}
        self.codec = TicketCodec(key=b't'*32, issuer_id=uid(), key_id=uid(), key_revision=1)
        self.wire = self.codec.seal_after_commit(envelope=envelope, delivery_id=uid(),
                                               audience=audience, expires_boottime_ns=1_000_000)
        @contextmanager
        def guard(ticket):
            self.events.append('DELIVERY_LOCK')
            yield {k:ticket[k] for k in ('command_receipt','result','snapshot')}
        def spawn(value):
            self.events.append('SPAWN')
            self.registry.attach(value)
            return copy.deepcopy(self.observation)
        controller = Controller(SimpleNamespace(reserve=lambda identity,record:
                            self.journal.reserve('controller',identity,record)), t,
                            SimpleNamespace(spawn=spawn), lambda:100, lambda workspace,head:head)
        self.dispatcher = CommittedController(codec=self.codec, audience=audience,
                  clock=lambda:100, journal=self.journal, kernel_guard=guard, controller=controller)
        def signer(issuer):
            return ProofSigner(issuer_id=issuer, key_id=uid(), revision=1, key=b'x'*32,
                               tenant_id=h.tenant, project_id=h.project)
        self.callback_signer = signer(h.controller)
        self.engine_signer = signer(h.controller)
        self.verifier_signer = signer(self.observer_id)
        self.evidence_signer = signer(uid())
        test = self
        class Validator:
            def validate(self, observation, *, expected):
                return observation.get('identity') == expected and not test.foreign
        class LaunchObserver:
            def observe(self, *, expected, observation):
                test.events.append('LAUNCH_OBSERVE')
                return dict(identity=expected, outcome='RUNNING',
                            process_identity_digest='c'*64, isolation_digest='d'*64)
        class StopObserver:
            def observe(self, *, expected):
                test.assertTrue(h.patch_committed)
                test.assertEqual(len(f.stops),1)
                test.events.append('STOP_OBSERVE')
                return dict(identity=expected, observer_id=test.observer_id,
                            outcome='RUNNING' if test.running else 'EXITED',
                            cgroup_populated=1 if test.running else 0,
                            workspace_fenced=not test.bad_stop, no_respawn_intent=True, usage_zero=True)
        self.activation = workflow.LaunchActivation(connect=h.connect, auth=f.controller,
                    callback_signer=self.callback_signer, engine_signer=self.engine_signer,
                    observer=LaunchObserver(), observation_validator=Validator())
        self.reconciler = workflow.ProcessReconciler(connect=h.connect, auth=f.controller,
                    signer=self.verifier_signer, observer=StopObserver(), observation_validator=Validator(),
                    producer_id=self.producer, controller_id=h.controller)
        class RuntimeVerifier:
            def verify(self, *, expected):
                test.events.append('VERIFY')
                test.verifier_calls.append(copy.deepcopy(expected))
                report = dict(execution_class='SOURCE_TEST' if test.source_report else 'ACTUAL_RUNTIME',
                              acceptance_eligible=not test.source_report, outcome='PASS',
                              oracle_id=verifier_runner.ORACLE_ID,
                              oracle_sha256=verifier_runner.ENROLLED_ORACLE_SHA256,
                              passed=13, total=13,
                              checks=[dict(id=key,result='PASS') for key in sorted(verifier_runner.EXPECTED_CASE_IDS)])
                report['report_digest'] = digest(canonical(report))
                return report
        class ReceiptValidator:
            def validate(self, report, *, expected):
                return not test.reject_receipt and expected == test.verifier_calls[-1]
        self.pipeline = verifier_runner.IndependentVerificationPipeline(connect=h.connect,
                    verifier_auth=f.controller, verifier_signer=self.verifier_signer,
                    evidence_auth=f.controller, evidence_signer=self.evidence_signer,
                    human_auth=f.controller, receipt_validator=ReceiptValidator())
        original = Cursor.execute
        def execute(cursor,sql,args=()):
            if 'r58_launch_callback(' in sql:
                payload=h.statements[args[1]]['binding']
                out=dict(process_id=h.process, capability_id=args[0], outcome='RUNNING',
                         process_identity_digest=payload['process_identity_digest'],
                         isolation_digest=payload['isolation_digest'], callback_attestation_id=args[1],
                         respawn_permitted=False)
                if test.callback_changed:out['process_id']=uid()
            elif 'r60_engine_bind(' in sql:
                out=dict(engine_session_id=h.engine,next_sequence=1)
            elif 'r60_process_reconcile(' in sql:
                test.events.append('RECONCILE')
                out=dict(process_id=h.process,observation='EXITED',respawn_permitted=False,release_performed=False)
            elif 'r58_verification_final_seal(' in sql:
                out=dict(verification_id=test.verification_id,seal_digest='e'*64)
            elif 'r58_evidence_provenance(' in sql:
                out=dict(evidence_id=test.evidence_id)
            elif 'r58_verification_accept(' in sql:
                test.events.append('ACCEPT')
                out=dict(state='ACCEPTED',task_id=h.task,attempt_id=h.attempt,acceptance_id=uid())
            else:
                return original(cursor,sql,args)
            h.events.append((cursor.c.id,sql,args))
            cursor.c.row=h.sealed(out)
        patch.object(Cursor,'execute',execute).start()
        patch.object(composition.PipeTransport,'from_observation',return_value=f.transport).start()
        ports={k:v for k,v in f.arguments.items() if k not in {'transport','lease_state'}}
        self.arguments=dict(dispatcher=self.dispatcher,activation=self.activation,lease_registry=self.registry,
                            pilot_ports=ports,reconciler=self.reconciler,runtime_verifier=RuntimeVerifier(),
                            verification_pipeline=self.pipeline,
                            close_observation=lambda obs,**kw:self.closed.append((obs,kw)),
                            expected_host_boot_id=self.boot,expected_cgroup_inode=111)
        self.request=dict(wire=self.wire,expected_task_revision=1,profile_digest='1'*64,
                          build_digest='2'*64,acceptance_criteria_digest='3'*64)

    def run_workflow(self):
        self.subject=workflow.PilotWorkflow(**self.arguments)
        return self.subject.run(**self.request)

    def test_launch_kernel_broker_patch_stop_reconcile_verifier_accept_chain(self):
        result=self.run_workflow()
        self.assertEqual(result['outcome'],'KERNEL_ACCEPTANCE_RECORDED')
        self.assertEqual(result['human_acceptance'],'NOT_CLAIMED')
        self.assertEqual(self.events,['DELIVERY_LOCK','SPAWN','LAUNCH_OBSERVE','STOP_OBSERVE','RECONCILE','VERIFY','ACCEPT'])
        self.assertEqual((self.h.file_writes,self.h.patch_writes),(1,1))
        self.assertEqual(self.verifier_calls[0]['head_digest'],digest(CANDIDATE))
        self.assertEqual(self.closed[0][1],{'pipes_transferred':True})
        self.f.assert_closed_once()
        with self.assertRaises(Unknown):self.subject.run(**self.request)
        self.assertEqual(self.events.count('SPAWN'),1)

    def test_tampered_ticket_stops_before_spawn(self):
        self.wire['tag']='0'*64
        with self.assertRaises(Denied):self.run_workflow()
        self.assertEqual(self.events,[])
        self.assertEqual(self.h.file_writes,0)

    def test_foreign_launch_measurement_stops_before_engine_or_file_effect(self):
        self.foreign=True
        with self.assertRaises(Denied):self.run_workflow()
        self.assertEqual(self.h.file_writes,0)
        self.assertEqual(len(self.f.stops),1)
        self.assertEqual(self.closed[0][1],{'pipes_transferred':False})
        self.assertEqual(self.verifier_calls,[])

    def test_changed_callback_readback_stops_before_file_effect(self):
        self.callback_changed=True
        with self.assertRaises(Unknown):self.run_workflow()
        self.assertEqual(self.h.file_writes,0)
        self.assertEqual(len(self.f.stops),1)

    def test_worker_still_running_never_verifies_or_accepts(self):
        self.running=True
        with self.assertRaises(Unknown):self.run_workflow()
        self.assertEqual(self.verifier_calls,[])
        self.assertNotIn('ACCEPT',self.events)
        self.f.assert_closed_once()

    def test_unfenced_workspace_never_verifies(self):
        self.bad_stop=True
        with self.assertRaises(Denied):self.run_workflow()
        self.assertEqual(self.verifier_calls,[])

    def test_lost_effect_commit_ack_has_no_reply_no_verification_no_replay(self):
        self.h.fail_commit='tool.effect'
        with self.assertRaises(Unknown):self.run_workflow()
        self.assertEqual(self.verifier_calls,[])
        self.assertEqual(self.f.transport.writes,[])
        self.assertEqual(self.h.file_writes,1)
        with self.assertRaises(Unknown):self.subject.run(**self.request)
        self.assertEqual(self.h.file_writes,1)

    def test_source_report_and_invalid_receipt_cannot_accept(self):
        self.source_report=True
        with self.assertRaises(Denied):self.run_workflow()
        self.assertNotIn('ACCEPT',self.events)

    def test_enrolled_validator_rejection_cannot_accept(self):
        self.reject_receipt=True
        with self.assertRaises(Denied):self.run_workflow()
        self.assertNotIn('ACCEPT',self.events)

    def test_missing_validator_is_rejected_before_spawn(self):
        self.pipeline.receipt_validator=None
        with self.assertRaises(Denied):workflow.PilotWorkflow(**self.arguments)
        self.assertEqual(self.events,[])

    def test_session_setup_failure_after_pipe_transfer_never_double_closes_pipes(self):
        self.arguments['pilot_ports']['directory_fd']=-1
        with self.assertRaises(Denied):self.run_workflow()
        self.assertEqual(self.closed[0][1],{'pipes_transferred':True})
        self.assertEqual(self.f.close_count,1)
        self.assertEqual(len(self.f.stops),1)
        self.assertEqual(self.h.file_writes,0)

    def test_callback_commit_ack_loss_cannot_retry_spawn(self):
        self.h.fail_commit='process.launch_callback'
        with self.assertRaises(command_host.UnknownCommitOutcome):self.run_workflow()
        with self.assertRaises(Unknown):self.subject.run(**self.request)
        self.assertEqual(self.events.count('SPAWN'),1)
        self.assertEqual(self.h.file_writes,0)
        self.assertEqual(len(self.f.stops),1)

    def test_dispatch_ack_loss_after_spawn_stops_without_respawn(self):
        original=self.dispatcher.dispatch
        def uncertain(wire):
            original(wire)
            raise Unknown('fixture lost dispatch acknowledgement')
        self.dispatcher.dispatch=uncertain
        with self.assertRaises(Unknown):self.run_workflow()
        self.assertEqual(self.events.count('SPAWN'),1)
        self.assertEqual(len(self.f.stops),1)
        self.assertEqual(self.verifier_calls,[])
        with self.assertRaises(Unknown):self.subject.run(**self.request)

    def test_stop_failure_blocks_verifier_and_stays_unknown(self):
        def failed(reason):
            self.f.stops.append(reason)
            raise OSError('fixture stop unconfirmed')
        self.arguments['pilot_ports']['stop_request']=failed
        with self.assertRaises(Unknown):self.run_workflow()
        self.assertEqual(self.verifier_calls,[])
        self.assertEqual(len(self.f.stops),1)
        with self.assertRaises(Unknown):self.subject._stop('again')

    def test_observation_cleanup_failure_is_unknown(self):
        def failed(*args,**kwargs):raise OSError('fixture close failed')
        self.arguments['close_observation']=failed
        with self.assertRaisesRegex(Unknown,'OBSERVATION_CLOSE_UNCONFIRMED'):
            self.run_workflow()
        with self.assertRaises(Unknown):self.subject.run(**self.request)

    def test_producer_cannot_be_runtime_verifier(self):
        self.pipeline.verifier_signer.issuer=self.producer
        with self.assertRaisesRegex(Denied,'INDEPENDENT_WORKFLOW_VERIFIERS_REQUIRED'):
            self.run_workflow()
        self.assertEqual(self.events,[])

    def test_foreign_process_scope_is_rejected_before_spawn(self):
        self.arguments['pilot_ports']['process_id']=uid()
        with self.assertRaisesRegex(Denied,'WORKFLOW_LAUNCH_SCOPE_MISMATCH'):
            self.run_workflow()
        self.assertEqual(self.events,[])

    def test_supervisor_entry_runs_canonical_chain_without_exposing_trust_material(self):
        installation=uid()
        human=uid()
        trust=dict(canonical_workspace=entry.CANONICAL_WORKSPACE,
                   root_record=dict(installation_id=installation,actual_human_id=human))
        for key in ('consent_path','consent_sha256','human_id','secret_directory_fd',
                    'secret_name','secret_owner_uid'):
            trust[key]='fixture-only'
        with patch.object(entry,'check_workflow_trust',
                          return_value=(SimpleNamespace(authority_granted=False),b'private-fixture-key')), \
             patch('builtins.print') as output:
            status=entry.main(trust_inputs=trust,workflow_ports=self.arguments,request=self.request,
                              read_bootstrap=lambda:dict(installation_id=installation,accepted_human_id=human))
        self.assertEqual(status,0)
        self.assertIn('ACCEPT',self.events)
        self.assertNotIn('private-fixture-key',str(output.call_args_list))

    def test_failed_transport_construction_reports_consumed_pipes_to_supervisor(self):
        def fail(observation, *, handoff_state):
            handoff_state['pipes_transferred']=True
            raise Denied('fixture transport constructor consumed originals')
        with patch.object(composition.PipeTransport,'from_observation',side_effect=fail):
            with self.assertRaises(Denied):self.run_workflow()
        self.assertEqual(self.closed[0][1],{'pipes_transferred':True})
        self.assertEqual(len(self.f.stops),1)
        self.assertEqual(self.h.file_writes,0)

    def test_supervisor_handle_registration_precedes_activation_and_handoff(self):
        test=self
        class Closer:
            def register(self,observation):test.events.append('REGISTER_HANDLES')
            def __call__(self,observation,**ownership):test.closed.append((observation,ownership))
        self.arguments['close_observation']=None
        with patch.object(workflow,'LaunchObservationCloser',return_value=Closer()) as factory:
            self.run_workflow()
        factory.assert_called_once_with(expected_host_boot_id=self.boot,expected_cgroup_inode=111)
        self.assertLess(self.events.index('REGISTER_HANDLES'),self.events.index('LAUNCH_OBSERVE'))
        self.assertEqual(self.closed[0][1],{'pipes_transferred':True})
