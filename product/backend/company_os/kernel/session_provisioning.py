"""Trusted physical setup session writer; never an HTTP/login route.

Caller owns the transaction and independent identity/custody verification.
Issuing a session neither creates grants nor assigns memberships. Existing
native root/clock checks remain authoritative; no Python wall-clock fallback.
Caller must roll back the entire transaction on any failure and commit only
through the already-approved physical provisioning process.
"""

import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from company_os.bootstrap.provisioning import ProvisioningBlocked, ProvisioningOutcomeUnknown

ROOT_FIELDS = frozenset(
    (
        "utc_lower",
        "utc_upper",
        "boottime_ns",
        "host_boot_id",
        "installation_id",
        "generation",
        "backend_pid",
        "transaction_id",
        "db_login",
    )
)

OWNER_BINDING_SQL = (
    "SELECT b.tenant_id,b.project_id,b.accepted_human_id,"
    "least(b.e0_valid_until,%s::timestamptz+%s*interval '1 second') "
    "FROM company_private.bootstrap_receipts b "
    "JOIN company_private.installation_bootstrap_control d USING(installation_id,generation) "
    "JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=b.accepted_human_id "
    "JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id "
    "JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id "
    "WHERE b.installation_id=%s::uuid AND b.generation=%s::bigint AND d.state='CONSUMED' "
    "AND p.kind='HUMAN' AND m.role='OWNER' AND c.state='SUCCEEDED' "
    "AND c.operation='trusted_setup.consume' AND c.principal_id=b.accepted_human_id "
    "AND c.r55_project_id=b.project_id AND c.r55_source_revision='r56' "
    "AND c.r55_result_digest=b.r56_result_digest AND b.e0_valid_until>%s::timestamptz"
)

PRINCIPAL_BINDING_SQL = (
    "SELECT b.tenant_id,b.project_id,p.id,p.kind,"
    "least(b.e0_valid_until,%s::timestamptz+%s*interval '1 second') "
    "FROM company_private.bootstrap_receipts b "
    "JOIN company_private.installation_bootstrap_control d USING(installation_id,generation) "
    "JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=%s::uuid "
    "JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id AND m.role=%s "
    "JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id "
    "WHERE b.installation_id=%s::uuid AND b.generation=%s::bigint AND d.state='CONSUMED' "
    "AND c.state='SUCCEEDED' AND c.operation='trusted_setup.consume' "
    "AND c.principal_id=b.accepted_human_id AND c.r55_project_id=b.project_id "
    "AND c.r55_source_revision='r56' AND c.r55_result_digest=b.r56_result_digest "
    "AND b.e0_valid_until>%s::timestamptz"
)


def _id(value, *, driver=False):
    if driver and type(value) is UUID:
        return str(value)
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError()
    except ValueError, TypeError, AttributeError:
        raise ProvisioningBlocked("CANONICAL_SESSION_ID_REQUIRED") from None
    return value


def _inputs(installation_id, token, ttl):
    installation_id = _id(installation_id)
    if (
        type(token) is not str
        or not 32 <= len(token.encode("utf-8")) <= 4096
        or type(ttl) is not int
        or not 1 <= ttl <= 900
    ):
        raise ProvisioningBlocked("BOUNDED_SESSION_REQUIRED")
    return installation_id


def _root_bounds(cursor, installation):
    cursor.execute("SELECT pg_backend_pid(),pg_current_xact_id()::text,session_user")
    context = cursor.fetchone()
    if (
        type(context) is not tuple
        or len(context) != 3
        or type(context[0]) is not int
        or context[0] < 1
        or type(context[1]) is not str
        or not context[1].isdigit()
        or type(context[2]) is not str
        or not context[2]
    ):
        raise ProvisioningBlocked("EXACT_SESSION_CONTEXT_REQUIRED")
    cursor.execute("SELECT company_private.r56_root_bounds(%s::uuid)", (installation,))
    row = cursor.fetchone()
    bounds = row[0] if type(row) is tuple and len(row) == 1 else None
    if (
        type(bounds) is not dict
        or set(bounds) != ROOT_FIELDS
        or bounds["installation_id"] != installation
        or type(bounds["generation"]) is not int
        or not 1 <= bounds["generation"] <= 9007199254740991
        or type(bounds["boottime_ns"]) is not int
        or bounds["boottime_ns"] < 0
        or type(bounds["backend_pid"]) is not int
        or (bounds["backend_pid"], bounds["transaction_id"], bounds["db_login"]) != context
    ):
        raise ProvisioningBlocked("CURRENT_ROOT_BOUNDS_REQUIRED")
    bounds = dict(bounds)
    _id(bounds["host_boot_id"])
    try:
        for name in ("utc_lower", "utc_upper"):
            if type(bounds[name]) is not str:
                raise ValueError()
            value = datetime.fromisoformat(bounds[name])
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError()
            bounds[name] = value
        if bounds["utc_lower"] > bounds["utc_upper"]:
            raise ValueError()
    except ValueError, TypeError:
        raise ProvisioningBlocked("TRUSTED_SESSION_TIME_REQUIRED") from None
    return bounds


def _scope_locks(cursor, tenant, project):
    cursor.execute(
        "SELECT l.lock_id,l.rank,l.identity_key FROM company.authority_scope_heads h "
        "JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id "
        "WHERE h.tenant_id=%s::uuid AND ((h.scope_kind='TENANT' AND h.scope_ref=%s::uuid) "
        "OR (h.scope_kind='PROJECT' AND h.scope_ref=%s::uuid)) ORDER BY l.rank,l.lock_id",
        (tenant, tenant, project),
    )
    locks = cursor.fetchall()
    expected = [
        {"kind": "TENANT", "tenant_id": tenant},
        {"kind": "PROJECT", "tenant_id": tenant, "project_id": project},
    ]
    if type(locks) is not list or len(locks) != 2:
        raise ProvisioningBlocked("EXACT_AUTHORITY_HEADS_REQUIRED")
    seen = set()
    for rank, row in enumerate(locks):
        if (
            type(row) is not tuple
            or len(row) != 3
            or type(row[0]) is not int
            or row[0] <= 0
            or type(row[1]) is not int
            or row[1] != rank
            or row[2] != expected[rank]
            or row[0] in seen
        ):
            raise ProvisioningBlocked("EXACT_SESSION_LOCK_IDENTITY_REQUIRED")
        seen.add(row[0])
    for lock, _, _ in locks:
        cursor.execute("SELECT pg_advisory_xact_lock(%s::bigint)", (lock,))


def _binding(row, bounds, role, principal):
    size = 4 if role == "OWNER" else 5
    if type(row) is not tuple or len(row) != size:
        raise ProvisioningBlocked("CURRENT_BOOTSTRAPPED_MEMBERSHIP_REQUIRED")
    tenant, project, pid = (_id(value, driver=True) for value in row[:3])
    if role != "OWNER" and (
        row[3] != {"OPERATOR": "HUMAN", "WORKER": "WORKER", "VERIFIER": "VERIFIER"}[role]
        or pid != principal
    ):
        raise ProvisioningBlocked("SESSION_PRINCIPAL_ROLE_MISMATCH")
    expires = row[-1]
    if (
        type(expires) is not datetime
        or expires.tzinfo is None
        or expires.utcoffset() is None
        or expires <= bounds["utc_upper"]
    ):
        raise ProvisioningBlocked("UNAMBIGUOUS_SESSION_EXPIRY_REQUIRED")
    return tenant, project, pid, expires


def _issue(cursor, installation, token, ttl, role, principal=None):
    original = _root_bounds(cursor, installation)
    sql = OWNER_BINDING_SQL if role == "OWNER" else PRINCIPAL_BINDING_SQL

    def args(bounds):
        prefix: tuple[object, ...] = (bounds["utc_lower"], ttl)
        if role != "OWNER":
            prefix += (principal, role)
        return prefix + (installation, bounds["generation"], bounds["utc_upper"])

    cursor.execute(sql, args(original))
    binding = _binding(cursor.fetchone(), original, role, principal)
    tenant, project, pid, _ = binding
    _scope_locks(cursor, tenant, project)
    current = _root_bounds(cursor, installation)
    if any(
        current[k] != original[k]
        for k in ("generation", "host_boot_id", "backend_pid", "transaction_id", "db_login")
    ):
        raise ProvisioningBlocked("SESSION_ROOT_CHANGED")
    cursor.execute(sql + " FOR SHARE OF b,d,p,m,c", args(current))
    locked = _binding(cursor.fetchone(), current, role, principal)
    if locked[:3] != binding[:3]:
        raise ProvisioningBlocked("SESSION_AUTHORITY_CHANGED")
    expires = locked[-1]
    session = str(uuid4())
    cursor.execute(
        "INSERT INTO company_private.scope_lock_registry(rank,identity_key) "
        "VALUES(2,jsonb_build_object('kind','SESSION','tenant_id',%s::uuid,'session_id',%s::uuid)) RETURNING lock_id",
        (tenant, session),
    )
    lockrow = cursor.fetchone()
    if not lockrow or type(lockrow[0]) is not int or lockrow[0] <= 0:
        raise ProvisioningBlocked("EXACT_SESSION_LOCK_REQUIRED")
    cursor.execute(
        "INSERT INTO company.sessions(tenant_id,id,principal_id,token_hash,expires_at) "
        "VALUES(%s::uuid,%s::uuid,%s::uuid,%s,%s)",
        (tenant, session, pid, hashlib.sha256(token.encode("utf-8")).hexdigest(), expires),
    )
    cursor.execute(
        "INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision) "
        "VALUES(%s::uuid,'SESSION',%s::uuid,%s::uuid,0,%s::bigint,0)",
        (tenant, session, session, lockrow[0]),
    )
    kind = "OwnerSessionIssued" if role == "OWNER" else "PrincipalSessionIssued"
    cursor.execute(
        "INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(%s::uuid,%s::uuid,%s::uuid,%s)",
        (tenant, str(uuid4()), pid, kind),
    )
    result = {
        "session_id": session,
        "installation_id": installation,
        "generation": current["generation"],
        "tenant_id": tenant,
        "principal_id": pid,
        "expires_at": expires,
        "new_grants": 0,
        "new_memberships": 0,
        "commit": "CALLER_MUST_COMMIT",
    }
    if role != "OWNER":
        result.update(principal_id=pid, role=role)
    return result


def issue_owner_session(cursor, *, installation_id, token, ttl_seconds=300):
    installation = _inputs(installation_id, token, ttl_seconds)
    return _issue(cursor, installation, token, ttl_seconds, "OWNER")


def issue_principal_session(cursor, *, installation_id, principal_id, role, token, ttl_seconds=300):
    installation = _inputs(installation_id, token, ttl_seconds)
    principal = _id(principal_id)
    if type(role) is not str or role not in ("OPERATOR", "WORKER", "VERIFIER"):
        raise ProvisioningBlocked("INVALID_SESSION_ROLE")
    return _issue(cursor, installation, token, ttl_seconds, role, principal)


SESSION_READBACK_SQL = """SELECT s.expires_at,s.token_hash,h.epoch,h.revision,l.rank,l.identity_key
FROM company.sessions s
JOIN company_private.bootstrap_receipts b
  ON b.tenant_id=s.tenant_id AND b.accepted_human_id=s.principal_id
JOIN company_private.installation_bootstrap_control ctl
  ON ctl.installation_id=b.installation_id AND ctl.generation=b.generation
JOIN company.principals p ON p.tenant_id=s.tenant_id AND p.id=s.principal_id
JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id
JOIN company.authority_scope_heads h
  ON h.tenant_id=s.tenant_id AND h.scope_ref=s.id AND h.session_id=s.id AND h.scope_kind='SESSION'
JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
WHERE s.id=%s::uuid AND b.installation_id=%s::uuid AND b.generation=%s::bigint
  AND s.tenant_id=%s::uuid AND s.principal_id=%s::uuid
  AND s.revoked_at IS NULL AND ctl.state='CONSUMED' AND p.kind='HUMAN' AND m.role='OWNER'
  AND s.expires_at>%s::timestamptz AND b.e0_valid_until>%s::timestamptz
LIMIT 2"""


def _idle_session_cursor(connection):
    if connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ProvisioningBlocked("IDLE_DEDICATED_SESSION_CONNECTION_REQUIRED")
    return connection.cursor()


def _check_session_login(cursor, expected_login: str, timeout_ms: int) -> None:
    cursor.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
    for setting in ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout"):
        cursor.execute("SELECT set_config(%s,%s,true)", (setting, str(timeout_ms) + "ms"))
    cursor.execute(
        "SELECT session_user,current_user,r.rolsuper,r.rolbypassrls,r.rolcreaterole "
        "FROM pg_catalog.pg_roles r WHERE r.rolname=session_user"
    )
    row = cursor.fetchone()
    if row != (expected_login, expected_login, False, False, False) or any(
        type(value) is not bool for value in row[2:]
    ):
        raise ProvisioningBlocked("EXACT_LEAST_PRIVILEGE_SESSION_LOGIN_REQUIRED")


def issue_committed_owner_session(
    connect,
    *,
    installation_id: str,
    token: str,
    expected_login: str,
    ttl_seconds: int = 300,
    timeout_ms: int = 2000,
) -> dict:
    """Supervisor-only issue/commit/fresh readback; no token is returned or logged.

    Existing native root/time/membership checks remain mandatory. Caller supplies
    an already-authorized provisioner, not an HTTP transport or identity verifier.
    Lost ACK or failed post-commit readback must be reconciled; never retry issue.
    """
    installation = _inputs(installation_id, token, ttl_seconds)
    if (
        not callable(connect)
        or type(expected_login) is not str
        or not 1 <= len(expected_login) <= 63
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= 5000
    ):
        raise ProvisioningBlocked("EXACT_SESSION_SUPERVISOR_BINDINGS_REQUIRED")
    connection = None
    committing = False
    committed = False
    writer = None
    try:
        connection = connect()
        writer = connection
        with _idle_session_cursor(connection) as cursor:
            _check_session_login(cursor, expected_login, timeout_ms)
            result = issue_owner_session(
                cursor, installation_id=installation, token=token, ttl_seconds=ttl_seconds
            )
        committing = True
        connection.commit()
        committed = True
        committing = False
        connection.close()
        connection = None
        connection = connect()
        if connection is writer:
            raise ProvisioningBlocked("INDEPENDENT_SESSION_READBACK_CONNECTION_REQUIRED")
        with _idle_session_cursor(connection) as cursor:
            _check_session_login(cursor, expected_login, timeout_ms)
            bounds = _root_bounds(cursor, installation)
            if bounds["generation"] != result["generation"]:
                raise ProvisioningBlocked("SESSION_GENERATION_CHANGED_AFTER_COMMIT")
            cursor.execute(
                SESSION_READBACK_SQL,
                (
                    result["session_id"],
                    installation,
                    bounds["generation"],
                    result["tenant_id"],
                    result["principal_id"],
                    bounds["utc_upper"],
                    bounds["utc_upper"],
                ),
            )
            rows = cursor.fetchall()
            if type(rows) is not list or len(rows) != 1:
                raise ProvisioningBlocked("SESSION_READBACK_NOT_UNIQUE_OR_EXPIRED")
            expires, token_hash, epoch, revision, rank, identity = rows[0]
            expected_identity = {
                "kind": "SESSION",
                "tenant_id": result["tenant_id"],
                "session_id": result["session_id"],
            }
            if (
                expires != result["expires_at"]
                or token_hash != hashlib.sha256(token.encode("utf-8")).hexdigest()
                or type(epoch) is not int
                or epoch != 0
                or type(revision) is not int
                or revision != 0
                or type(rank) is not int
                or rank != 2
                or identity != expected_identity
            ):
                raise ProvisioningBlocked("SESSION_READBACK_BINDING_MISMATCH")
        connection.rollback()
        connection.close()
        connection = None
        return dict(
            result,
            commit="ACKNOWLEDGED",
            independent_readback="MATCH",
            authorization="SESSION_ONLY_NOT_WORKFLOW_ACCEPTANCE",
        )
    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        if committing or committed:
            raise ProvisioningOutcomeUnknown(
                "SESSION_COMMIT_OR_READBACK_REQUIRES_RECONCILIATION"
            ) from None
        if isinstance(error, ProvisioningBlocked):
            raise
        # Only stable native error identifiers may cross the secret boundary.
        code = getattr(getattr(error, "diag", None), "message_primary", None)
        if code in {"ROOT_BOOTTIME_EXPIRED_OR_REBOOTED", "ROOT_TRUST_ANCHOR_NOT_ENROLLED"}:
            raise ProvisioningBlocked(code) from None
        raise ProvisioningBlocked("SESSION_ISSUANCE_NOT_COMMITTED") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                raise ProvisioningOutcomeUnknown("SESSION_CONNECTION_CLOSE_UNCONFIRMED") from None
