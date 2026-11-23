"""Finite synthetic PostgreSQL readback probe in a NEW private temporary cluster.

No existing cluster, native assembly, guard, mount or application data is used.
Minimal SQL contract fixture only; no root enrollment/first13 authorization.
Temporary roles/data exist solely inside this cluster and disappear on cleanup.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from company_os.bootstrap_readback import read_bootstrap_receipt,read_native_bootstrap_receipt,FIELDS,QUERY,NATIVE_QUERY
from company_os.provisioning import ProvisioningBlocked

BIN=Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/postgresql/18/bin')
LIB=Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/x86_64-linux-gnu')
READER='aipof_readback_fixture'
DENIED='aipof_denied_fixture'

DDL="""
CREATE SCHEMA company; CREATE SCHEMA company_private;
CREATE TABLE company_private.bootstrap_receipts(installation_id uuid,generation bigint,tenant_id uuid,project_id uuid,accepted_human_id uuid,command_id uuid,payload_digest text,setup_manifest_digest text,initial_grants_digest text,r56_result_digest text,r56_final_proof jsonb);
CREATE TABLE company_private.installation_bootstrap_control(installation_id uuid,generation bigint,state text,payload_digest text,expected_tenant_id uuid,expected_project_id uuid,expected_human_id uuid);
CREATE TABLE company.principals(tenant_id uuid,id uuid,kind text);
CREATE TABLE company.memberships(tenant_id uuid,principal_id uuid,role text);
CREATE TABLE company.commands(tenant_id uuid,id uuid,principal_id uuid,operation text,state text,result_ref uuid,payload_digest text,r55_source_revision text,r55_result_digest text,r55_result_payload jsonb,r55_audit_id bigint,correlation_id uuid);
CREATE TABLE company.audit_events(tenant_id uuid,id bigint,kind text,actor_id uuid,correlation_id uuid);
CREATE TABLE company.outbox(tenant_id uuid,project_id uuid,event_instance_id uuid,kind text,project_sequence bigint,event_writer_generation bigint,payload jsonb,aggregate_id uuid,aggregate_revision bigint,event_digest text);
CREATE ROLE aipof_readback_fixture LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE aipof_denied_fixture LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA company,company_private TO aipof_readback_fixture,aipof_denied_fixture;
GRANT SELECT ON ALL TABLES IN SCHEMA company,company_private TO aipof_readback_fixture;
"""


def main(native=False):
    read_function=read_native_bootstrap_receipt if native else read_bootstrap_receipt
    reader_login='company_provisioning_runtime_r55' if native else READER
    database='postgres'
    if sys.platform!='linux' or os.geteuid()!=999:
        print(json.dumps(dict(status='BLOCKED',reason='EXISTING_LINUX_UID999_REQUIRED')));return 2
    import resource
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    import psycopg
    from psycopg.types.json import Jsonb
    env=dict(os.environ,LD_LIBRARY_PATH=str(LIB))
    folder=Path(tempfile.mkdtemp(prefix='aipof-reader-pg-')).resolve()
    if folder.parent!=Path('/tmp') or not folder.name.startswith('aipof-reader-pg-'):
        raise RuntimeError('unexpected probe temp directory')
    os.chmod(folder,0o700)
    data=folder/'data';socket=folder/'socket';socket.mkdir(mode=0o700)
    report=dict(scope='SYNTHETIC_NATIVE_MINIMAL_SQL_FIXTURE_NOT_ENROLLMENT_OR_FULL_ASSEMBLY',
                application_acceptance=False,stages={},negatives={},uid=os.geteuid(),native_acl_mode=native)
    if native:report['scope']='SYNTHETIC_NATIVE_FULL_CATALOG_ACL_PLUS_MINIMAL_POSITIVE_WITNESS_NOT_ENROLLMENT'
    admin=None;initialized=False;stopped=False
    def command(args,timeout=20):
        return subprocess.run([str(x) for x in args],env=env,capture_output=True,text=True,timeout=timeout)
    def connect(user):
        return psycopg.connect(host=str(socket),port=55489,dbname=database,user=user,connect_timeout=3)
    try:
        result=command([BIN/'initdb','-D',data,'-U','aipof-dbtest','--encoding=UTF8','--locale=C','--auth-local=trust','--auth-host=reject'])
        if result.returncode:raise RuntimeError('PRIVATE_INITDB_FAILED:'+result.stderr[-1000:])
        initialized=True
        options=f"-k {socket} -p 55489 -c listen_addresses='' -c unix_socket_permissions=0700 -c shared_buffers=16MB -c max_connections=5 -c max_worker_processes=0 -c max_parallel_workers=0 -c dynamic_shared_memory_type=mmap"
        result=command([BIN/'pg_ctl','-D',data,'-l',folder/'postgres.log','-o',options,'-w','-t','10','start'])
        if result.returncode:raise RuntimeError('PRIVATE_POSTGRES_START_FAILED:'+result.stderr[-1000:])
        admin=connect('aipof-dbtest');admin.autocommit=True
        if native:
            from tools.native_bootstrap_acl_fixture import native_catalog,install_minimal_acl
            report['native_catalog'],readback_body=native_catalog(admin,connect)
            from tools.native_root_reader_fixture import probe_root_reader
            report['native_root_reader']=probe_root_reader(admin,connect)
            admin.execute('CREATE DATABASE readback_fixture')
            admin.close();database='readback_fixture';admin=connect('aipof-dbtest');admin.autocommit=True
        admin.execute(DDL)
        report['postgres_version']=admin.execute('SHOW server_version').fetchone()[0]
        report['listen_addresses']=admin.execute('SHOW listen_addresses').fetchone()[0]
        report['socket_permissions']=admin.execute('SHOW unix_socket_permissions').fetchone()[0]
        if report['listen_addresses']!='' or report['socket_permissions']!='0700':
            raise RuntimeError('PRIVATE_SOCKET_CONFIGURATION_MISMATCH')
        report['fixture_local_auth']='TRUST_ONLY_INSIDE_PRIVATE_UID999_TEMP_DIRECTORY_NOT_PRODUCTION_POLICY'
        report['stages']['private_cluster_and_minimal_fixture']='PASS'
        expected={name:('a'*64 if name.endswith('digest') else str(uuid4())) for name in FIELDS}
        expected['generation']=1;expected['setup_manifest_digest']='b'*64;expected['initial_grants_digest']='c'*64
        i,t,p,h,c=(expected[name] for name in ('installation_id','tenant_id','project_id','accepted_human_id','command_id'))
        corr=str(uuid4())
        proof=dict(phase='COMMIT_CUT',installation_id=i,generation=1,manifest_digest=expected['payload_digest'])
        payload=dict(final_proof=proof,fixture=True)
        digest=admin.execute("SELECT encode(sha256(convert_to(jsonb_build_array(%s::uuid,%s::text,%s::uuid,%s::jsonb)::text,'UTF8')),'hex')",(c,expected['payload_digest'],i,Jsonb(payload))).fetchone()[0]
        expected['r56_result_digest']=digest
        event=dict(result_digest=digest,request_digest=expected['payload_digest'])
        event_digest=admin.execute("SELECT encode(sha256(convert_to(jsonb_build_array(%s::uuid,0,'InstallationBootstrapped',%s::jsonb)::text,'UTF8')),'hex')",(p,Jsonb(event))).fetchone()[0]
        admin.execute('INSERT INTO company_private.bootstrap_receipts VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',tuple(expected[name] for name in FIELDS)+(Jsonb(proof),))
        admin.execute("INSERT INTO company_private.installation_bootstrap_control VALUES(%s,1,'CONSUMED',%s,%s,%s,%s)",(i,expected['payload_digest'],t,p,h))
        admin.execute("INSERT INTO company.principals VALUES(%s,%s,'HUMAN')",(t,h))
        admin.execute("INSERT INTO company.memberships VALUES(%s,%s,'OWNER')",(t,h))
        admin.execute("INSERT INTO company.commands VALUES(%s,%s,%s,'trusted_setup.consume','SUCCEEDED',%s,%s,'r56',%s,%s,1,%s)",(t,c,h,i,expected['payload_digest'],digest,Jsonb(payload),corr))
        admin.execute("INSERT INTO company.audit_events VALUES(%s,1,'InstallationBootstrapped',%s,%s)",(t,h,corr))
        admin.execute("INSERT INTO company.outbox VALUES(%s,%s,%s,'InstallationBootstrapped',1,54,%s,%s,0,%s)",(t,p,c,Jsonb(event),p,event_digest))
        if native:install_minimal_acl(admin,readback_body)
        connections=[]
        class RecordingConnection:
            def __init__(self,connection):self.connection=connection
            @property
            def autocommit(self):return self.connection.autocommit
            @property
            def info(self):return self.connection.info
            @property
            def closed(self):return self.connection.closed
            def rollback(self):return self.connection.rollback()
            def close(self):return self.connection.close()
            def cursor(self):
                actual=self.connection.cursor()
                class RecordingCursor:
                    def __enter__(self):actual.__enter__();return self
                    def __exit__(self,*args):return actual.__exit__(*args)
                    def execute(self,statement,args=()):
                        if statement in (QUERY,NATIVE_QUERY):
                            actual.execute("SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation')")
                            read_only,isolation=actual.fetchone()
                            if (read_only,isolation)!=('on','repeatable read'):
                                raise RuntimeError('ACTUAL_READER_TRANSACTION_CONFIGURATION_MISMATCH')
                            report['stages']['actual_reader_transaction']=dict(read_only=read_only,isolation=isolation)
                        return actual.execute(statement,args)
                    def fetchone(self):return actual.fetchone()
                    def fetchall(self):return actual.fetchall()
                return RecordingCursor()
        def reader():
            connection=RecordingConnection(connect(reader_login));connections.append(connection);return connection
        positive=read_function(reader,expected=expected,expected_login=reader_login)
        if positive['readback']!='EXACT_COMMITTED_WITNESS_MATCH' or positive['authorization']!='NOT_VERIFIED':
            raise RuntimeError('UNEXPECTED_READER_RESULT')
        report['stages']['actual_query_driver_uuid_and_pg_jsonb_digest']='PASS'
        cases=[
          ('control_generation',"UPDATE company_private.installation_bootstrap_control SET generation=2",(),"UPDATE company_private.installation_bootstrap_control SET generation=1",()),
          ('owner_kind',"UPDATE company.principals SET kind='WORKER'",(),"UPDATE company.principals SET kind='HUMAN'",()),
          ('owner_membership',"UPDATE company.memberships SET role='VIEWER'",(),"UPDATE company.memberships SET role='OWNER'",()),
          ('command_digest',"UPDATE company.commands SET r55_result_digest=%s",('f'*64,),"UPDATE company.commands SET r55_result_digest=%s",(digest,)),
          ('command_payload',"UPDATE company.commands SET r55_result_payload='{}'::jsonb",(),"UPDATE company.commands SET r55_result_payload=%s",(Jsonb(payload),)),
          ('audit_kind',"UPDATE company.audit_events SET kind='wrong'",(),"UPDATE company.audit_events SET kind='InstallationBootstrapped'",()),
          ('event_digest',"UPDATE company.outbox SET event_digest=%s",('f'*64,),"UPDATE company.outbox SET event_digest=%s",(event_digest,)),
          ('event_generation',"UPDATE company.outbox SET event_writer_generation=53",(),"UPDATE company.outbox SET event_writer_generation=54",())]
        for name,mutation,args,restore,restore_args in cases:
            admin.execute(mutation,args)
            try:
                try:read_function(reader,expected=expected,expected_login=reader_login)
                except ProvisioningBlocked:report['negatives'][name]='REJECTED'
                else:raise RuntimeError('NEGATIVE_NOT_REJECTED:'+name)
            finally:admin.execute(restore,restore_args)
        for name,login,pins in [('wrong_login','wrong-login',expected),('foreign_scope',reader_login,dict(expected,project_id=str(uuid4())))]:
            try:read_function(reader,expected=pins,expected_login=login)
            except ProvisioningBlocked:report['negatives'][name]='REJECTED'
            else:raise RuntimeError('NEGATIVE_NOT_REJECTED:'+name)
        if native:
            with connect(DENIED) as denied:
                try:denied.execute(NATIVE_QUERY,tuple(expected[name] for name in FIELDS))
                except psycopg.errors.InsufficientPrivilege:report['negatives']['missing_native_execute_privilege']='REJECTED'
                else:raise RuntimeError('UNAUTHORIZED_NATIVE_READER_NOT_REJECTED')
        else:
            try:read_bootstrap_receipt(lambda:connect(DENIED),expected=expected,expected_login=DENIED)
            except ProvisioningBlocked:report['negatives']['missing_select_privilege']='REJECTED'
            else:raise RuntimeError('UNAUTHORIZED_READER_NOT_REJECTED')
        with connect(reader_login) as connection:
            try:connection.execute("INSERT INTO company.memberships VALUES(%s,%s,'OWNER')",(t,str(uuid4())))
            except psycopg.errors.InsufficientPrivilege:report['negatives']['reader_write_privilege']='REJECTED'
            else:raise RuntimeError('READER_CAN_WRITE')
        final=read_function(reader,expected=expected,expected_login=reader_login)
        report['stages']['final_independent_readback']='PASS' if final['readback']==positive['readback'] else 'FAIL'
        admin.close();admin=None
        restart=command([BIN/'pg_ctl','-D',data,'-l',folder/'postgres.log','-m','fast','-o',options,'-w','-t','10','restart'])
        if restart.returncode:raise RuntimeError('PRIVATE_POSTGRES_RESTART_FAILED')
        restarted=read_function(reader,expected=expected,expected_login=reader_login)
        if restarted!=positive:raise RuntimeError('PERSISTENT_RESTART_READBACK_CHANGED')
        report['stages']['persistent_readback_after_private_restart']='PASS'
        report['stages']['reader_connections_closed']=all(connection.closed for connection in connections)
        if report['stages']['final_independent_readback']!='PASS' or not report['stages']['reader_connections_closed']:
            raise RuntimeError('FINAL_READBACK_OR_CONNECTION_CLEANUP_FAILED')
        report['status']='PASS'
    except Exception as error:
        report['status']='FAIL';report['error_type']=type(error).__name__;report['error']=str(error)[:1500]
    finally:
        if admin is not None:admin.close()
        if initialized:
            try:
                result=command([BIN/'pg_ctl','-D',data,'-m','fast','-w','-t','10','stop'])
                report['stop_exit']=result.returncode
            except Exception as error:
                report['stop_error_type']=type(error).__name__
            stopped=not (data/'postmaster.pid').exists()
        else:stopped=True
        report['private_server_stopped']=stopped
        if stopped:
            # Only the uniquely created, resolved /tmp probe directory is removed.
            if folder.parent!=Path('/tmp') or not folder.name.startswith('aipof-reader-pg-'):
                raise RuntimeError('probe cleanup scope changed')
            shutil.rmtree(folder);report['temporary_cluster_removed']=not folder.exists()
        else:
            report['temporary_cluster_removed']=False
            report['preserved_probe_directory']=str(folder)
        report['existing_clusters_touched']=False
        report['query_sha256']=hashlib.sha256((NATIVE_QUERY if native else QUERY).encode()).hexdigest()
        report['fixture_ddl_sha256']=hashlib.sha256(DDL.encode()).hexdigest()
        print(json.dumps(report,ensure_ascii=False))
    return 0 if report.get('status')=='PASS' and stopped and report.get('temporary_cluster_removed') else 1


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--native-acl',action='store_true')
    raise SystemExit(main(parser.parse_args().native_acl))
