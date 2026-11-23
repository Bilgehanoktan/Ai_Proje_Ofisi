"""Current native bootstrap window check, not general runtime authorization.

The trusted local DB clock and r56 root checks remain the authority. No Python
wall-clock fallback, root creation or clock-state override is available here.
The native function takes a row lock, so its dedicated transaction cannot be
READ ONLY. The adapter always rolls back and closes; it performs no DML.
"""

import copy
import re
from datetime import datetime
from uuid import UUID

from company_os.bootstrap.provisioning import ProvisioningBlocked

LOGIN = "company_provisioning_runtime_r55"
FIELDS = ("installation_id", "generation", "enrollment_digest", "host_boot_id")
QUERY = "SELECT company_private.bootstrap_window_readback_v1(%s::uuid,%s::bigint,%s::text,%s::uuid)"
RESULT_FIELDS = frozenset(
    FIELDS
    + (
        "utc_lower",
        "utc_upper",
        "boottime_ns",
        "backend_pid",
        "transaction_id",
        "db_login",
        "authorization",
        "new_grants",
    )
)


def inspect_current_bootstrap_window(connect, *, expected, timeout_ms=2000):
    pins = copy.deepcopy(expected)
    if type(pins) is not dict or set(pins) != set(FIELDS):
        raise ProvisioningBlocked("EXACT_BOOTSTRAP_WINDOW_PINS_REQUIRED")
    for name in ("installation_id", "host_boot_id"):
        try:
            if type(pins[name]) is not str or str(UUID(pins[name])) != pins[name]:
                raise ValueError()
        except ValueError, TypeError, AttributeError:
            raise ProvisioningBlocked("CANONICAL_BOOTSTRAP_WINDOW_ID_REQUIRED") from None
    if (
        type(pins["generation"]) is not int
        or not 1 <= pins["generation"] <= 9007199254740991
        or type(pins["enrollment_digest"]) is not str
        or re.fullmatch("[a-f0-9]{64}", pins["enrollment_digest"]) is None
    ):
        raise ProvisioningBlocked("EXACT_BOOTSTRAP_WINDOW_BINDING_REQUIRED")
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
        raise ProvisioningBlocked("BOUNDED_TIMEOUT_REQUIRED")
    connection = None
    try:
        connection = connect()
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise ProvisioningBlocked("IDLE_DEDICATED_TRANSACTION_REQUIRED")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
            for name in (
                "statement_timeout",
                "lock_timeout",
                "idle_in_transaction_session_timeout",
            ):
                cursor.execute("SELECT set_config(%s,%s,true)", (name, str(timeout_ms) + "ms"))
            cursor.execute("SELECT pg_backend_pid(),pg_current_xact_id()::text,session_user")
            context = cursor.fetchone()
            if (
                type(context) is not tuple
                or len(context) != 3
                or type(context[0]) is not int
                or context[0] < 1
                or type(context[1]) is not str
                or re.fullmatch("[0-9]+", context[1]) is None
                or context[2] != LOGIN
            ):
                raise ProvisioningBlocked("BOOTSTRAP_WINDOW_CONTEXT_REQUIRED")
            cursor.execute(QUERY, tuple(pins[name] for name in FIELDS))
            row = cursor.fetchone()
            result = row[0] if type(row) is tuple and len(row) == 1 else None
            if (
                type(result) is not dict
                or set(result) != RESULT_FIELDS
                or any(result[name] != pins[name] for name in FIELDS)
                or type(result["generation"]) is not int
                or (result["backend_pid"], result["transaction_id"], result["db_login"]) != context
                or type(result["backend_pid"]) is not int
                or result["authorization"] != "BOOTSTRAP_WINDOW_ONLY_NOT_RUNTIME"
                or type(result["new_grants"]) is not int
                or result["new_grants"] != 0
                or type(result["boottime_ns"]) is not int
                or result["boottime_ns"] < 0
            ):
                raise ProvisioningBlocked("CURRENT_BOOTSTRAP_WINDOW_MISMATCH")
            times = []
            for name in ("utc_lower", "utc_upper"):
                if type(result[name]) is not str:
                    raise ValueError()
                value = datetime.fromisoformat(result[name])
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError()
                times.append(value)
            if times[0] > times[1]:
                raise ValueError()
        return copy.deepcopy(result)
    except ProvisioningBlocked:
        raise
    except Exception:
        raise ProvisioningBlocked("CURRENT_BOOTSTRAP_WINDOW_UNAVAILABLE") from None
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                raise ProvisioningBlocked("BOOTSTRAP_WINDOW_ROLLBACK_FAILED") from None
            finally:
                try:
                    connection.close()
                except Exception:
                    raise ProvisioningBlocked("BOOTSTRAP_WINDOW_CLOSE_FAILED") from None
