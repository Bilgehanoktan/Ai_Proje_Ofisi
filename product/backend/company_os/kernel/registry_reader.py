"""Dedicated DB-API connection üzerinden salt okunur registry önkontrolü.

Bağlantı sağlayıcı kimliği dışarıdan verir. Bu modül login/grant oluşturmaz.
DB rolünün registry SELECT erişimi ayrıca sağlanmış olmalıdır.
"""

from company_os.kernel.registry_preflight import REQUIRED, RegistryBlocked, check_required_registry

FIELDS = (
    "operation_id",
    "permission",
    "scope_kind",
    "execution_class",
    "policy_revision",
    "approved_policy_digest",
)
QUERY = (
    "SELECT operation_id, permission, scope_kind, execution_class, "
    "policy_revision, approved_policy_digest "
    "FROM company_private.operation_permissions "
    "WHERE operation_id = ANY(%s::text[]) ORDER BY operation_id"
)


def inspect_registry(connect, *, timeout_ms=2000):
    """Tek tutarlı snapshot okur; sonuç yalnız şekil kontrolüdür.

    connect() yeni, idle, autocommit kapalı ve dedicated connection vermelidir.
    SELECT sonrası rollback ile kapanır; satır veya policy değiştirilmez.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000:
        raise RegistryBlocked("BOUNDED_TIMEOUT_REQUIRED")
    connection = connect()
    try:
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise RegistryBlocked("IDLE_DEDICATED_TRANSACTION_REQUIRED")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for setting in (
                "statement_timeout",
                "lock_timeout",
                "idle_in_transaction_session_timeout",
            ):
                cursor.execute("SELECT set_config(%s,%s,true)", (setting, str(timeout_ms) + "ms"))
            cursor.execute(QUERY, (sorted(REQUIRED),))
            raw = cursor.fetchall()
            if any(not isinstance(row, (tuple, list)) or len(row) != len(FIELDS) for row in raw):
                raise RegistryBlocked("INVALID_REGISTRY_READBACK")
            result = check_required_registry([dict(zip(FIELDS, row)) for row in raw])
        connection.rollback()
        return result
    except RegistryBlocked:
        raise
    except Exception:
        # DB exception text may contain connection details; do not expose it.
        raise RegistryBlocked("REGISTRY_READBACK_FAILED") from None
    finally:
        # Failed cleanup must not turn an unsuccessful read into a success.
        try:
            connection.rollback()
        except Exception:
            raise RegistryBlocked("REGISTRY_CLEANUP_FAILED") from None
        finally:
            try:
                connection.close()
            except Exception:
                raise RegistryBlocked("REGISTRY_CLOSE_FAILED") from None
