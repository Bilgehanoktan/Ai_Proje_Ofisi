"""Synthetic root adapter probe in a NEW disposable native catalog only.

The fixture admin bypasses RLS. This is driver/schema evidence, never proof of
physical enrollment approval, custody, provisioning ACL or current authority.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from company_os.bootstrap.provisioning import FIELDS, enroll_root, read_root, ProvisioningBlocked


def probe_root_reader(admin, connect):
    from psycopg.types.json import Jsonb
    now = datetime.now(timezone.utc)
    record = dict.fromkeys(FIELDS, 'a' * 64)
    for name in ('installation_id', 'issuer_id', 'key_id', 'actual_human_id',
                 'custodian_id', 'host_boot_id'):
        record[name] = str(uuid4())
    record.update(custodian_id=record['actual_human_id'], generation=1,
        enrollment_revision=1, allowed_operations=['e0.setup_mandate_consume'],
        not_before=now, not_after=now + timedelta(minutes=1),
        r56_anchor_utc_lower=now, r56_anchor_utc_upper=now,
        not_after_boottime_ns=20, r56_anchor_boottime_ns=10,
        r56_issuer_class='PROVISIONING_SERVICE')
    lock = admin.execute('INSERT INTO company_private.scope_lock_registry(rank,identity_key) '
        'VALUES(0,%s) RETURNING lock_id', (Jsonb(dict(kind='INSTALLATION_BOOTSTRAP',
        installation_id=record['installation_id'])),)).fetchone()[0]
    record['lock_id'] = lock
    login = 'aipof-dbtest'
    connections = []
    def dedicated():
        connection = connect(login)
        connections.append(connection)
        return connection
    class SyntheticVerifier:
        # Explicit test double; does not verify a real human or approval.
        def verify_root(self, value): return value
    report = dict(scope='SYNTHETIC_ADMIN_DRIVER_SCHEMA_NOT_PROVISIONING_AUTHORIZATION')
    try:
        written = enroll_root(dedicated, SyntheticVerifier(), record, expected_login=login)
        if written['bootstrap'] != 'NOT_ARMED': raise RuntimeError('false bootstrap claim')
        report['insert_commit'] = 'PASS'
        result = read_root(dedicated, record, expected_login=login)
        if result != dict(readback='MATCH', bootstrap='NOT_ARMED'):
            raise RuntimeError('unexpected root readback')
        report['independent_native_driver_readback'] = 'PASS'
        for column in ('revoked_at', 'compromised_at'):
            admin.execute('UPDATE company_private.r55_setup_root_enrollments SET '+column+'=clock_timestamp() '
                          'WHERE installation_id=%s AND generation=1', (record['installation_id'],))
            try:
                try: read_root(dedicated, record, expected_login=login)
                except ProvisioningBlocked: report[column] = 'REJECTED'
                else: raise RuntimeError('revoked/compromised root accepted')
            finally:
                admin.execute('UPDATE company_private.r55_setup_root_enrollments SET '+column+'=NULL '
                              'WHERE installation_id=%s AND generation=1', (record['installation_id'],))
        wrong = dict(record, enrollment_digest='b'*64)
        try: read_root(dedicated, wrong, expected_login=login)
        except ProvisioningBlocked: report['wrong_digest'] = 'REJECTED'
        else: raise RuntimeError('wrong root digest accepted')
        report['connections_closed'] = all(connection.closed for connection in connections)
        if not report['connections_closed']: raise RuntimeError('root connection leaked')
        return report
    finally:
        # Native lock registry is append-only. Preserve its rules and let the
        # outer disposable-cluster lifecycle remove the entire test database.
        for connection in connections:
            if not connection.closed: connection.close()
