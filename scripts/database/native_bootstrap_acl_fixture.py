"""Explicit disposable compiler fixture, not a migration/deployment command.

Only call inside a NEW isolated test cluster. Source guards, files and manifest
remain inert. In-memory test copies omit only the outer transaction and known
DESIGN_ONLY marker, under a single fixture transaction.
"""
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())
ROLE='company_provisioning_runtime_r55'
FUNCTION='company_private.bootstrap_receipt_readback_v1(uuid,bigint,uuid,uuid,uuid,uuid,text,text,text,text)'


def fixture_body(path,index):
    text=path.read_text(encoding='utf-8')
    if not text.rstrip().endswith('ROLLBACK;'):raise RuntimeError('fixture source has no rollback boundary')
    text=text.rstrip()[:-len('ROLLBACK;')]
    text,count=re.subn(r'(?m)^BEGIN;[ \t]*\r?\n','',text,count=1)
    if count!=1:raise RuntimeError('fixture source has no single outer BEGIN')
    guard="DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;"
    expected_guards={45:0,50:3}.get(index,1)
    if text.count(guard)!=expected_guards:raise RuntimeError('fixture source guard mismatch:'+str(index))
    return text.replace(guard,'-- Exact DESIGN_ONLY marker omitted in this disposable fixture only.')


def native_catalog(admin,connect):
    import psycopg
    manifest=json.loads((ROOT/'database/assembly/assembly.json').read_text())
    if manifest['automatic_execution'] is not False or len(manifest['order'])!=85:
        raise RuntimeError('unexpected active assembly contract')
    bodies=[];pins={}
    for index,row in enumerate(manifest['order'],1):
        path=(ROOT/row['path']).resolve()
        if not path.is_relative_to((ROOT/'database/sources').resolve()):raise RuntimeError('native source escaped SQL root')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise RuntimeError('native fixture source hash mismatch')
        pins[row['path']]=row['sha256'];bodies.append(fixture_body(path,index))
    report=dict(source_files=len(pins),source_sha256=pins,scope='DISPOSABLE_COMPILE_NOT_APPLICATION_BOOTSTRAP')
    original=(ROOT/manifest['order'][0]['path']).read_text()
    try:admin.execute(original)
    except psycopg.errors.RaiseException as error:
        if 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED' not in str(error):raise
        report['original_guard_rejected']=True
    else:raise RuntimeError('original source guard did not reject')
    finally:admin.execute('ROLLBACK')
    # This externally supplied dependency exists only in this private test DB.
    # Active 084 refuses to create/approve a missing production provisioning role.
    admin.execute('CREATE ROLE '+ROLE+' LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION')
    fixture="BEGIN; SET LOCAL statement_timeout='20s';\n"+'\n'.join(bodies)+'\nCOMMIT;'
    report['derived_fixture_sha256']=hashlib.sha256(fixture.encode()).hexdigest()
    admin.execute(fixture)
    report['native_compile']='PASS'
    counts=admin.execute('SELECT (SELECT count(*) FROM company.projects),(SELECT count(*) FROM company.project_grants),(SELECT count(*) FROM company_private.bootstrap_receipts)').fetchone()
    if counts!=(0,0,0):raise RuntimeError('unexpected application data in empty native fixture')
    report['empty_projects_grants_bootstrap']=list(counts)
    owner=admin.execute("SELECT rolcanlogin,rolsuper,rolbypassrls,rolinherit FROM pg_roles WHERE rolname='company_bootstrap_readback_v1'").fetchone()
    if owner!=(False,False,False,False):raise RuntimeError('unsafe readback function owner')
    proc=admin.execute("SELECT p.prosecdef,p.proconfig,r.rolname,coalesce((SELECT bool_or(privilege_type='EXECUTE') FROM aclexplode(p.proacl) WHERE grantee=0),false) FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=%s::regprocedure",(FUNCTION,)).fetchone()
    if proc!=(True,['search_path=pg_catalog'],'company_bootstrap_readback_v1',False):
        raise RuntimeError('unsafe native function security/catalog ACL')
    raw=admin.execute("SELECT has_table_privilege(%s,'company_private.bootstrap_receipts','SELECT'),pg_has_role(%s,'company_bootstrap_readback_v1','MEMBER'),has_table_privilege('company_bootstrap_readback_v1','company_private.bootstrap_receipts','INSERT,UPDATE,DELETE')",(ROLE,ROLE)).fetchone()
    if raw!=(False,False,False):raise RuntimeError('readback accidentally grants raw read or write/owner membership')
    report['catalog_security']='PASS'
    # The complete native schema is empty; a permitted caller must reach the
    # witness check, not bypass RLS or receive a fabricated successful record.
    from company_os.bootstrap.bootstrap_readback import FIELDS, NATIVE_QUERY
    values={name:('a'*64 if name.endswith('digest') else str(uuid4())) for name in FIELDS};values['generation']=1
    with connect(ROLE) as connection:
        try:connection.execute(NATIVE_QUERY,tuple(values[name] for name in FIELDS))
        except psycopg.errors.RaiseException as error:
            if 'BOOTSTRAP_READBACK_WITNESS_MISMATCH' not in str(error):raise
            report['native_empty_witness_rejected']='PASS'
        else:raise RuntimeError('empty native schema returned a false bootstrap receipt')
    with connect(ROLE) as connection:
        try:connection.execute('SELECT installation_id FROM company_private.bootstrap_receipts')
        except psycopg.errors.InsufficientPrivilege:report['native_raw_table_read_denied']='PASS'
        else:raise RuntimeError('provisioning caller unexpectedly has raw table access')
    # Current bootstrap-window API must reach the native missing-enrollment
    # rejection under its real non-superuser provisioning identity.
    from company_os.bootstrap.bootstrap_window import QUERY as WINDOW_QUERY
    window_args=(str(uuid4()),1,'a'*64,str(uuid4()))
    with connect(ROLE) as connection:
        try:connection.execute(WINDOW_QUERY,window_args)
        except psycopg.errors.RaiseException as error:
            if 'CURRENT_BOOTSTRAP_WINDOW_NOT_ENROLLED' not in str(error):raise
            report['current_window_missing_enrollment_rejected']='PASS'
        else:raise RuntimeError('empty native schema returned current bootstrap authority')
    with connect(ROLE) as connection:
        try:connection.execute('SELECT company_private.r56_root_bounds(%s::uuid)',(window_args[0],))
        except psycopg.errors.InsufficientPrivilege:
            report['current_window_internal_function_not_exposed']='PASS'
        else:raise RuntimeError('internal root clock function exposed to caller')
    try:admin.execute(WINDOW_QUERY,window_args)
    except psycopg.errors.RaiseException as error:
        if 'BOOTSTRAP_WINDOW_PROVISIONER_REQUIRED' not in str(error):raise
        report['current_window_wrong_session_user_rejected']='PASS'
    else:raise RuntimeError('wrong session user accepted by current window API')
    window_proc=admin.execute("SELECT p.prosecdef,p.proconfig,r.rolname,coalesce((SELECT bool_or(privilege_type='EXECUTE') FROM aclexplode(p.proacl) WHERE grantee=0),false) FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid='company_private.bootstrap_window_readback_v1(uuid,bigint,text,uuid)'::regprocedure").fetchone()
    if window_proc!=(True,['search_path=pg_catalog'],'company_bootstrap_functions_r56',False):
        raise RuntimeError('unsafe bootstrap window function ACL')
    report['current_window_catalog_security']='PASS'
    return report,bodies[83]


def install_minimal_acl(admin,readback_body):
    # Roles are cluster-wide and already created by native_catalog. Only tables
    # are mirrored in this second test database; FKs/native triggers are NOT
    # represented here. Positive witness cases retain SYNTHETIC_NATIVE scope.
    body=re.sub(r'(?m)^CREATE ROLE company_bootstrap_readback_v1[^\n]*\n','',readback_body,count=1)
    admin.execute('BEGIN;'+body+';COMMIT;')
    tables=['company_private.bootstrap_receipts','company_private.installation_bootstrap_control',
            'company.principals','company.memberships','company.commands','company.audit_events','company.outbox']
    for table in tables:
        admin.execute('ALTER TABLE '+table+' ENABLE ROW LEVEL SECURITY')
        admin.execute('ALTER TABLE '+table+' FORCE ROW LEVEL SECURITY')
