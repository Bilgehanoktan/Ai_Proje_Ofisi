"""Profile/observer behavior with explicit doubles; Linux probes are not qualification."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from company_os.runtime.observers.observer_profile import ObserverProfile, load_observer_profile
from company_os.runtime.observers import linux_observer as observer
from company_os.kernel.execution_protocol import Denied, Unknown

WORKSPACE=r'E:\Projeler\Ai_Proje_Ofisi'


def profile_data():
    return dict(version='company.linux-observer-profile/1',canonical_workspace=WORKSPACE,
        host_boot_id=str(uuid4()),worker_uid=1001,controller_uid=1001,observer_uid=1002,
        namespace_inodes=dict(user=11,mnt=12,net=13,pid=14),
        host_namespace_inodes=dict(user=21,mnt=22,net=23,pid=24),
        cgroup_inode=111,cgroup_path='/fixture-worker',
        resource_limits={'memory.max':'1048576','pids.max':'1','cpu.max':'50000 100000'},
        executable_digest='a'*64,native_library_digest='b'*64,source_digest='c'*64,
        enrollment_digest='d'*64,not_after_boottime_ns=10_000_000_000)


def profile(data):
    raw=json.dumps(data).encode()
    return ObserverProfile(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),canonical_workspace=WORKSPACE)


class ProfileTests(unittest.TestCase):
    def test_external_pin_scope_and_immutable_view(self):
        data=profile_data();p=profile(data)
        changed=p.data;changed['worker_uid']=0
        self.assertEqual(p.data['worker_uid'],1001)
        raw=json.dumps(data).encode()
        for pin,workspace in [('0'*64,WORKSPACE),(hashlib.sha256(raw).hexdigest(),'wrong-workspace')]:
            with self.assertRaises(Denied):ObserverProfile(raw,expected_sha256=pin,canonical_workspace=workspace)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json';path.write_bytes(raw)
            self.assertEqual(load_observer_profile(path,expected_sha256=p.sha256,
                                                  canonical_workspace=WORKSPACE).data,data)
            path.write_bytes(raw+b' ')
            with self.assertRaises(Denied):load_observer_profile(path,expected_sha256=p.sha256,canonical_workspace=WORKSPACE)

    def test_root_alias_unbounded_or_incomplete_profile_is_rejected(self):
        base=profile_data()
        cases=[dict(worker_uid=0),dict(observer_uid=1001),dict(observer_uid=True),
               dict(controller_uid=1002),dict(cgroup_path='/'),dict(cgroup_path='/a/../b'),
               dict(namespace_inodes=base['host_namespace_inodes']),dict(executable_digest='x'*64),
               dict(resource_limits=dict(base['resource_limits'],**{'memory.max':'max'})),
               dict(resource_limits=dict(base['resource_limits'],**{'cpu.max':'0 100000'}))]
        for change in cases:
            with self.subTest(change=change),self.assertRaises(Denied):profile(dict(base,**change))
        for key in base:
            changed=copy.deepcopy(base);del changed[key]
            with self.subTest(missing=key),self.assertRaises(Denied):profile(changed)

    def test_duplicate_unknown_fields_and_oversize_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'x'*32769):
            with self.assertRaises(Denied):ObserverProfile(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),canonical_workspace=WORKSPACE)
        with self.assertRaises(Denied):profile(dict(profile_data(),verified=True))


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.data=profile_data();self.profile=profile(self.data)
        self.context=dict(observer_uid=1002,host_boot_id=self.data['host_boot_id'],boottime_ns=1)
        self.expected=dict(process_id=str(uuid4()),capability_id=str(uuid4()),tuple_digest='e'*64,
                           host_boot_id=self.data['host_boot_id'],controller_generation=1,cgroup_inode=111)
        self.observation=dict(pid=100,pidfd=42,host_boot_id=self.data['host_boot_id'],cgroup_inode=111,
                              state='CREATED_NOT_EXEC_ATTESTED')
        self.process=dict(pid=100,starttime=123,uid=[1001]*4,namespace_inodes=self.data['namespace_inodes'],
            cgroup_membership='0::/fixture-worker',executable_digest='a'*64,executable_seals=15,
            no_new_privs=1,seccomp=2,capabilities=dict(CapEff=0,CapPrm=0,CapInh=0,CapAmb=0),descriptors=[0,1,2])
        self.group=dict(inode=111,resource_limits=self.data['resource_limits'],processes=[100],populated=1)
        self.proc_reader=SimpleNamespace(capture=lambda **kwargs:copy.deepcopy(self.process))
        self.cgroup_reader=SimpleNamespace(capture=lambda fd:copy.deepcopy(self.group))
        self.subject=observer.LinuxLaunchObserver(profile=self.profile,cgroup_fd=43,
            proc_reader=self.proc_reader,cgroup_reader=self.cgroup_reader,context_reader=lambda:copy.deepcopy(self.context))
        self.enrollment=SimpleNamespace(validate=lambda **kwargs:True) # Explicit fixture, not real enrollment.

    def measure(self):return self.subject.observe(expected=self.expected,observation=self.observation)

    def test_launch_measurement_is_rechecked_before_validator_accepts(self):
        measured=self.measure()
        validator=observer.LinuxLaunchObservationValidator(observer=self.subject,enrollment_reader=self.enrollment)
        self.assertTrue(validator.validate(measured,expected=self.expected))
        self.assertEqual(measured['outcome'],'RUNNING')
        self.assertNotIn('acceptance_eligible',measured)
        self.process['starttime']+=1
        with self.assertRaises(Denied):validator.validate(measured,expected=self.expected)

    def test_missing_or_revoked_enrollment_never_validates(self):
        measured=self.measure()
        for enrollment in [None,SimpleNamespace(validate=lambda **kwargs:False)]:
            with self.assertRaises(Denied):
                observer.LinuxLaunchObservationValidator(observer=self.subject,enrollment_reader=enrollment).validate(measured,expected=self.expected)
        with patch.object(self.enrollment,'validate',side_effect=[True,False]):
            with self.assertRaisesRegex(Denied,'ENROLLMENT_CHANGED_DURING_MEASUREMENT'):
                observer.LinuxLaunchObservationValidator(observer=self.subject,
                    enrollment_reader=self.enrollment).validate(measured,expected=self.expected)

    def test_changed_uid_namespace_executable_fd_or_privilege_is_rejected(self):
        original=copy.deepcopy(self.process)
        changes=[dict(uid=[0]*4),dict(namespace_inodes=self.data['host_namespace_inodes']),
                 dict(executable_digest='f'*64),dict(executable_seals=7),dict(no_new_privs=0),
                 dict(seccomp=0),dict(capabilities=dict(CapEff=1,CapPrm=0,CapInh=0,CapAmb=0)),
                 dict(capabilities={}),dict(descriptors=[0,1,2,7])]
        for change in changes:
            self.process=dict(original,**change)
            with self.subTest(change=change),self.assertRaises(Denied):self.measure()

    def test_expired_boot_or_observer_identity_stops_measurement(self):
        original=copy.deepcopy(self.context)
        for change in [dict(observer_uid=1001),dict(host_boot_id=str(uuid4())),dict(boottime_ns=10_000_000_000)]:
            self.context=dict(original,**change)
            with self.subTest(change=change),self.assertRaises(Denied):self.measure()

    def test_cgroup_race_extra_process_or_changed_limit_rejected(self):
        for change in [dict(processes=[100,101]),dict(inode=222),dict(resource_limits={})]:
            original=copy.deepcopy(self.group);self.group.update(change)
            with self.subTest(change=change),self.assertRaises(Denied):self.measure()
            self.group=original
        values=[copy.deepcopy(self.group),dict(self.group,populated=0)]
        with patch.object(self.cgroup_reader,'capture',side_effect=values):
            with self.assertRaises(Denied):self.measure()

    def stop_subject(self):
        measured=self.measure()
        expected=dict(self.expected,process_identity_digest=measured['process_identity_digest'])
        authority=SimpleNamespace(read=lambda **kwargs:dict(identity=copy.deepcopy(expected),
                        workspace_fenced=True,no_respawn_intent=True,usage_zero=True))
        subject=observer.LinuxStopObserver(profile=self.profile,cgroup_fd=43,observer_id=str(uuid4()),
            authoritative_readback=authority,proc_reader=self.proc_reader,cgroup_reader=self.cgroup_reader,
            context_reader=lambda:copy.deepcopy(self.context),exit_reader=lambda fd:True)
        return subject,expected,authority

    def bind_stop(self,subject,expected):
        with patch.object(observer.os,'dup',return_value=44),              patch.object(observer.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=123)):
            subject.bind(expected=expected,observation=self.observation)

    def test_stop_binds_same_process_and_requires_pidfd_exit_empty_cgroup_and_authority(self):
        subject,expected,authority=self.stop_subject();self.bind_stop(subject,expected)
        self.group.update(processes=[],populated=0)
        with patch.object(observer.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=123)):
            measured=subject.observe(expected=expected)
            validator=observer.LinuxStopObservationValidator(observer=subject,enrollment_reader=self.enrollment)
            self.assertTrue(validator.validate(measured,expected=expected))
            self.assertEqual(measured['outcome'],'EXITED')
            subject.exit_reader=lambda fd:False
            self.assertEqual(subject.observe(expected=expected)['outcome'],'RUNNING')
            subject.exit_reader=lambda fd:True
            authority.read=lambda **kwargs:dict(identity=expected,workspace_fenced=False,no_respawn_intent=True,usage_zero=True)
            with self.assertRaises(Denied):subject.observe(expected=expected)

    def test_foreign_pidfd_identity_cannot_be_bound_or_replaced(self):
        subject,expected,_=self.stop_subject()
        with self.assertRaises(Denied):subject.bind(expected=dict(expected,process_identity_digest='f'*64),observation=self.observation)
        self.bind_stop(subject,expected)
        with patch.object(observer.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=999)):
            with self.assertRaises(Denied):subject.observe(expected=expected)

    def test_stop_close_failure_is_unknown_and_does_not_retry_reused_descriptor(self):
        subject,expected,_=self.stop_subject();self.bind_stop(subject,expected)
        with patch.object(observer.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=123)),              patch.object(observer.os,'close',side_effect=OSError('fixture close failed')) as close:
            with self.assertRaises(Unknown):subject.close()
            with self.assertRaises(Unknown):subject.close()
            self.assertEqual(close.call_count,1)


@unittest.skipUnless(sys.platform=='linux' and hasattr(os,'pidfd_open'),'Linux proc/pidfd measurements')
class LinuxSensorTests(unittest.TestCase):
    def test_real_bounded_proc_capture_and_pidfd_exit_for_benign_source_test_child(self):
        process=subprocess.Popen(['/bin/sleep','3'])
        fd=None
        try:
            fd=os.pidfd_open(process.pid)
            reader=observer.LinuxProcReader()
            measured=reader.capture(pid=process.pid,pidfd=fd,require_sealed=False)
            self.assertEqual(measured['pid'],process.pid)
            self.assertEqual(measured['uid'],[os.getuid()]*4)
            self.assertGreater(measured['starttime'],0)
            self.assertFalse(observer.pidfd_exited(fd))
            with self.assertRaises(Denied):reader.capture(pid=process.pid,pidfd=fd)
            with self.assertRaises(Denied):reader.capture(pid=process.pid+1,pidfd=fd)
            process.terminate();process.wait(timeout=2)
            self.assertTrue(observer.pidfd_exited(fd))
            with self.assertRaises(Denied):reader.capture(pid=process.pid,pidfd=fd)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=2)
            if fd is not None:os.close(fd)

    def test_plain_directory_cannot_impersonate_cgroup_filesystem(self):
        with tempfile.TemporaryDirectory() as folder:
            fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaises(Denied):observer.LinuxCgroupReader().capture(fd)
            finally:os.close(fd)
