"""Real parent FDs only; never a worker/isolation/verification acceptance test."""
import os
import sys
import unittest
from unittest.mock import patch

from company_os.engine.engine_bridge import PipeTransport
from company_os.runtime.supervisor.supervisor_handles import LaunchObservationCloser, PIPE_KEYS
from company_os.kernel.execution_protocol import Denied, Unknown


class HandlePlatformTests(unittest.TestCase):
    def test_non_linux_constructor_is_rejected_without_touching_descriptors(self):
        with patch('company_os.runtime.supervisor.supervisor_handles.sys.platform', 'win32'), \
             patch('os.close') as close:
            with self.assertRaises(Denied):
                LaunchObservationCloser(expected_host_boot_id='fixture', expected_cgroup_inode=1)
            close.assert_not_called()

    def test_transport_constructor_failure_publishes_consumed_ownership(self):
        observation = dict(state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=31,
                           engine_stdin_fd=32, engine_stderr_fd=33)
        state = {}
        with patch.object(PipeTransport, '__init__', side_effect=Denied('fixture setup failed')), \
             patch('os.close') as close:
            with self.assertRaises(Denied):
                PipeTransport.from_observation(observation, handoff_state=state)
        self.assertEqual(state, {'pipes_transferred': True})
        self.assertEqual([call.args[0] for call in close.call_args_list], [31,32,33])

    def test_original_close_failure_attempts_remaining_descriptors_and_stays_unknown(self):
        observation = dict(state='CREATED_NOT_EXEC_ATTESTED', engine_stdout_fd=31,
                           engine_stdin_fd=32, engine_stderr_fd=33)
        state = {}
        with patch.object(PipeTransport, '__init__', side_effect=Denied('fixture setup failed')), \
             patch('os.close', side_effect=[OSError('fixture close failed'),None,None]) as close:
            with self.assertRaises(Unknown):
                PipeTransport.from_observation(observation, handoff_state=state)
        self.assertEqual(state, {'pipes_transferred': True})
        self.assertEqual(close.call_count, 3)


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os,'pidfd_open'), 'Linux parent FD checks')
class LinuxHandleTests(unittest.TestCase):
    def setUp(self):
        self.owned = set()
        def pipe():
            pair = os.pipe()
            self.owned.update(pair)
            return pair
        out_r,out_w = pipe()
        in_r,in_w = pipe()
        err_r,err_w = pipe()
        pidfd = os.pidfd_open(os.getpid())
        self.owned.add(pidfd)
        self.observation = dict(pid=os.getpid(),pidfd=pidfd,host_boot_id='fixture-boot',
            cgroup_inode=111,state='CREATED_NOT_EXEC_ATTESTED',engine_stdout_fd=out_r,
            engine_stdin_fd=in_w,engine_stderr_fd=err_r)
        self.closer = LaunchObservationCloser(expected_host_boot_id='fixture-boot',expected_cgroup_inode=111)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for fd in self.owned:
            try:os.close(fd)
            except OSError:pass

    def test_before_handoff_closes_all_parent_handles_once(self):
        self.closer.register(self.observation)
        self.closer(self.observation,pipes_transferred=False)
        for key in ('pidfd',)+PIPE_KEYS:
            with self.assertRaises(OSError):os.fstat(self.observation[key])
        self.closer(self.observation,pipes_transferred=False)

    def test_after_transfer_keeps_transport_duplicates_alive(self):
        self.closer.register(self.observation)
        state={}
        transport=PipeTransport.from_observation(self.observation,handoff_state=state)
        self.addCleanup(transport.close)
        self.closer(self.observation,pipes_transferred=state['pipes_transferred'])
        for fd in transport.fds:os.fstat(fd)
        with self.assertRaises(OSError):os.fstat(self.observation['pidfd'])

    def test_failed_handoff_cannot_close_reused_pipe_descriptor(self):
        sentinel_r,sentinel_w=os.pipe()
        self.owned.update((sentinel_r,sentinel_w))
        self.closer.register(self.observation)
        state={}
        with patch.object(PipeTransport,'__init__',side_effect=Denied('fixture setup failed')):
            with self.assertRaises(Denied):
                PipeTransport.from_observation(self.observation,handoff_state=state)
        reused=self.observation['engine_stdout_fd']
        os.dup2(sentinel_r,reused)
        self.closer(self.observation,pipes_transferred=state['pipes_transferred'])
        os.fstat(reused)
        self.closer(self.observation,pipes_transferred=True)
        os.fstat(reused)

    def test_changed_descriptor_is_not_closed_and_failure_cannot_retry(self):
        self.closer.register(self.observation)
        target=self.observation['engine_stdout_fd']
        os.close(target)
        replacement=self.observation['engine_stderr_fd']
        os.dup2(replacement,target)
        with self.assertRaises(Unknown):self.closer(self.observation,pipes_transferred=False)
        os.fstat(target)
        with self.assertRaises(Unknown):self.closer(self.observation,pipes_transferred=False)
        os.fstat(target)

    def test_alias_or_unregistered_observation_never_closes(self):
        with self.assertRaises(Denied):self.closer(self.observation,pipes_transferred=False)
        altered=dict(self.observation,engine_stdin_fd=self.observation['engine_stdout_fd'])
        with self.assertRaises(Denied):self.closer.register(altered)
        for key in ('pidfd',)+PIPE_KEYS:os.fstat(self.observation[key])
