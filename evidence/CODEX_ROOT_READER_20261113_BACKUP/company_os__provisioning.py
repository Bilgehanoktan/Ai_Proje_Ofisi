"""Fiziksel root provisioning ve kayıtlı revoke işlemi adapterleri.

Bu modül insan kimliğini doğrulamaz, kanıt veya onay üretmez. Root yazıcısı
bağımsız doğrulanmış kaydı, revoke ise mevcut Kernel yetkisini zorunlu tutar.
Genel grant issuer bağlı değildir; başarılıymış gibi sonuç döndürülemez.
"""
from datetime import datetime
from uuid import UUID
import re

FIELDS = (
    'installation_id', 'generation', 'enrollment_revision', 'issuer_id', 'key_id',
    'key_fingerprint', 'actual_human_id', 'custodian_id',
    'verified_identity_evidence_digest', 'release_digest', 'enrollment_digest',
    'allowed_operations', 'host_boot_id', 'clock_policy_digest', 'not_before',
    'not_after', 'not_after_boottime_ns', 'lock_id', 'r56_anchor_boottime_ns',
    'r56_anchor_utc_lower', 'r56_anchor_utc_upper', 'r56_issuer_class',
    'r56_approved_manifest_digest', 'r56_approved_nonce_hash',
    'r56_human_consent_evidence_digest',
)
ALLOWED = frozenset({'projects.read', 'projects.create',
                     'e0.setup_mandate_consume', 'e0.evaluation_attempt_create'})


class ProvisioningBlocked(ValueError):
    pass


def root_insert(record):
    """Exact insert SQL + parametreler; provenance doğrulaması ayrıca zorunlu."""
    if type(record) is not dict or set(record) != set(FIELDS):
        raise ProvisioningBlocked('EXACT_ROOT_RECORD_REQUIRED')
    for name in ('installation_id', 'issuer_id', 'key_id', 'actual_human_id',
                 'custodian_id', 'host_boot_id'):
        value = record[name]
        try:
            valid = type(value) is str and str(UUID(value)) == value
        except ValueError:
            valid = False
        if not valid:
            raise ProvisioningBlocked('CANONICAL_UUID_REQUIRED')
    if record['actual_human_id'] == record['issuer_id']:
        raise ProvisioningBlocked('HUMAN_ISSUER_SEPARATION_REQUIRED')
    if record['actual_human_id'] != record['custodian_id']:
        raise ProvisioningBlocked('SINGLE_HUMAN_CUSTODIAN_REQUIRED')
    for name in FIELDS:
        if name.endswith(('_digest', '_hash', '_fingerprint')):
            if type(record[name]) is not str or not re.fullmatch('[a-f0-9]{64}', record[name]):
                raise ProvisioningBlocked('EXACT_EVIDENCE_DIGEST_REQUIRED')
    for name in ('generation', 'enrollment_revision', 'not_after_boottime_ns', 'lock_id'):
        if type(record[name]) is not int or record[name] <= 0:
            raise ProvisioningBlocked('POSITIVE_INTEGER_REQUIRED')
    anchor = record['r56_anchor_boottime_ns']
    if type(anchor) is not int or not 0 <= anchor < record['not_after_boottime_ns']:
        raise ProvisioningBlocked('BOOTTIME_WINDOW_REQUIRED')
    operations = record['allowed_operations']
    if (type(operations) is not list or not operations
            or any(type(op) is not str or op not in ALLOWED for op in operations)
            or len(set(operations)) != len(operations)):
        raise ProvisioningBlocked('FINITE_BOOTSTRAP_SCOPE_REQUIRED')
    dates = [record[n] for n in ('not_before', 'r56_anchor_utc_lower',
                                'r56_anchor_utc_upper', 'not_after')]
    if any(type(d) is not datetime or d.tzinfo is None or d.utcoffset() is None for d in dates):
        raise ProvisioningBlocked('AWARE_TIME_REQUIRED')
    if not dates[0] <= dates[1] <= dates[2] < dates[3]:
        raise ProvisioningBlocked('UTC_WINDOW_REQUIRED')
    if record['r56_issuer_class'] != 'PROVISIONING_SERVICE':
        raise ProvisioningBlocked('PROVISIONING_SERVICE_REQUIRED')
    sql = ('INSERT INTO company_private.r55_setup_root_enrollments ('
           + ','.join(FIELDS) + ') VALUES (' + ','.join(['%s'] * len(FIELDS)) + ')')
    return sql, tuple(list(record[n]) if n == 'allowed_operations' else record[n]
                      for n in FIELDS)


class ProvisioningOutcomeUnknown(RuntimeError):
    pass


def enroll_root(connect, verifier, record, *, expected_login, timeout_ms=2000):
    """Trusted physical provisioning adapter only; not an application route.

    verifier.verify_root must independently validate identity/consent/custody
    and source bindings, returning the exact approved record. A shape check
    or caller-provided verified flag is insufficient. No default verifier.
    """
    import copy
    if type(expected_login) is not str or not expected_login:
        raise ProvisioningBlocked('EXACT_PROVISIONER_LOGIN_REQUIRED')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
        raise ProvisioningBlocked('BOUNDED_TIMEOUT_REQUIRED')
    approved = copy.deepcopy(record)
    try:
        checked = verifier.verify_root(copy.deepcopy(approved))
    except Exception:
        raise ProvisioningBlocked('INDEPENDENT_PROVISIONING_VERIFICATION_FAILED') from None
    if checked != approved:
        raise ProvisioningBlocked('EXACT_APPROVED_ROOT_REQUIRED')
    sql, args = root_insert(approved)
    connection = connect()
    committing = False
    try:
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise ProvisioningBlocked('IDLE_DEDICATED_TRANSACTION_REQUIRED')
        with connection.cursor() as cursor:
            cursor.execute('BEGIN ISOLATION LEVEL SERIALIZABLE')
            for name in ('statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout'):
                cursor.execute('SELECT set_config(%s,%s,true)', (name, str(timeout_ms) + 'ms'))
            cursor.execute('SELECT session_user')
            if cursor.fetchone() != (expected_login,):
                raise ProvisioningBlocked('PROVISIONER_LOGIN_MISMATCH')
            cursor.execute(
                'SELECT rank, identity_key FROM company_private.scope_lock_registry '
                'WHERE lock_id=%s FOR SHARE', (approved['lock_id'],))
            if cursor.fetchone() != (0, {'kind': 'INSTALLATION_BOOTSTRAP',
                                         'installation_id': approved['installation_id']}):
                raise ProvisioningBlocked('ROOT_LOCK_IDENTITY_MISMATCH')
            cursor.execute(sql, args)
        committing = True
        connection.commit()
        committing = False
        return {'installation_id': approved['installation_id'],
                'generation': approved['generation'], 'commit': 'ACKNOWLEDGED',
                'independent_readback': 'NOT_RUN', 'bootstrap': 'NOT_ARMED'}
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        if committing:
            raise ProvisioningOutcomeUnknown('RECONCILE_ROOT_NO_AUTOMATIC_RETRY') from None
        raise ProvisioningBlocked('ROOT_ENROLLMENT_NOT_COMMITTED') from None
    finally:
        connection.close()


def read_root(connect, expected_record, *, expected_login, timeout_ms=2000):
    """Ayrı dedicated bağlantıda exact enrollment readback; bootstrap kabulü değil."""
    root_insert(expected_record)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
        raise ProvisioningBlocked('BOUNDED_TIMEOUT_REQUIRED')
    connection = connect()
    try:
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise ProvisioningBlocked('IDLE_DEDICATED_TRANSACTION_REQUIRED')
        with connection.cursor() as cursor:
            cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for name in ('statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout'):
                cursor.execute('SELECT set_config(%s,%s,true)', (name, str(timeout_ms) + 'ms'))
            cursor.execute('SELECT session_user')
            if cursor.fetchone() != (expected_login,):
                raise ProvisioningBlocked('PROVISIONER_LOGIN_MISMATCH')
            cursor.execute('SELECT ' + ','.join(FIELDS) +
                           ',revoked_at,compromised_at FROM company_private.r55_setup_root_enrollments '
                           'WHERE installation_id=%s AND generation=%s',
                           (expected_record['installation_id'], expected_record['generation']))
            row = cursor.fetchone()
            expected = tuple(expected_record[n] for n in FIELDS) + (None, None)
            if row is None or tuple(row) != expected:
                raise ProvisioningBlocked('ROOT_READBACK_MISMATCH_OR_REVOKED')
        return {'readback': 'MATCH', 'bootstrap': 'NOT_ARMED'}
    except ProvisioningBlocked:
        raise
    except Exception:
        raise ProvisioningBlocked('ROOT_READBACK_FAILED') from None
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()

class ProvisioningContext:
    def __init__(self, *, installation_id, tenant_id, project_id, issued_by_human_id, bootstrap_receipt_id, authority_evidence_ref):
        self.installation_id = installation_id
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.issued_by_human_id = issued_by_human_id
        self.bootstrap_receipt_id = bootstrap_receipt_id
        self.authority_evidence_ref = authority_evidence_ref

def provision_project_grant(conn, pctx, *, grant_id, principal_id, permissions, task_id=None, attempt_id=None, fencing_epoch=None, valid_from_iso=None, valid_until_iso=None):
    """Unsupported general issuer: do not mint authority or consume caller conn.

    Only the existing approved bootstrap writers create the bounded initial
    grants. A matching approved general provisioning writer is not wired here.
    """
    raise ProvisioningBlocked('ENROLLED_NATIVE_GRANT_WRITER_REQUIRED')

def revoke_project_grant(conn, auth, *, target_grant_id, reason, tenant_id=None,
                         grant_revision=None, revocation_scope_digest=None,
                         idempotency_key=None, correlation_id=None):
    """Exact r64 revoke through CommandHost; never synthesize a revoke receipt.

    Inputs are checked before handing connection ownership to CommandHost.
    The scope digest must be independently supplied in PG-jsonb representation;
    calculating a Python JSON hash is not a substitute. Lost commit acknowledgements
    and mismatched post-commit results require readback, never automatic retry.
    """
    import copy
    import json
    from . import command_host
    def identity(value):
        try:
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ProvisioningBlocked('CANONICAL_REVOKE_ID_REQUIRED') from None
        return value
    if type(auth) is not dict:
        raise ProvisioningBlocked('EXACT_REVOKE_AUTH_REQUIRED')
    project = identity(auth.get('project_id'))
    if auth.get('kind') != 'PROJECT' or auth.get('resource_id') != project:
        raise ProvisioningBlocked('PROJECT_REVOKE_SCOPE_REQUIRED')
    target = identity(target_grant_id)
    tenant = identity(tenant_id)
    correlation = identity(correlation_id)
    if (type(grant_revision) is not int or not 0 <= grant_revision <= 9007199254740991
            or reason not in ('OWNER_REQUEST', 'POLICY_CHANGED', 'INCIDENT')
            or type(revocation_scope_digest) is not str
            or not re.fullmatch('[a-f0-9]{64}', revocation_scope_digest)
            or type(idempotency_key) is not str
            or not re.fullmatch('[A-Za-z0-9_.:-]{16,128}', idempotency_key)):
        raise ProvisioningBlocked('EXACT_REVOKE_BINDING_REQUIRED')
    request = dict(schema_version='PK04-r1', operation='CAP-017.revoke',
        correlation_id=correlation, tenant_id=tenant, project_id=project,
        resource_id=target, expected_revision=grant_revision, idempotency_key=idempotency_key,
        payload=dict(grant_id=target, grant_revision=grant_revision, reason_code=reason,
                     revocation_scope_digest=revocation_scope_digest))
    envelope = command_host.execute(conn, copy.deepcopy(auth), 'CAP-017.revoke',
                                     [json.dumps(request, allow_nan=False)])
    result = envelope.get('result')
    receipt = envelope.get('command_receipt')
    if (type(result) is not dict or type(receipt) is not dict
            or receipt.get('state') != 'SUCCEEDED' or receipt.get('result_ref') != target
            or type(receipt.get('command_id')) is not str
            or re.fullmatch('[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}', receipt['command_id']) is None
            or result.get('operation') != 'CAP-017.revoke' or result.get('status') != 'RECORDED'
            or result.get('resource_id') != target or type(result.get('revision')) is not int
            or result['revision'] != grant_revision + 1
            or result.get('scope_digest') != revocation_scope_digest
            or type(result.get('descendant_ids')) is not list or target not in result['descendant_ids']
            or result.get('command_receipt_ref') != receipt.get('command_id')
            or type(result.get('result')) is not dict
            or result['result'].get('revocation_receipt_ref') != receipt.get('command_id')):
        raise ProvisioningOutcomeUnknown('REVOKE_COMMITTED_RESULT_REQUIRES_READBACK_NO_RETRY')
    return copy.deepcopy(envelope)
