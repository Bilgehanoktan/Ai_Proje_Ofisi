"""Native DB-API/socket host candidate. No connection/server started on import.

All keys remain in the enrolled SecretAdapter/DB verifier, never SQL arguments.
Every callable route and SQL cast list is server-owned, not user SQL text.
"""

import hashlib
import json
import math
import time
from uuid import UUID


class Blocked(ValueError):
    pass


class UnknownCommitOutcome(RuntimeError):
    pass


CONSTRUCTOR_OPERATIONS = frozenset({"objectives.create", "plans.create", "tasks.create"})


ROUTES = {
    "objectives.create": ("r53_objectives_create", ("jsonb",)),
    "plans.create": ("r54_plans_create", ("jsonb",)),
    "tasks.create": ("r54_tasks_create", ("jsonb",)),
    "tasks.ready": ("r60_tasks_ready", ("uuid", "bigint", "text", "jsonb")),
    "engine.bind": ("r60_engine_bind", ("uuid", "text", "uuid")),
    "tool.consume": ("r60_tool_consume", ("uuid", "bytea", "text", "uuid")),
    "process.lease_prepare": ("r60_lease_prepare", ("uuid", "bigint", "text", "uuid")),
    "process.lease_commit": ("r60_lease_commit", ("uuid", "uuid", "text", "uuid")),
    "process.lease_activate": ("r60_lease_activate", ("uuid", "uuid", "text", "uuid")),
    "process.lease_read": ("r60_lease_read", ("uuid",)),
    "process.reconcile": ("r60_process_reconcile", ("uuid", "uuid", "text", "uuid")),
    "worker.claim": (
        "r58_worker_claim",
        ("uuid", "bigint", "uuid", "text", "bigint", "text", "uuid"),
    ),
    "worker.heartbeat": (
        "r58_worker_heartbeat",
        ("uuid", "uuid", "bigint", "bigint", "text", "uuid"),
    ),
    "workspace.current_head": ("r58_workspace_current_head", ("uuid", "text", "uuid")),
    "process.launch_reserve": (
        "r58_launch_reserve",
        ("uuid", "uuid", "bigint", "uuid", "text", "uuid"),
    ),
    "process.launch_consume": ("r58_launch_consume", ("uuid", "text", "text", "uuid")),
    "process.launch_callback": ("r58_launch_callback", ("uuid", "uuid", "text", "uuid")),
    "tool.authorize_final": (
        "r58_tool_authorize_final",
        ("uuid", "uuid", "bigint", "uuid", "text", "text", "text", "uuid"),
    ),
    "patch.receipt": ("r58_patch_receipt", ("uuid", "uuid", "bigint", "uuid", "text", "uuid")),
    "verification.final_seal": (
        "r58_verification_final_seal",
        ("uuid", "uuid", "bigint", "uuid", "text", "uuid"),
    ),
    "evidence.provenance": (
        "r58_evidence_provenance",
        ("uuid", "uuid", "bigint", "uuid", "text", "uuid"),
    ),
    "verification.accept": (
        "r58_verification_accept",
        ("uuid", "uuid", "bigint", "bigint", "uuid", "text", "uuid"),
    ),
    "process.stop_release": (
        "r58_process_stop_release",
        ("uuid", "bigint", "uuid", "text", "uuid"),
    ),
    "evidence.attestation_ingest": (
        "r58_attestation_ingest",
        ("uuid", "uuid", "uuid", "bigint", "text", "bytea", "bytea", "text", "uuid"),
    ),
    "candidate.r58.artifacts.read": ("r58_signed_artifact_read", ("uuid",)),
}
ROUTES.update(
    {
        "CAP-017.revoke": ("r53_revoke_project_grant", ("jsonb",)),
        "e0.setup_mandate_consume": ("r54_e0_setup_mandate_consume", ("uuid", "uuid")),
        "e0.qualification_candidate_issue": (
            "r54_qualification_candidate_issue",
            ("uuid", "timestamptz", "text", "uuid"),
        ),
        "e0.evaluation_artifact_record": (
            "r54_e0_evaluation_artifact_record",
            ("uuid", "jsonb", "text", "uuid"),
        ),
        "qualification.activate": (
            "r54_qualification_decide",
            ("uuid", "bigint", "uuid", "uuid", "uuid", "boolean", "text", "uuid"),
        ),
        "qualification.revoke": (
            "r54_qualification_decide",
            ("uuid", "bigint", "uuid", "uuid", "uuid", "boolean", "text", "uuid"),
        ),
    }
)
FINALITY_ROUTES = frozenset(
    [
        "CAP-017.revoke",
        "e0.setup_mandate_consume",
        "e0.qualification_candidate_issue",
        "e0.evaluation_artifact_record",
        "qualification.activate",
        "qualification.revoke",
    ]
)
for _resource in [
    "attempts",
    "qualifications",
    "agent_runs",
    "tool_requests",
    "evidence",
    "acceptance_decisions",
]:
    ROUTES["candidate.r54." + _resource + ".read"] = (
        "r54_" + _resource + "_read",
        ("uuid", "uuid", "uuid", "text", "bigint"),
    )


def enter(cursor, auth, operation):
    if "grant_ids" in auth and auth["grant_ids"] is not None:
        grant_ids = auth["grant_ids"]
        if type(grant_ids) is not dict or operation not in grant_ids:
            raise Blocked("EXACT_OPERATION_GRANT_BINDING_REQUIRED")
        grant_id = grant_ids[operation]
    else:
        grant_id = auth["grant_id"]
    cursor.execute(
        "SELECT company_private.r54_context_enter(%s::text,%s::text,%s::uuid,%s::text,%s::uuid,%s::uuid,%s::uuid,%s::bigint,%s::uuid)",
        (
            auth["token"],
            operation,
            auth["project_id"],
            auth["kind"],
            auth["resource_id"],
            auth.get("task_id"),
            auth.get("attempt_id"),
            auth.get("fence"),
            grant_id,
        ),
    )
    return cursor.fetchone()[0]


def execute(connection, auth, operation, args, *, timeout_ms=2000, read_command_id=None):
    committing = False
    try:
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
            raise Blocked("BOUNDED_COMMAND_TIMEOUT_REQUIRED")
        if operation not in ROUTES:
            raise Blocked("ROUTE_NOT_REGISTERED")
        name, types = ROUTES[operation]
        if read_command_id is not None:
            if (
                operation not in CONSTRUCTOR_OPERATIONS
                or args
                or type(read_command_id) is not str
                or str(UUID(read_command_id)) != read_command_id
            ):
                raise Blocked("EXACT_CONSTRUCTOR_READBACK_REQUIRED")
        elif len(args) != len(types):
            raise Blocked("EXACT_ARGUMENTS_REQUIRED")
        if int(connection.info.transaction_status) != 0:
            raise Blocked("IDLE_DEDICATED_CONNECTION_REQUIRED")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            for setting in [
                "statement_timeout",
                "lock_timeout",
                "idle_in_transaction_session_timeout",
            ]:
                cursor.execute("SELECT set_config(%s,%s,true)", (setting, str(timeout_ms) + "ms"))
            nonce = enter(cursor, auth, operation)
            snapshot = None
            if operation == "CAP-017.revoke":
                cursor.execute("SELECT company_private.r58_emission_snapshot()")
                snapshot = cursor.fetchone()[0]
            if operation in {"qualification.activate", "qualification.revoke"} and (
                type(args[5]) is not bool or args[5] != (operation == "qualification.revoke")
            ):
                raise Blocked("EXACT_QUALIFICATION_DECISION_ROUTE_REQUIRED")
            sql = "SELECT company_private." + name + "(" + ",".join("%s::" + t for t in types) + ")"
            if read_command_id is None:
                cursor.execute(sql, tuple(args))
            else:
                # Existing native readback binds principal/project/operation and
                # rechecks immutable audit/outbox witnesses. Never replay DML.
                cursor.execute(
                    "SELECT company_private.r63_constructor_result(%s::uuid)",
                    (read_command_id,),
                )
            row = cursor.fetchone()
            if not row or type(row[0]) is not dict:
                raise Blocked("INVALID_NATIVE_RESULT")
            if operation in CONSTRUCTOR_OPERATIONS:
                if row[0].get("state") != "SUCCEEDED" or not row[0].get("command_id"):
                    raise Blocked("SEALED_CONSTRUCTOR_RECEIPT_REQUIRED")
                if read_command_id is None:
                    cursor.execute(
                        "SELECT company_private.r63_constructor_result(%s::uuid)",
                        (row[0]["command_id"],),
                    )
                    row = cursor.fetchone()
                elif row[0]["command_id"] != read_command_id:
                    raise Blocked("CONSTRUCTOR_READBACK_ID_MISMATCH")
                if not row or type(row[0]) is not dict or "result_payload" not in row[0]:
                    raise Blocked("CANONICAL_CONSTRUCTOR_RESULT_REQUIRED")
            if operation in FINALITY_ROUTES and (
                "result_payload" not in row[0] or not row[0].get("command_id")
            ):
                raise Blocked("CANONICAL_FINALITY_RESULT_REQUIRED")
            native = json.loads(json.dumps(row[0], allow_nan=False))
            receipt = None
            if "result_payload" in native:
                if native.get("state") != "SUCCEEDED" or type(native["result_payload"]) is not dict:
                    raise Blocked("INVALID_FINALIZED_COMMAND_RESULT")
                result = native.pop("result_payload")
                receipt = native
            else:
                result = native
            if snapshot is None:
                cursor.execute("SELECT company_private.r58_emission_snapshot()")
                snapshot = cursor.fetchone()[0]
            cursor.execute("SELECT company_private.r55_cp_context_exit(%s::uuid)", (nonce,))
        committing = True
        connection.commit()
        committing = False
        return dict(result=result, command_receipt=receipt, snapshot=snapshot, operation=operation)
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        if committing:
            raise UnknownCommitOutcome("UNKNOWN_COMMIT_OUTCOME_NO_AUTOMATIC_RETRY") from None
        raise Blocked("NO_COMMAND_RESULT_RELEASED") from None
    finally:
        connection.close()


def _emit(
    connection,
    auth,
    envelope,
    socket,
    approved_timeout,
    *,
    chunk_size=16384,
    max_response_bytes=1048576,
):
    """Call only with an enrolled bounded socket and matching native revoke path.

    Scope advisory locks are held throughout each bounded send. No transfer to an
    uncontrolled async queue. This cannot retract bytes already sent or buffered.
    """
    if (
        type(approved_timeout) not in (int, float)
        or not math.isfinite(approved_timeout)
        or approved_timeout <= 0
    ):
        raise Blocked("APPROVED_FINITE_EMISSION_TIMEOUT_REQUIRED")
    if type(chunk_size) is not int or not 1 <= chunk_size <= 65536:
        raise Blocked("BOUNDED_CHUNK_REQUIRED")
    if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 1048576:
        raise Blocked("BOUNDED_RESPONSE_REQUIRED")
    if int(connection.info.transaction_status) != 0:
        raise Blocked("IDLE_DEDICATED_CONNECTION_REQUIRED")
    operation = envelope["operation"]
    if operation not in ROUTES:
        raise Blocked("ROUTE_NOT_REGISTERED")
    deadline = time.monotonic() + approved_timeout
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload = dict(
        result=envelope["result"],
        command_receipt=envelope.get("command_receipt"),
        authorization_snapshot=envelope["snapshot"],
        semantics="AUTHORIZED_FACT_NOT_CURRENT_STATE",
    )
    parts = []
    size = 0
    for part in encoder.iterencode(payload):
        encoded = part.encode()
        size += len(encoded)
        if size > max_response_bytes:
            raise Blocked("RESPONSE_BYTE_LIMIT_EXCEEDED")
        if time.monotonic() >= deadline:
            raise Blocked("TOTAL_EMISSION_DEADLINE_EXCEEDED")
        parts.append(encoded)
    body = b"".join(parts)
    snapshot = envelope["snapshot"]
    sent = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            nonce = enter(cursor, auth, operation)
            for offset in range(0, len(body), chunk_size):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Blocked("TOTAL_EMISSION_DEADLINE_EXCEEDED")
                # Bound the DB check as well as the socket; expire again after the check.
                cursor.execute(
                    "SELECT set_config('statement_timeout',%s,true)",
                    (str(max(1, int(remaining * 1000))) + "ms",),
                )
                cursor.execute(
                    "SELECT company_private.r58_emission_check(%s::jsonb)",
                    (json.dumps(snapshot, allow_nan=False),),
                )
                if cursor.fetchone()[0] is not True:
                    raise Blocked("EMISSION_REVOKED_OR_STALE")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Blocked("TOTAL_EMISSION_DEADLINE_EXCEEDED")
                socket.settimeout(remaining)
                socket.sendall(body[offset : offset + chunk_size])
                sent += min(chunk_size, len(body) - offset)
                if time.monotonic() >= deadline:
                    raise Blocked("TOTAL_EMISSION_DEADLINE_EXCEEDED")
            cursor.execute("SELECT company_private.r55_cp_context_exit(%s::uuid)", (nonce,))
        connection.commit()
        return dict(bytes_sent=sent, response_digest=hashlib.sha256(body).hexdigest())
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        # sendall failure can mean partial bytes even if it never returned.
        raise UnknownCommitOutcome("UNKNOWN_EMISSION_OUTCOME_NO_AUTOMATIC_RESEND") from None


def emit(
    connection,
    auth,
    envelope,
    socket,
    approved_timeout,
    *,
    chunk_size=16384,
    max_response_bytes=1048576,
):
    """Own the connection even when validation/serialization fails before BEGIN."""
    try:
        return _emit(
            connection,
            auth,
            envelope,
            socket,
            approved_timeout,
            chunk_size=chunk_size,
            max_response_bytes=max_response_bytes,
        )
    finally:
        connection.close()
