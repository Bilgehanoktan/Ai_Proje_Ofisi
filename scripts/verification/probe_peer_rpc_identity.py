"""Finite distinct-UID IPC mechanism probe; never enrollment/runtime acceptance.

Coordinator must be Linux root solely to drop two finite test helpers to existing
UIDs 999 and 65534. No users, grants, namespaces, DBs or services are installed.
Peer/scope validators below are explicit fixtures, not enrolled policy.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())
if str(ROOT) not in sys.path:sys.path[:0] = [str(ROOT),str(ROOT/'product/backend'),str(ROOT/'contracts/source/python'),str(ROOT/'verifier/src')]
from company_os.runtime.ipc.peer_rpc import PeerRpcClient, PeerRpcService, UnixEndpoint

CLIENT=999
SERVER=65534


def server(folder):
    if os.geteuid()!=SERVER:raise RuntimeError('probe server UID mismatch')
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    try:
        listener.bind(str(folder/'rpc.sock'));os.chmod(folder/'rpc.sock',0o660)
        listener.listen(1);listener.settimeout(5)
        (folder/'ready').write_text('ready')
        connection,_=listener.accept()
        peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        handler=SimpleNamespace(handle=lambda operation,**kw:dict(server_uid=os.geteuid(),peer_uid=peer[1],echo=kw['expected']))
        service=PeerRpcService(client_uid=CLIENT,peer_validator=SimpleNamespace(validate=lambda **kw:True),
            handler=handler,journal=None,timeout=3)
        service.serve_connection(connection)
    finally:listener.close()
    return 0


def client(folder):
    if os.geteuid()!=CLIENT:raise RuntimeError('probe client UID mismatch')
    fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        rpc=PeerRpcClient(endpoint=UnixEndpoint(directory_fd=fd,name='rpc.sock',server_uid=SERVER),
            server_uid=SERVER,peer_validator=SimpleNamespace(validate=lambda **kw:True),timeout=3)
        result=rpc.call('stop.observe',expected={'probe':'fixture-only'})
        print(json.dumps(dict(client_uid=os.geteuid(),measured_server_uid=rpc.last_peer['uid'],result=result)))
    finally:os.close(fd)
    return 0


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--role',choices=['server','client']);parser.add_argument('--directory')
    args=parser.parse_args()
    if args.role:
        return server(Path(args.directory)) if args.role=='server' else client(Path(args.directory))
    if sys.platform!='linux' or os.geteuid()!=0:
        print(json.dumps(dict(status='BLOCKED',reason='LINUX_UID_DROP_PROBE_COORDINATOR_REQUIRED')));return 2
    gid=pwd.getpwuid(CLIENT).pw_gid;pwd.getpwuid(SERVER)
    def drop(uid):
        def apply():os.setgroups([]);os.setgid(gid);os.setuid(uid)
        return apply
    child=None
    with tempfile.TemporaryDirectory(prefix='aipof-peer-probe-') as folder:
        path=Path(folder);os.chown(path,SERVER,gid);os.chmod(path,0o750)
        try:
            child=subprocess.Popen([sys.executable,'-B',__file__,'--role','server','--directory',str(path)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,preexec_fn=drop(SERVER))
            deadline=time.monotonic()+5
            while not (path/'ready').exists():
                if child.poll() is not None or time.monotonic()>deadline:raise RuntimeError('bounded probe server did not start')
                time.sleep(.01)
            result=subprocess.run([sys.executable,'-B',__file__,'--role','client','--directory',str(path)],
                capture_output=True,text=True,timeout=5,preexec_fn=drop(CLIENT))
            output,errors=child.communicate(timeout=5)
            if result.returncode or child.returncode:
                raise RuntimeError('probe helper failed: '+result.stderr+errors)
            data=json.loads(result.stdout)
            assert data['client_uid']==CLIENT and data['measured_server_uid']==SERVER
            assert data['result']['server_uid']==SERVER and data['result']['peer_uid']==CLIENT
            print(json.dumps(dict(status='PASS',scope='DISTINCT_UID_IPC_MECHANISM_ONLY_NOT_ENROLLMENT',
                actual=data,helpers_stopped=True)))
        finally:
            if child is not None and child.poll() is None:child.kill();child.communicate(timeout=2)
    return 0


if __name__=='__main__':raise SystemExit(main())
