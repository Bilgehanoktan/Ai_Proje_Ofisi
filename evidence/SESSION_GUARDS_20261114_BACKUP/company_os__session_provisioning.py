"""Trusted Kernel kurulum transaction'ı için ilk insan oturumu yazıcısı.

Normal HTTP/model rotası değildir. Caller transaction/commit ve bağımsız
kimlik doğrulamasını yönetir. Oturum oluşturmak yeni grant üretmez.
"""
import hashlib
from uuid import uuid4
from .provisioning import ProvisioningBlocked


def issue_owner_session(cursor, *, installation_id, token, ttl_seconds=300):
    if (type(token) is not str or not 32 <= len(token.encode('utf-8')) <= 4096
            or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900):
        raise ProvisioningBlocked('BOUNDED_SESSION_REQUIRED')
    # Existing r56 root verifier rejects expiry, compromised roots, wrong boot
    # and untrusted clock. No independent clock implementation is introduced.
    cursor.execute('SELECT company_private.r56_root_bounds(%s::uuid)', (installation_id,))
    row = cursor.fetchone()
    if not row or type(row[0]) is not dict:
        raise ProvisioningBlocked('CURRENT_ROOT_BOUNDS_REQUIRED')
    binding_sql = (
        "SELECT b.tenant_id,b.project_id,b.accepted_human_id,"
        "least(b.e0_valid_until,clock_timestamp()+%s*interval '1 second') "
        "FROM company_private.bootstrap_receipts b "
        "JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=b.accepted_human_id "
        "JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id "
        "JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id "
        "WHERE b.installation_id=%s::uuid AND p.kind='HUMAN' AND c.state='SUCCEEDED' "
        "AND c.r55_result_digest=b.r56_result_digest AND b.e0_valid_until>clock_timestamp() "
        "")
    cursor.execute(binding_sql, (ttl_seconds, installation_id))
    binding = cursor.fetchone()
    if not binding:
        raise ProvisioningBlocked('CURRENT_BOOTSTRAPPED_HUMAN_REQUIRED')
    tenant, project, human, expires = binding
    cursor.execute(
        "SELECT l.lock_id FROM company.authority_scope_heads h "
        "JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id "
        "WHERE h.tenant_id=%s::uuid AND ((h.scope_kind='TENANT' AND h.scope_ref=%s::uuid) "
        "OR (h.scope_kind='PROJECT' AND h.scope_ref=%s::uuid)) ORDER BY l.rank,l.lock_id",
        (tenant, tenant, project))
    locks = cursor.fetchall()
    if len(locks) != 2:
        raise ProvisioningBlocked('EXACT_AUTHORITY_HEADS_REQUIRED')
    for lock, in locks:
        cursor.execute('SELECT pg_advisory_xact_lock(%s::bigint)', (lock,))
    cursor.execute(binding_sql + ' FOR SHARE OF b,p,m,c', (ttl_seconds, installation_id))
    current = cursor.fetchone()
    if not current or current[:3] != binding[:3]:
        raise ProvisioningBlocked('SESSION_AUTHORITY_CHANGED')
    expires = current[3]
    session = str(uuid4())
    cursor.execute(
        "INSERT INTO company_private.scope_lock_registry(rank,identity_key) "
        "VALUES(2,jsonb_build_object('kind','SESSION','tenant_id',%s::uuid,'session_id',%s::uuid)) RETURNING lock_id",
        (tenant, session))
    lock = cursor.fetchone()[0]
    cursor.execute(
        'INSERT INTO company.sessions(tenant_id,id,principal_id,token_hash,expires_at) '
        'VALUES(%s::uuid,%s::uuid,%s::uuid,%s,%s)',
        (tenant, session, human, hashlib.sha256(token.encode('utf-8')).hexdigest(), expires))
    cursor.execute(
        "INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision) "
        "VALUES(%s::uuid,'SESSION',%s::uuid,%s::uuid,0,%s::bigint,0)",
        (tenant, session, session, lock))
    cursor.execute(
        "INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) "
        "VALUES(%s::uuid,%s::uuid,%s::uuid,'OwnerSessionIssued')",
        (tenant, str(uuid4()), human))
    return {'session_id': session, 'expires_at': expires, 'new_grants': 0,
            'commit': 'CALLER_MUST_COMMIT'}


def issue_principal_session(cursor, *, installation_id, principal_id, role, token, ttl_seconds=300):
    if (type(token) is not str or not 32 <= len(token.encode('utf-8')) <= 4096
            or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900):
        raise ProvisioningBlocked('BOUNDED_SESSION_REQUIRED')
    if role not in ('OPERATOR', 'WORKER', 'VERIFIER'):
        raise ProvisioningBlocked('INVALID_SESSION_ROLE')
    cursor.execute('SELECT company_private.r56_root_bounds(%s::uuid)', (installation_id,))
    row = cursor.fetchone()
    if not row or type(row[0]) is not dict:
        raise ProvisioningBlocked('CURRENT_ROOT_BOUNDS_REQUIRED')
    binding_sql = (
        "SELECT b.tenant_id,b.project_id,p.id,p.kind,"
        "least(b.e0_valid_until,clock_timestamp()+%s*interval '1 second') "
        "FROM company_private.bootstrap_receipts b "
        "JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=%s::uuid "
        "JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id "
        "WHERE b.installation_id=%s::uuid AND c.state='SUCCEEDED' "
        "AND c.r55_result_digest=b.r56_result_digest AND b.e0_valid_until>clock_timestamp() "
        "")
    cursor.execute(binding_sql, (ttl_seconds, principal_id, installation_id))
    binding = cursor.fetchone()
    if not binding:
        raise ProvisioningBlocked('CURRENT_BOOTSTRAPPED_PRINCIPAL_REQUIRED')
    tenant, project, pid, pkind, expires = binding
    if ((role == 'OPERATOR' and pkind != 'HUMAN')
            or (role == 'WORKER' and pkind != 'WORKER')
            or (role == 'VERIFIER' and pkind != 'VERIFIER')):
        raise ProvisioningBlocked('SESSION_PRINCIPAL_ROLE_MISMATCH')
    cursor.execute(
        "SELECT l.lock_id FROM company.authority_scope_heads h "
        "JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id "
        "WHERE h.tenant_id=%s::uuid AND ((h.scope_kind='TENANT' AND h.scope_ref=%s::uuid) "
        "OR (h.scope_kind='PROJECT' AND h.scope_ref=%s::uuid)) ORDER BY l.rank,l.lock_id",
        (tenant, tenant, project))
    locks = cursor.fetchall()
    if len(locks) != 2:
        raise ProvisioningBlocked('EXACT_AUTHORITY_HEADS_REQUIRED')
    for lock, in locks:
        cursor.execute('SELECT pg_advisory_xact_lock(%s::bigint)', (lock,))
    cursor.execute(binding_sql + ' FOR SHARE OF b,p,c', (ttl_seconds, principal_id, installation_id))
    current = cursor.fetchone()
    if not current or current[:4] != binding[:4]:
        raise ProvisioningBlocked('SESSION_AUTHORITY_CHANGED')
    expires = current[4]
    cursor.execute(
        'INSERT INTO company.memberships(tenant_id,principal_id,role) '
        'VALUES(%s::uuid,%s::uuid,%s) ON CONFLICT(tenant_id,principal_id) DO NOTHING',
        (tenant, pid, role))
    session = str(uuid4())
    cursor.execute(
        "INSERT INTO company_private.scope_lock_registry(rank,identity_key) "
        "VALUES(2,jsonb_build_object('kind','SESSION','tenant_id',%s::uuid,'session_id',%s::uuid)) RETURNING lock_id",
        (tenant, session))
    lock = cursor.fetchone()[0]
    cursor.execute(
        'INSERT INTO company.sessions(tenant_id,id,principal_id,token_hash,expires_at) '
        'VALUES(%s::uuid,%s::uuid,%s::uuid,%s,%s)',
        (tenant, session, pid, hashlib.sha256(token.encode('utf-8')).hexdigest(), expires))
    cursor.execute(
        "INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision) "
        "VALUES(%s::uuid,'SESSION',%s::uuid,%s::uuid,0,%s::bigint,0)",
        (tenant, session, session, lock))
    cursor.execute(
        "INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) "
        "VALUES(%s::uuid,%s::uuid,%s::uuid,'PrincipalSessionIssued')",
        (tenant, str(uuid4()), pid))
    return {'session_id': session, 'principal_id': str(pid), 'role': role,
            'expires_at': expires, 'new_grants': 0, 'commit': 'CALLER_MUST_COMMIT'}
