"""Native plan and missing-root denial; never synthesize identity/clock proof."""
from datetime import datetime,timezone
from uuid import uuid4

from company_os.kernel.session_provisioning import OWNER_BINDING_SQL, PRINCIPAL_BINDING_SQL, issue_owner_session


def probe_session_guards(admin,connect):
    import psycopg
    report={'scope':'NATIVE_SQL_PLAN_AND_NEGATIVE_NOT_REAL_SESSION_ISSUANCE'}
    installation,principal=str(uuid4()),str(uuid4())
    lower=datetime(2026,11,14,12,tzinfo=timezone.utc)
    upper=datetime(2026,11,14,12,0,1,tzinfo=timezone.utc)
    owner_args=(lower,30,installation,1,upper)
    principal_args=(lower,30,principal,'WORKER',installation,1,upper)
    for name,sql,args in [('owner',OWNER_BINDING_SQL,owner_args),('principal',PRINCIPAL_BINDING_SQL,principal_args)]:
        for locked in (False,True):
            # EXPLAIN without ANALYZE type-checks the real full native schema;
            # it does not execute root/time functions or lock actual records.
            suffix=' FOR SHARE OF b,d,p,m,c' if locked else ''
            plan=admin.execute('EXPLAIN '+sql+suffix,args).fetchall()
            if not plan:raise RuntimeError('missing native session binding plan')
            report[name+('_locked_plan' if locked else '_plan')]='PASS'
    with connect('aipof-dbtest') as connection:
        try:
            with connection.cursor() as cursor:
                issue_owner_session(cursor,installation_id=installation,
                    token='synthetic-session-not-created-'*2,ttl_seconds=30)
        except psycopg.errors.RaiseException as error:
            if 'ROOT_TRUST_ANCHOR_NOT_ENROLLED' not in str(error):raise
            connection.rollback();report['missing_native_root_rejected']='PASS'
        else:raise RuntimeError('session created without physical enrollment')
    counts=admin.execute('SELECT (SELECT count(*) FROM company.sessions),'
        '(SELECT count(*) FROM company.memberships)').fetchone()
    if counts!=(0,0):raise RuntimeError('unexpected session or membership created by guard probe')
    report['sessions_memberships_after_denial']=list(counts)
    return report
