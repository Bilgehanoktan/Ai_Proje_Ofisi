"""Actual Linux packet/SCM_RIGHTS tests with fixture UID context; not enrollment."""
import os
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from company_os.runtime.ipc import peer_rpc as rpc
from company_os.kernel.execution_protocol import Denied, Unknown
from company_os.runtime.supervisor.supervisor_service import RemoteReceiptValidator, RemoteStopObserver, VerificationReceiptStore
from tests.unit.test_runtime_verification import binding


class PortTests(unittest.TestCase):
    def test_deadlines_and_unregistered_operations_are_rejected(self):
        for timeout in (0,-1,float('inf'),True):
            with self.assertRaises(Denied):rpc.PeerRpcClient(endpoint=None,server_uid=1002,peer_validator=None,timeout=timeout)
        with self.assertRaises(Denied):rpc._decode(b'{"id":1,"id":2}')

    def test_receipt_integer_true_is_not_boolean_confirmation(self):
        port=SimpleNamespace(call=lambda *a,**kw:dict(valid=1))
        self.assertFalse(RemoteReceiptValidator(port).validate({},expected=binding()))

    def test_remote_stop_ack_loss_retains_scope_for_cleanup_without_rebind(self):
        calls=[]
        def call(operation,**kwargs):
            calls.append(operation)
            if operation=='stop.bind':raise Unknown('fixture lost acknowledgement')
            return dict(closed=True)
        subject=RemoteStopObserver(SimpleNamespace(call=call))
        observation=dict(pid=1,pidfd=10,host_boot_id='fixture',cgroup_inode=1,state='CREATED_NOT_EXEC_ATTESTED')
        with self.assertRaises(Unknown):subject.bind(expected={'id':'fixture'},observation=observation)
        subject.close();subject.close()
        self.assertEqual(calls,['stop.bind','stop.close'])
        with self.assertRaises(Denied):subject.bind(expected={'id':'fixture'},observation=observation)


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()>0,'Rootless Linux seqpacket/SCM_RIGHTS')
class LinuxRpcTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.threads=[];self.received=[];self.keys=set()
        self.reject=False;self.delay=0
        actual_uid=os.geteuid()
        self.uid=actual_uid
        # Explicit identity-context double. Actual same-UID rejection has its own
        # test; this positive transport test does not prove separate identities.
        self.fixture_uid=actual_uid+10000
        test=self
        class Journal:
            def reserve(self,scope,identity,record):
                key=(scope,identity)
                if key in test.keys:raise Unknown('fixture durable intent exists')
                test.keys.add(key)
        class Handler:
            def handle(self,operation,*,expected,payload,descriptors,deadline):
                if test.delay:time.sleep(test.delay)
                if descriptors:
                    test.received.append(descriptors[0])
                    return dict(content=os.read(descriptors[0],32).decode())
                return dict(expected=expected,operation=operation)
        self.handler=Handler()
        self.validator=SimpleNamespace(validate=lambda **kw:not self.reject)
        self.service=rpc.PeerRpcService(client_uid=actual_uid,peer_validator=self.validator,
                  handler=self.handler,journal=Journal(),timeout=1,uid_reader=lambda:self.fixture_uid)
        class Endpoint:
            def connect(self,*,timeout):
                client,server=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
                def serve():
                    try:test.service.serve_connection(server)
                    except Exception as exc:test.errors.append(exc)
                thread=threading.Thread(target=serve,daemon=True);test.threads.append(thread);thread.start()
                return client
        self.client=rpc.PeerRpcClient(endpoint=Endpoint(),server_uid=actual_uid,peer_validator=self.validator,
                    timeout=1,uid_reader=lambda:self.fixture_uid)
        self.addCleanup(self.join)

    def join(self):
        for thread in self.threads:thread.join(timeout=2)

    def test_packet_exchange_is_exact_and_current_peer_is_rechecked(self):
        result=self.client.call('stop.observe',expected={'task':'fixture'})
        self.assertEqual(result,dict(expected={'task':'fixture'},operation='stop.observe'))
        self.assertEqual(self.client.last_peer['uid'],self.uid)
        self.join();self.assertEqual(self.errors,[])

    def test_actual_same_uid_is_rejected_with_default_uid_reader(self):
        self.client.uid_reader=os.geteuid
        with self.assertRaises(Denied):self.client.call('stop.observe',expected={})

    def test_scm_rights_received_handle_is_closed_but_sender_handle_survives(self):
        read,write=os.pipe()
        try:
            os.write(write,b'fixture');os.close(write);write=None
            result=self.client.call('stop.bind',expected={'task':'fixture'},
                     payload={},descriptors=(read,))
            self.assertEqual(result,dict(content='fixture'))
            self.join();os.fstat(read)
            self.assertEqual(len(self.received),1)
            with self.assertRaises(OSError):os.fstat(self.received[0])
        finally:
            os.close(read)
            if write is not None:os.close(write)

    def test_lost_reply_or_duplicate_oneshot_never_reinvokes_action(self):
        expected={'task':'fixture'}
        self.client.call('verification.run',expected=expected)
        with self.assertRaises(Unknown):self.client.call('verification.run',expected=expected)
        self.assertEqual(len(self.keys),1)

    def test_timeout_has_no_automatic_reconnect_or_retry(self):
        self.client.timeout=.05;self.delay=.2
        with self.assertRaises(Unknown):self.client.call('verification.run',expected={})
        self.assertEqual(len(self.threads),1)

    def test_revoked_peer_never_invokes_handler(self):
        self.reject=True
        with self.assertRaises(Denied):self.client.call('verification.run',expected={})
        self.assertEqual(self.keys,set())

    def test_peer_revocation_after_response_never_releases_result(self):
        from unittest.mock import Mock
        self.client.validator=SimpleNamespace(validate=Mock(side_effect=[True,False]))
        with self.assertRaises(Denied):self.client.call('verification.run',expected={'task':'fixture'})
        self.assertEqual(len(self.keys),1)

    def test_invalid_packet_closes_received_descriptor_and_keeps_sender_descriptor(self):
        import array
        from unittest.mock import patch
        left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        read,write=os.pipe();closed=[];original=os.close
        try:
            left.sendmsg([b'{"a":1,"a":2}'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[read]))])
            def close(fd):closed.append(fd);original(fd)
            with patch.object(rpc.os,'close',side_effect=close):
                with self.assertRaises(Denied):rpc._receive(right,time.monotonic()+1)
            self.assertEqual(len(closed),1)
            os.fstat(read)
            with self.assertRaises(OSError):os.fstat(closed[0])
        finally:
            left.close();right.close();os.close(read);os.close(write)

    def test_private_receipt_store_is_exact_append_only_and_survives_reopen(self):
        if os.geteuid()==0:self.skipTest('rootless service receipt store')
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory,0o700)
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:
                expected=binding();report=dict(expected=expected,report_digest='a'*64)
                store=VerificationReceiptStore(directory_fd=fd,owner_uid=os.geteuid())
                store.append(expected=expected,report=report)
                self.assertTrue(store.matches(expected=expected,report=report))
                self.assertFalse(store.matches(expected=expected,report=dict(report,report_digest='b'*64)))
                reopened=VerificationReceiptStore(directory_fd=fd,owner_uid=os.geteuid())
                self.assertTrue(reopened.matches(expected=expected,report=report))
                with self.assertRaises(Unknown):store.append(expected=expected,report=report)
            finally:os.close(fd)
