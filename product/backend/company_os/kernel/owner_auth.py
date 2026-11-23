"""Post-bootstrap owner authentication and session recovery supervisor adapter.

Never acts as an HTTP login endpoint or identity verifier, never touches root
expiry windows, and never mints project grants or memberships. Caller provides
an already-authorized least-privilege provisioning transport connection and
independent custodian signing material.
"""

import copy
import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from company_os.bootstrap.bootstrap_protocol import frame, raw_json
from company_os.bootstrap.provisioning import ProvisioningBlocked, ProvisioningOutcomeUnknown

PROFILE = "application.owner-auth.v1"
FRAME_PREFIX = b"APP-OWNER-AUTH-v1"
ACTIONS = frozenset(("ISSUE_SESSION", "REVOKE_SESSION", "RECOVER_ROTATE_SESSIONS"))
OUTCOMES = frozenset(("ISSUED", "REVOKED", "RECOVERED_ROTATED", "REPLAY_ALREADY_RECORDED"))

EXECUTE_QUERY = (
    "SELECT company_private.owner_auth_execute_v1("
    "%s::uuid,%s::uuid,%s::uuid,%s::bigint,%s::bytea,%s::bytea)"
)
READBACK_QUERY = (
    "SELECT company_private.owner_auth_receipt_readback_v1("
    "%s::uuid,%s::uuid,%s::uuid,%s::uuid,%s::uuid,%s::text,%s::uuid,%s::text,%s::text)"
)

READBACK_INPUT_FIELDS = (
    "tenant_id",
    "auth_request_id",
    "installation_id",
    "project_id",
    "human_id",
    "action",
    "session_id",
    "token_hash",
    "receipt_digest",
)

SAFE_NATIVE_ERRORS = frozenset(
    {
        "OWNER_AUTH_TRANSPORT_REQUIRED",
        "INVALID_OWNER_AUTH_WIRE",
        "AMBIGUOUS_OWNER_AUTH_JSON",
        "OWNER_AUTH_CONTEXT_MISMATCH",
        "OWNER_AUTH_STATEMENT_SHAPE",
        "OWNER_AUTH_PARAMS_INVALID",
        "OWNER_AUTH_INSTALLATION_NOT_CONSUMED",
        "OWNER_AUTH_INSTALLATION_MISMATCH",
        "OWNER_AUTH_HUMAN_OWNER_REQUIRED",
        "EXACT_OWNER_AUTH_LOCK_IDENTITY_REQUIRED",
        "OWNER_SESSION_NOT_FOUND",
        "OWNER_SESSION_ALREADY_REVOKED",
        "OWNER_SESSION_HEAD_MISSING",
        "OWNER_AUTH_KEY_OR_ENROLLMENT_INVALID",
        "INVALID_OWNER_AUTH_HMAC",
        "OWNER_AUTH_ENROLLMENT_EXPIRED_OR_AMBIGUOUS",
        "OWNER_AUTH_REQUEST_CONFLICT",
        "UNAMBIGUOUS_SESSION_EXPIRY_REQUIRED",
        "BLOCKED_TIME_DEPENDENCY",
        "CLOCK_EPOCH_SAMPLE_NOT_CURRENT",
        "CLOCK_HOST_GENERATION_STALE",
        "CLOCK_POLICY_NOT_APPROVED",
        "BLOCKED_LOCAL_CLOCK_SOURCE",
        "CLOCK_SAMPLE_STALE",
        "CLOCK_DRIFT_EXCEEDED",
        "CLOCK_UNCERTAINTY_EXCEEDED",
        "CLOCK_JUMP",
        "CLOCK_SAMPLE_ENROLLMENT_REVOKED_OR_AMBIGUOUS",
        "OWNER_AUTH_READBACK_WITNESS_MISMATCH",
        "EXACT_OWNER_AUTH_READBACK_INPUT_REQUIRED",
    }
)


def _uuid(value: object) -> str:
    try:
        if type(value) is not str:
            raise ValueError()
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError()
    except ValueError, TypeError, AttributeError:
        raise ProvisioningBlocked("CANONICAL_OWNER_AUTH_ID_REQUIRED") from None
    return value


def _hex64(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_DIGEST_REQUIRED")
    return value


def _aware_datetime(value: object) -> datetime:
    if type(value) is not str:
        raise ProvisioningBlocked("OWNER_AUTH_TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError, TypeError:
        raise ProvisioningBlocked("OWNER_AUTH_TIMESTAMP_REQUIRED") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProvisioningBlocked("OWNER_AUTH_TIMESTAMP_REQUIRED")
    return parsed


def _check_supervisor_args(connect: object, expected_login: object, timeout_ms: object) -> None:
    if (
        not callable(connect)
        or type(expected_login) is not str
        or not 1 <= len(expected_login) <= 63
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= 5000
    ):
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_SUPERVISOR_BINDINGS_REQUIRED")


def _idle_cursor(connection: Any) -> Any:
    if connection.autocommit or int(connection.info.transaction_status) != 0:
        raise ProvisioningBlocked("IDLE_DEDICATED_OWNER_AUTH_CONNECTION_REQUIRED")
    return connection.cursor()


def _begin_and_check_login(
    cursor: Any, expected_login: str, timeout_ms: int, *, readonly: bool
) -> None:
    isolation = (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
        if readonly
        else "BEGIN ISOLATION LEVEL SERIALIZABLE"
    )
    cursor.execute(isolation)
    for setting in ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout"):
        cursor.execute("SELECT set_config(%s,%s,true)", (setting, f"{timeout_ms}ms"))
    cursor.execute(
        "SELECT session_user,current_user,r.rolsuper,r.rolbypassrls,r.rolcreaterole "
        "FROM pg_catalog.pg_roles r WHERE r.rolname=session_user"
    )
    row = cursor.fetchone()
    if row != (expected_login, expected_login, False, False, False) or any(
        type(value) is not bool for value in row[2:]
    ):
        raise ProvisioningBlocked("EXACT_LEAST_PRIVILEGE_OWNER_AUTH_LOGIN_REQUIRED")


def _db_context(cursor: Any, expected_login: str) -> dict[str, object]:
    cursor.execute("SELECT pg_backend_pid(),pg_current_xact_id()::text,session_user")
    row = cursor.fetchone()
    if (
        type(row) is not tuple
        or len(row) != 3
        or type(row[0]) is not int
        or row[0] < 1
        or type(row[1]) is not str
        or not row[1].isdigit()
        or row[2] != expected_login
    ):
        raise ProvisioningBlocked("OWNER_AUTH_CONTEXT_REQUIRED")
    return {"backend_pid": row[0], "transaction_id": row[1], "db_login": row[2]}


def owner_auth_tag(
    key: bytes,
    *,
    auth_request_id: str,
    tenant_id: str,
    project_id: str,
    human_id: str,
    key_id: str,
    enrollment_revision: int,
    raw: bytes,
) -> bytes:
    """Compute exact length-prefixed HMAC-SHA256 tag for owner_auth_execute_v1."""
    if type(key) is not bytes or len(key) != 32:
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_SIGNING_KEY_REQUIRED")
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_BYTES_REQUIRED")
    if type(enrollment_revision) is not int or enrollment_revision < 0:
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_REVISION_REQUIRED")
    parts = [
        _uuid(auth_request_id).encode("utf-8"),
        _uuid(tenant_id).encode("utf-8"),
        _uuid(project_id).encode("utf-8"),
        _uuid(human_id).encode("utf-8"),
        _uuid(key_id).encode("utf-8"),
        str(enrollment_revision).encode("utf-8"),
        raw,
    ]
    return hmac.digest(key, frame(FRAME_PREFIX, parts), "sha256")


def _validate_readback_pins(expected: object) -> dict[str, str]:
    if type(expected) is not dict or set(expected) != set(READBACK_INPUT_FIELDS):
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_READBACK_INPUT_REQUIRED")
    pins: dict[str, str] = {}
    for name in READBACK_INPUT_FIELDS:
        val = expected[name]
        if name == "action":
            if type(val) is not str or val not in ACTIONS:
                raise ProvisioningBlocked("INVALID_OWNER_AUTH_ACTION")
            pins[name] = val
        elif name in ("token_hash", "receipt_digest"):
            pins[name] = _hex64(val)
        else:
            pins[name] = _uuid(val)
    return pins


def _query_readback_with_cursor(cursor: Any, pins: dict[str, str]) -> dict[str, Any]:
    cursor.execute(READBACK_QUERY, tuple(pins[name] for name in READBACK_INPUT_FIELDS))
    row = cursor.fetchone()
    data = (
        row[0]
        if isinstance(row, (tuple, list)) and type(row) in (tuple, list) and len(row) == 1
        else None
    )
    if type(data) is not dict:
        raise ProvisioningBlocked("OWNER_AUTH_READBACK_WITNESS_MISMATCH")
    for name in READBACK_INPUT_FIELDS:
        if data.get(name) != pins[name]:
            raise ProvisioningBlocked("OWNER_AUTH_READBACK_WITNESS_MISMATCH")
    if (
        data.get("readback") != "EXACT_COMMITTED_WITNESS_MATCH"
        or data.get("authorization") != "SESSION_RECORD_READBACK_NOT_WORKFLOW_ACCEPTANCE"
        or type(data.get("new_grants")) is not int
        or data["new_grants"] != 0
        or type(data.get("new_memberships")) is not int
        or data["new_memberships"] != 0
        or type(data.get("revoked_session_count")) is not int
        or data["revoked_session_count"] < 0
        or type(data.get("audit_id")) is not int
        or data["audit_id"] <= 0
    ):
        raise ProvisioningBlocked("OWNER_AUTH_READBACK_WITNESS_MISMATCH")
    _aware_datetime(data.get("expires_at"))
    return copy.deepcopy(data)


def read_owner_auth_receipt_v1(
    connect: Callable[[], Any],
    *,
    expected: dict[str, object],
    expected_login: str,
    timeout_ms: int = 2000,
) -> dict[str, Any]:
    """Read-only witness verification for owner auth/recovery receipts (lost-ACK reconciliation)."""
    pins = _validate_readback_pins(expected)
    _check_supervisor_args(connect, expected_login, timeout_ms)
    connection = None
    try:
        connection = connect()
        with _idle_cursor(connection) as cursor:
            _begin_and_check_login(cursor, expected_login, timeout_ms, readonly=True)
            data = _query_readback_with_cursor(cursor, pins)
        connection.rollback()
        connection.close()
        connection = None
        return data
    except ProvisioningBlocked:
        raise
    except Exception as error:
        code = getattr(getattr(error, "diag", None), "message_primary", None)
        if code in SAFE_NATIVE_ERRORS:
            raise ProvisioningBlocked(code) from None
        raise ProvisioningBlocked("OWNER_AUTH_READBACK_FAILED") from None
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                raise ProvisioningOutcomeUnknown("OWNER_AUTH_READBACK_CLOSE_UNCONFIRMED") from None


def _validate_execute_result(
    row: object,
    *,
    auth_request: str,
    installation: str,
    tenant: str,
    project: str,
    human: str,
    action: str,
    expected_token_hash: str | None,
) -> dict[str, Any]:
    data = (
        row[0]
        if isinstance(row, (tuple, list)) and type(row) in (tuple, list) and len(row) == 1
        else None
    )
    if type(data) is not dict:
        raise ProvisioningBlocked("INVALID_OWNER_AUTH_RESULT")
    expected_fields = {
        "auth_request_id": auth_request,
        "installation_id": installation,
        "tenant_id": tenant,
        "project_id": project,
        "principal_id": human,
        "action": action,
        "authorization": "SESSION_LIFECYCLE_ONLY_NOT_WORKFLOW_ACCEPTANCE",
    }
    for key, expected_val in expected_fields.items():
        if data.get(key) != expected_val:
            raise ProvisioningBlocked("OWNER_AUTH_RESULT_BINDING_MISMATCH")
    if (
        type(data.get("new_grants")) is not int
        or data["new_grants"] != 0
        or type(data.get("new_memberships")) is not int
        or data["new_memberships"] != 0
        or type(data.get("revoked_session_count")) is not int
        or data["revoked_session_count"] < 0
        or type(data.get("audit_id")) is not int
        or data["audit_id"] <= 0
        or data.get("outcome") not in OUTCOMES
    ):
        raise ProvisioningBlocked("OWNER_AUTH_RESULT_BINDING_MISMATCH")
    _uuid(data.get("session_id"))
    _hex64(data.get("token_hash"))
    _hex64(data.get("receipt_digest"))
    _aware_datetime(data.get("expires_at"))
    if expected_token_hash is not None and data["token_hash"] != expected_token_hash:
        raise ProvisioningBlocked("OWNER_AUTH_TOKEN_HASH_MISMATCH")
    return data


def _build_params(
    action: str,
    *,
    token: str | None,
    target_session_id: str | None,
    ttl_seconds: int,
) -> tuple[dict[str, object], str | None]:
    if action in ("ISSUE_SESSION", "RECOVER_ROTATE_SESSIONS"):
        if target_session_id is not None:
            raise ProvisioningBlocked("UNEXPECTED_TARGET_SESSION_FOR_ISSUE")
        if (
            type(token) is not str
            or not 32 <= len(token.encode("utf-8")) <= 4096
            or type(ttl_seconds) is not int
            or not 1 <= ttl_seconds <= 900
        ):
            raise ProvisioningBlocked("BOUNDED_OWNER_SESSION_REQUIRED")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return {"token_hash": token_hash, "ttl_seconds": ttl_seconds}, token_hash
    if token is not None:
        raise ProvisioningBlocked("UNEXPECTED_TOKEN_FOR_REVOKE")
    target = _uuid(target_session_id)
    return {"target_session_id": target}, None


def issue_committed_owner_auth_v1(
    connect: Callable[[], Any],
    *,
    installation_id: str,
    tenant_id: str,
    project_id: str,
    human_id: str,
    action: str,
    key_id: str,
    enrollment_revision: int,
    signing_key: bytes,
    expected_login: str,
    token: str | None = None,
    target_session_id: str | None = None,
    ttl_seconds: int = 300,
    auth_request_id: str | None = None,
    timeout_ms: int = 2000,
) -> dict[str, Any]:
    """Supervisor-only issue/revoke/recovery with commit + independent fresh readback.

    Plaintext token and signing_key never enter SQL arguments, logs or return
    values. Lost commit ACK or readback mismatch raises ProvisioningOutcomeUnknown
    without retrying.
    """
    installation = _uuid(installation_id)
    tenant = _uuid(tenant_id)
    project = _uuid(project_id)
    human = _uuid(human_id)
    key = _uuid(key_id)
    if type(action) is not str or action not in ACTIONS:
        raise ProvisioningBlocked("INVALID_OWNER_AUTH_ACTION")
    if type(enrollment_revision) is not int or enrollment_revision < 0:
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_REVISION_REQUIRED")
    if type(signing_key) is not bytes or len(signing_key) != 32:
        raise ProvisioningBlocked("EXACT_OWNER_AUTH_SIGNING_KEY_REQUIRED")
    _check_supervisor_args(connect, expected_login, timeout_ms)
    auth_request = _uuid(auth_request_id) if auth_request_id is not None else str(uuid4())
    params, expected_token_hash = _build_params(
        action,
        token=token,
        target_session_id=target_session_id,
        ttl_seconds=ttl_seconds,
    )

    connection = None
    committing = False
    committed = False
    writer = None
    try:
        connection = connect()
        writer = connection
        with _idle_cursor(connection) as cursor:
            _begin_and_check_login(cursor, expected_login, timeout_ms, readonly=False)
            ctx = _db_context(cursor, expected_login)
            wire = {
                "profile": PROFILE,
                "backend_pid": ctx["backend_pid"],
                "transaction_id": ctx["transaction_id"],
                "db_login": ctx["db_login"],
                "statement": {
                    "auth_request_id": auth_request,
                    "installation_id": installation,
                    "tenant_id": tenant,
                    "project_id": project,
                    "human_id": human,
                    "action": action,
                    "params": params,
                },
            }
            raw = raw_json(wire)
            tag = owner_auth_tag(
                signing_key,
                auth_request_id=auth_request,
                tenant_id=tenant,
                project_id=project,
                human_id=human,
                key_id=key,
                enrollment_revision=enrollment_revision,
                raw=raw,
            )
            cursor.execute(
                EXECUTE_QUERY,
                (installation, auth_request, key, enrollment_revision, raw, tag),
            )
            result = _validate_execute_result(
                cursor.fetchone(),
                auth_request=auth_request,
                installation=installation,
                tenant=tenant,
                project=project,
                human=human,
                action=action,
                expected_token_hash=expected_token_hash,
            )
        committing = True
        connection.commit()
        committed = True
        committing = False
        connection.close()
        connection = None

        connection = connect()
        if connection is writer:
            raise ProvisioningOutcomeUnknown("INDEPENDENT_OWNER_AUTH_READBACK_CONNECTION_REQUIRED")
        readback_pins = _validate_readback_pins(
            {
                "tenant_id": tenant,
                "auth_request_id": auth_request,
                "installation_id": installation,
                "project_id": project,
                "human_id": human,
                "action": action,
                "session_id": result["session_id"],
                "token_hash": expected_token_hash
                if expected_token_hash is not None
                else result["token_hash"],
                "receipt_digest": result["receipt_digest"],
            }
        )
        with _idle_cursor(connection) as cursor:
            _begin_and_check_login(cursor, expected_login, timeout_ms, readonly=True)
            readback = _query_readback_with_cursor(cursor, readback_pins)
        if (
            _aware_datetime(readback["expires_at"]) != _aware_datetime(result["expires_at"])
            or readback["revoked_session_count"] != result["revoked_session_count"]
            or readback["audit_id"] != result["audit_id"]
        ):
            raise ProvisioningOutcomeUnknown("OWNER_AUTH_READBACK_MISMATCH_REQUIRES_RECONCILIATION")
        connection.rollback()
        connection.close()
        connection = None

        return {
            "auth_request_id": auth_request,
            "installation_id": installation,
            "tenant_id": tenant,
            "project_id": project,
            "principal_id": human,
            "action": action,
            "session_id": result["session_id"],
            "expires_at": readback["expires_at"],
            "revoked_session_count": readback["revoked_session_count"],
            "receipt_digest": result["receipt_digest"],
            "audit_id": readback["audit_id"],
            "outcome": result["outcome"],
            "commit": "ACKNOWLEDGED",
            "independent_readback": "MATCH",
            "new_grants": 0,
            "new_memberships": 0,
            "authorization": "SESSION_LIFECYCLE_ONLY_NOT_WORKFLOW_ACCEPTANCE",
        }
    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        if committing or committed:
            raise ProvisioningOutcomeUnknown(
                "OWNER_AUTH_COMMIT_OR_READBACK_REQUIRES_RECONCILIATION"
            ) from None
        if isinstance(error, ProvisioningBlocked):
            raise
        code = getattr(getattr(error, "diag", None), "message_primary", None)
        if code in SAFE_NATIVE_ERRORS:
            raise ProvisioningBlocked(code) from None
        raise ProvisioningBlocked("OWNER_AUTH_NOT_COMMITTED") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                raise ProvisioningOutcomeUnknown(
                    "OWNER_AUTH_CONNECTION_CLOSE_UNCONFIRMED"
                ) from None
