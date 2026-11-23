"""Dedicated local PostgreSQL foundation, not application/native acceptance.

Explicit prepare→initialize→start actions. No existing cluster reuse/overwrite,
no SQL assembly execution, role/session/grant issuance or recursive deletion.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

BASE=Path('/var/lib/ai-proje-ofisi-local')
BIN=Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/postgresql/18/bin')
LIB=Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/x86_64-linux-gnu')
WORKSPACE='E:\\Projeler\\Ai_Proje_Ofisi'
OWNER='aipof-dbtest'
PORT=55490
DATABASE='ai_proje_ofisi'
SCOPE='POSTGRES_FOUNDATION_ONLY_NOT_APPLICATION_ACCEPTANCE'
CONFIG="""# Dedicated local foundation; no application schema installed.
listen_addresses = ''
port = 55490
unix_socket_permissions = 0700
shared_buffers = '16MB'
work_mem = '1MB'
maintenance_work_mem = '16MB'
max_connections = 8
max_worker_processes = 0
max_parallel_workers = 0
dynamic_shared_memory_type = 'mmap'
max_wal_size = '64MB'
min_wal_size = '32MB'
statement_timeout = '2s'
lock_timeout = '2s'
idle_in_transaction_session_timeout = '5s'
"""


class SetupBlocked(ValueError): pass


def require_uid(root=False):
    if sys.platform!='linux':raise SetupBlocked('LINUX_LOCAL_SETUP_REQUIRED')
    import pwd
    account=pwd.getpwnam(OWNER)
    if account.pw_uid!=999 or os.geteuid()!=(0 if root else account.pw_uid):
        raise SetupBlocked('EXACT_EXISTING_SETUP_OS_IDENTITY_REQUIRED')
    return account


def base_path():
    if BASE.is_symlink() or BASE.resolve()!=BASE:
        raise SetupBlocked('EXACT_LOCAL_SETUP_DIRECTORY_REQUIRED')
    return BASE


def binary_digest():
    path=BIN/'postgres'
    if not path.is_file():raise SetupBlocked('EXISTING_POSTGRES_BINARY_REQUIRED')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    account=require_uid(root=True);base=base_path()
    if base.exists():raise SetupBlocked('TARGET_EXISTS_NO_OVERWRITE')
    digest=binary_digest()
    os.umask(0o077)
    base.mkdir(mode=0o700)
    os.chown(base,account.pw_uid,account.pw_gid)
    for name in ('data','socket'):
        path=base/name;path.mkdir(mode=0o700);os.chown(path,account.pw_uid,account.pw_gid)
    marker=dict(version=1,canonical_workspace=WORKSPACE,owner_uid=account.pw_uid,
        owner_gid=account.pw_gid,postgres_sha256=digest,scope=SCOPE)
    with (base/'INSTANCE.json').open('x',encoding='utf-8') as output:json.dump(marker,output,indent=2)
    os.chown(base/'INSTANCE.json',account.pw_uid,account.pw_gid)
    return dict(status='DIRECTORY_PREPARED',scope=SCOPE,application_schema_installed=False)


def checked_layout():
    account=require_uid();base=base_path()
    for path in (base,base/'data',base/'socket'):
        info=path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=account.pw_uid
                or stat.S_IMODE(info.st_mode)!=0o700):
            raise SetupBlocked('PRIVATE_OWNED_LOCAL_DIRECTORY_REQUIRED')
    marker_path=base/'INSTANCE.json'
    info=marker_path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=account.pw_uid
            or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>4096):
        raise SetupBlocked('EXACT_LOCAL_INSTANCE_MARKER_REQUIRED')
    marker=json.loads(marker_path.read_text('utf-8'))
    expected=dict(version=1,canonical_workspace=WORKSPACE,owner_uid=account.pw_uid,
        owner_gid=account.pw_gid,postgres_sha256=binary_digest(),scope=SCOPE)
    if marker!=expected:raise SetupBlocked('LOCAL_INSTANCE_MARKER_MISMATCH')
    return base


def command(args):
    env=dict(os.environ,LD_LIBRARY_PATH=str(LIB))
    result=subprocess.run([str(x) for x in args],env=env,capture_output=True,text=True,timeout=25)
    if result.returncode:raise SetupBlocked('POSTGRES_CONTROL_FAILED')
    return result


def initialize():
    base=checked_layout();data=base/'data'
    if any(data.iterdir()):raise SetupBlocked('DATA_NOT_EMPTY_NO_INITIALIZATION')
    os.umask(0o077)
    command([BIN/'initdb','-D',data,'-U',OWNER,'--encoding=UTF8','--locale=C',
             '--auth-local=peer','--auth-host=reject'])
    with (data/'aipof-local.conf').open('x',encoding='utf-8') as output:
        output.write(CONFIG+"unix_socket_directories = '"+str(base/'socket')+"'\n")
    with (data/'postgresql.conf').open('a',encoding='utf-8') as output:
        output.write("\ninclude = 'aipof-local.conf'\n")
    return dict(status='EMPTY_CLUSTER_INITIALIZED',scope=SCOPE,application_schema_installed=False)


def running(base):
    result=subprocess.run([str(BIN/'pg_ctl'),'-D',str(base/'data'),'status'],
        env=dict(os.environ,LD_LIBRARY_PATH=str(LIB)),capture_output=True,text=True,timeout=5)
    return result.returncode==0


def connect_database(base,database):
    import psycopg
    socket=base/'socket'/('.s.PGSQL.'+str(PORT));info=socket.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=999 or stat.S_IMODE(info.st_mode)!=0o700:
        raise SetupBlocked('PRIVATE_LOCAL_POSTGRES_SOCKET_REQUIRED')
    no_password=base/'NO_PASSWORD_FILE'
    if no_password.exists() or no_password.is_symlink():
        raise SetupBlocked('PASSWORD_FILE_NOT_ALLOWED_FOR_LOCAL_PEER')
    return psycopg.connect(host=str(base/'socket'),port=PORT,user=OWNER,dbname=database,
        passfile=str(no_password),connect_timeout=3,application_name='aipof-local-foundation')


def probe(base):
    with connect_database(base,DATABASE) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(),session_user,current_setting('listen_addresses'),"
                "current_setting('unix_socket_permissions'),current_setting('data_directory'),pg_is_in_recovery()")
            if cursor.fetchone()!=(DATABASE,OWNER,'','0700',str(base/'data'),False):
                raise SetupBlocked('LOCAL_SERVER_CONFIGURATION_MISMATCH')
            cursor.execute("SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname IN ('company','company_private')")
            schemas=cursor.fetchone()[0]
            cursor.execute('SELECT type,auth_method,error FROM pg_catalog.pg_hba_file_rules')
            auth=cursor.fetchall()
            if (not auth or not any(kind=='local' for kind,_,_ in auth)
                    or any(error is not None or (method!='peer' if kind=='local' else method!='reject')
                           for kind,method,error in auth)):
                raise SetupBlocked('LOCAL_PEER_AUTH_POLICY_MISMATCH')
    return dict(status='LOCAL_POSTGRES_RUNNING',scope=SCOPE,database=DATABASE,port=PORT,
        tcp_enabled=False,local_auth='PEER_OS_IDENTITY',auth_policy_readback_verified=True,socket_permissions='0700',
        application_schema_installed=False if schemas==0 else None,application_schema_count=schemas,
        application_schema_status='NOT_INSTALLED' if schemas==0 else 'NOT_VERIFIED',
        application_session_issued=False,task_execution_verified=False)


def start():
    base=checked_layout()
    if (base/'data/PG_VERSION').read_text().strip()!='18':raise SetupBlocked('POSTGRES18_CLUSTER_REQUIRED')
    os.umask(0o077)
    if not running(base):command([BIN/'pg_ctl','-D',base/'data','-l',base/'postgres.log','-w','-t','15','start'])
    # This creates only one EMPTY application database. No native guarded source
    # is applied and no user, role, enrollment, session or grant is invented.
    connection=connect_database(base,'postgres');connection.autocommit=True
    try:
        if connection.execute("SELECT current_setting('data_directory')").fetchone()!=(str(base/'data'),):
            raise SetupBlocked('LOCAL_DATA_DIRECTORY_MISMATCH')
        if not connection.execute('SELECT 1 FROM pg_catalog.pg_database WHERE datname=%s',(DATABASE,)).fetchone():
            connection.execute('CREATE DATABASE '+DATABASE)
    finally:connection.close()
    return probe(base)


def inspect():
    base=checked_layout()
    if not running(base):return dict(status='LOCAL_POSTGRES_STOPPED',scope=SCOPE)
    return probe(base)


def stop():
    base=checked_layout()
    if running(base):command([BIN/'pg_ctl','-D',base/'data','-m','fast','-w','-t','15','stop'])
    if running(base):raise SetupBlocked('LOCAL_STOP_NOT_CONFIRMED')
    return dict(status='LOCAL_POSTGRES_STOPPED_DATA_PRESERVED',scope=SCOPE)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','initialize','start','inspect','stop'))
    args=parser.parse_args()
    try:
        result=globals()[args.action]()
        print(json.dumps(result));return 0
    except SetupBlocked as error:
        print(json.dumps(dict(status='BLOCKED',reason=str(error),scope=SCOPE)));return 2
    except Exception:
        print(json.dumps(dict(status='BLOCKED',reason='LOCAL_POSTGRES_ACTION_FAILED',scope=SCOPE)));return 2


if __name__=='__main__':raise SystemExit(main())
