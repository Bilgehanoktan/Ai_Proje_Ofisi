"""Canonical PilotSession integration with DB/OS doubles, never actual runtime."""
import base64
import copy
import json
import tempfile
import unittest
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from company_os import composition
from company_os.execution_protocol import Denied, Unknown
from .test_pipeline import Harness, Cursor, SOURCE, CANDIDATE, digest, uid
from .test_engine_bridge import Transport


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = Harness(self.tmp.name)
        self.stops = []
        self.executor_closes = []
        self.guard_revoked = False
        self.tamper_patch = False
        self.close_count = 0
        wire = json.dumps(dict(protocol='company.producer-output/1', action='replace',
                               replacement_base64=base64.b64encode(CANDIDATE).decode())).encode()+b'\n'
        self.transport = Transport([wire[:15], wire[15:]])
        original_close = self.transport.close
        def close():
            self.close_count += 1
            original_close()
        self.transport.close = close
        original = Cursor.execute
        test = self
        def execute(cursor, sql, args=()):
            if 'r65_engine_reply_guard(' in sql:
                test.assertTrue(test.h.patch_committed)
                test.h.events.append((cursor.c.id, sql, args))
                if test.guard_revoked:
                    raise ValueError('fixture current authorization revoked')
                cursor.c.row = dict(receipt_id=args[0], request_id=test.h.request['request_id'],
                                   engine_session_id=test.h.engine)
                return
            original(cursor, sql, args)
            if test.tamper_patch and 'r58_patch_receipt(' in sql:
                cursor.c.row['result_payload']['result_head'] = 'f'*64
        self.addCleanup(patch.stopall)
        patch.object(Cursor, 'execute', execute).start()
        executor = SimpleNamespace(execute=self.h.executor.execute,
                                   close=lambda: self.executor_closes.append(True))
        self.executor_factory = patch.object(composition, 'LinuxSingleFileExecutor', return_value=executor).start()
        h = self.h
        self.lease = SimpleNamespace(identity=dict(process_id=h.process, attempt_id=h.attempt,
                                                   fencing_epoch=1, host_boot_id=uid(),
                                                   controller_generation=1), remaining=lambda: 2_000_000_000)
        self.worker = copy.deepcopy(h.auth)
        self.controller = dict(h.auth, token='different-controller-fixture-token', grant_id=uid())
        journal = SimpleNamespace(reserve=lambda scope, identity, record: h.reserve(identity, record))
        self.arguments = dict(connect=h.connect, worker_auth=self.worker, controller_auth=self.controller,
                              controller_id=h.controller, process_id=h.process, binding=h.binding,
                              proposal_signer=h.proposal_signer, effect_signer=h.effect_signer,
                              patch_signer=h.patch_signer, directory_fd=42,
                              measure_head=lambda: digest((Path(self.tmp.name)/'task_title.py').read_bytes()),
                              source_snapshot=lambda: dict(head_digest=digest(SOURCE), source_bytes=SOURCE),
                              journal=journal, transport=self.transport,
                              stop_request=self.stops.append, lease_state=self.lease, timeout=2)

    def session(self, **changes):
        return composition.PilotSession(**dict(self.arguments, **changes))

    def assert_closed_once(self):
        self.assertEqual(self.close_count, 1)
        self.assertEqual(len(self.stops), 1)
        self.assertEqual(len(self.executor_closes), 1)

    def test_real_composition_ports_stage_commit_guard_send_stop_and_export_exact_patch(self):
        session = self.session()
        with session:
            result = session.run()
        h = self.h
        self.assertEqual(result['outcome'], 'PATCH_RECORDED_STOP_AND_VERIFY_REQUIRED')
        self.assertEqual(result['patch_receipt'], session.recorder.confirmed)
        self.assertEqual(result['patch_receipt']['result_head'], digest(CANDIDATE))
        self.assertEqual(result['attempt_id'], h.attempt)
        self.assertEqual(result['process_id'], h.process)
        self.assertEqual(result['quiescence'], 'NOT_OBSERVED')
        self.assertEqual(result['verification'], 'NOT_RUN')
        self.assertEqual(h.reader_connection, h.effect_connection)
        self.assertTrue(h.effect_committed and h.patch_committed)
        self.assertEqual((h.file_writes, h.patch_writes), (1, 1))
        self.assertEqual(json.loads(self.transport.writes[0])['status'], 'OK')
        self.assert_closed_once()
        result['patch_receipt']['result_head'] = '0'*64
        self.assertEqual(session.recorder.confirmed['result_head'], digest(CANDIDATE))
        with self.assertRaises(Denied):
            session.run()

    def test_lost_patch_commit_never_emits_or_reapplies_and_stops(self):
        self.h.fail_commit = 'patch.receipt'
        session = self.session()
        with self.assertRaises(Unknown):
            session.run()
        self.assertIsNone(session.recorder.confirmed)
        self.assertEqual(self.transport.writes, [])
        self.assertEqual(self.h.file_writes, 1)
        with self.assertRaises(Denied):
            session.run()
        self.assert_closed_once()

    def test_lost_effect_commit_has_no_patch_record_and_no_response(self):
        self.h.fail_commit = 'tool.effect'
        session = self.session()
        with self.assertRaises(Unknown):
            session.run()
        self.assertEqual((self.h.file_writes, self.h.patch_writes), (1, 0))
        self.assertEqual(self.transport.writes, [])
        self.assert_closed_once()

    def test_current_authority_revoked_after_patch_commit_sends_zero_bytes(self):
        self.guard_revoked = True
        session = self.session()
        with self.assertRaises(Unknown):
            session.run()
        self.assertTrue(self.h.patch_committed)
        self.assertEqual(self.transport.writes, [])
        self.assert_closed_once()

    def test_wrong_committed_patch_metadata_is_not_exported_or_emitted(self):
        self.tamper_patch = True
        session = self.session()
        with self.assertRaises(Unknown):
            session.run()
        self.assertIsNone(session.recorder.confirmed)
        self.assertEqual(self.transport.writes, [])
        self.assert_closed_once()

    def test_expired_lease_and_changed_identity_stop_before_read_or_effect(self):
        session = self.session()
        self.lease.identity['process_id'] = uid()
        with self.assertRaises(Unknown):
            session.run()
        self.assertEqual(self.transport.reads, 0)
        self.assertEqual(self.h.events, [])
        self.assert_closed_once()

    def test_expired_lease_at_setup_stops_and_closes_without_creating_executor(self):
        self.lease.remaining = lambda: 0
        with self.assertRaisesRegex(Denied, 'ENROLLED_BOOTTIME_LEASE_EXPIRED'):
            self.session()
        self.executor_factory.assert_not_called()
        self.assertEqual((self.close_count, len(self.stops)), (1, 1))
        self.assertEqual(self.h.events, [])

    def test_setup_failure_after_executor_creation_stops_and_closes_every_port(self):
        with self.assertRaises(Denied):
            self.session(timeout=float('nan'))
        self.assert_closed_once()
        self.assertEqual(self.h.events, [])

    def test_wrong_task_project_fence_and_reused_sessions_are_rejected_before_effects(self):
        variants = [dict(self.controller, task_id=uid()), dict(self.controller, project_id=uid()),
                    dict(self.controller, fence=True), dict(self.worker)]
        for auth in variants:
            with self.subTest(auth_fields=sorted(auth)):
                # Each rejected construction transfers its own fake transport.
                self.transport.closed = False
                with self.assertRaises(Denied):
                    self.session(controller_auth=auth)
        self.executor_factory.assert_not_called()
        self.assertEqual(self.h.events, [])

    def test_caller_auth_mutation_cannot_change_assembled_scope(self):
        session = self.session()
        self.worker['task_id'] = uid()
        self.controller['project_id'] = uid()
        result = session.run()
        self.assertEqual(result['task_id'], self.h.task)
        self.assert_closed_once()

    def test_stop_failure_is_unknown_and_cannot_silently_turn_into_success(self):
        def fail(reason):
            self.stops.append(reason)
            raise OSError('fixture stop request lost')
        session = self.session(stop_request=fail)
        with self.assertRaises(Unknown):
            session.run()
        with self.assertRaises(Unknown):
            session.close()
        self.assert_closed_once()

    def test_cancel_before_run_closes_once_and_produces_no_effect(self):
        session = self.session()
        session.close()
        session.close()
        self.assertEqual(self.h.events, [])
        self.assert_closed_once()
        with self.assertRaises(Denied):
            session.run()

    def test_launcher_parent_pipe_handoff_uses_canonical_session_without_promoting_state(self):
        boot = self.lease.identity['host_boot_id']
        observation = dict(pid=999, pidfd=10, host_boot_id=boot, cgroup_inode=111,
                           state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=11,
                           engine_stdin_fd=12, engine_stderr_fd=13)
        ports = {k:v for k,v in self.arguments.items() if k != 'transport'}
        with patch.object(composition.PipeTransport, 'from_observation',
                          return_value=self.transport) as transfer:
            session = composition.PilotSession.from_launch_observation(
                observation=observation, expected_host_boot_id=boot,
                expected_cgroup_inode=111, **ports)
            result = session.run()
        transfer.assert_called_once_with(observation)
        self.assertEqual(session.launch_metadata['state'], 'CREATED_NOT_EXEC_ATTESTED')
        self.assertNotIn('pidfd', session.launch_metadata)
        self.assertEqual(result['verification'], 'NOT_RUN')
        self.assert_closed_once()

    def test_wrong_launch_host_or_cgroup_and_alias_pipe_never_transfer_or_emit(self):
        boot = self.lease.identity['host_boot_id']
        observation = dict(pid=999, pidfd=10, host_boot_id=boot, cgroup_inode=111,
                           state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=11,
                           engine_stdin_fd=12, engine_stderr_fd=13)
        ports = {k:v for k,v in self.arguments.items() if k != 'transport'}
        with patch.object(composition.PipeTransport, 'from_observation') as transfer:
            for changes in ({'host_boot_id':uid()}, {'cgroup_inode':222}, {'engine_stdout_fd':10}):
                with self.subTest(changes=changes), self.assertRaises(Denied):
                    composition.PilotSession.from_launch_observation(
                        observation=dict(observation, **changes), expected_host_boot_id=boot,
                        expected_cgroup_inode=111, **ports)
        transfer.assert_not_called()
        self.executor_factory.assert_not_called()
        self.assertEqual(self.transport.writes, [])
        self.assertEqual(self.h.events, [])
        self.assertEqual(self.stops, ['PILOT_LAUNCH_HANDOFF_REJECTED']*3)

    def test_bad_supervisor_argument_shape_is_rejected_before_pipe_transfer(self):
        boot = self.lease.identity['host_boot_id']
        observation = dict(pid=999, pidfd=10, host_boot_id=boot, cgroup_inode=111,
                           state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=11,
                           engine_stdin_fd=12, engine_stderr_fd=13)
        ports = {k:v for k,v in self.arguments.items() if k != 'transport'}
        with patch.object(composition.PipeTransport, 'from_observation') as transfer:
            with self.assertRaises(TypeError):
                composition.PilotSession.from_launch_observation(
                    observation=observation, expected_host_boot_id=boot,
                    expected_cgroup_inode=111, unrecognized_argument=True, **ports)
        transfer.assert_not_called()
        self.assertEqual(self.stops, ['PILOT_LAUNCH_HANDOFF_REJECTED'])
        self.assertEqual(self.h.events, [])


class CgroupStopTests(unittest.TestCase):
    @contextmanager
    def fake_cgroup(self, written=1):
        # No Linux syscall/cgroup is exercised by these port-failure tests.
        with ExitStack() as stack:
            stack.enter_context(patch.object(composition.sys, 'platform', 'linux'))
            stack.enter_context(patch.object(composition.os, 'geteuid', return_value=1000, create=True))
            stack.enter_context(patch.object(composition.os, 'O_NOFOLLOW', 0, create=True))
            stack.enter_context(patch.object(composition.os, 'fstat',
                                            return_value=SimpleNamespace(st_mode=stat.S_IFDIR, st_ino=111)))
            stack.enter_context(patch.object(composition.os, 'dup', return_value=55))
            opened = stack.enter_context(patch.object(composition.os, 'open', return_value=66))
            stack.enter_context(patch.object(composition.os, 'write', return_value=written))
            closed = stack.enter_context(patch.object(composition.os, 'close'))
            yield composition.CgroupStopRequest(cgroup_fd=44, expected_inode=111), opened, closed

    def test_partial_kill_write_remains_unknown_on_repeated_stop(self):
        with self.fake_cgroup(written=0) as (stop, opened, closed):
            with self.assertRaises(OSError):
                stop('fixture')
            with self.assertRaises(Unknown):
                stop('fixture retry')
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(closed.call_count, 2)

    def test_successful_stop_request_is_one_shot_not_quiescence_proof(self):
        with self.fake_cgroup() as (stop, opened, closed):
            self.assertIsNone(stop('fixture'))
            self.assertIsNone(stop('fixture duplicate'))
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(closed.call_count, 2)
            self.assertTrue(stop.used)
            self.assertFalse(stop.failed)
