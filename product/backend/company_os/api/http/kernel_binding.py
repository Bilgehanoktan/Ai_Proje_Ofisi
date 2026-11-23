"""Explicit HTTP→existing Kernel binding; not a full runtime profile/installer.

No roles, grants, sessions, databases or secrets are created. A supervisor owns
the profile pin and libpq service configuration. Native token authorization is
still required per operation. Catalog precheck is not application acceptance.
"""

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path, PurePosixPath

from company_os.api.http.task_http import create_project_backend, create_server
from company_os.kernel import command_host

FIELDS = frozenset(
    (
        "version",
        "canonical_workspace",
        "postgres_service",
        "database",
        "expected_login",
        "socket_directory",
        "project_id",
        "grant_ids",
        "port",
        "emission_timeout",
    )
)


class BindingBlocked(ValueError):
    pass


def load_binding(path, *, expected_sha256):
    if type(expected_sha256) is not str or re.fullmatch("[a-f0-9]{64}", expected_sha256) is None:
        raise BindingBlocked("EXTERNAL_BINDING_PIN_REQUIRED")
    with Path(path).open("rb") as source:
        raw = source.read(32769)
    if len(raw) > 32768 or not hmac.compare_digest(
        hashlib.sha256(raw).hexdigest(), expected_sha256
    ):
        raise BindingBlocked("BINDING_BYTES_MISMATCH")

    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BindingBlocked("DUPLICATE_BINDING_KEY")
            result[key] = value
        return result

    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(BindingBlocked("NONFINITE_BINDING")),
        )
    except ValueError, UnicodeError:
        raise BindingBlocked("INVALID_BINDING_DOCUMENT") from None
    if type(data) is not dict or set(data) != FIELDS:
        raise BindingBlocked("EXACT_BINDING_FIELDS_REQUIRED")
    if (
        data["version"] != "company.http-kernel-binding/1"
        or data["canonical_workspace"] != "E:\\Projeler\\Ai_Proje_Ofisi"
    ):
        raise BindingBlocked("BINDING_SCOPE_MISMATCH")
    for key in ("postgres_service", "database", "expected_login"):
        if (
            type(data[key]) is not str
            or re.fullmatch("[A-Za-z_][A-Za-z0-9_.-]{0,62}", data[key]) is None
        ):
            raise BindingBlocked("NONSECRET_SERVICE_REFERENCE_REQUIRED")
    directory = data["socket_directory"]
    if (
        type(directory) is not str
        or not directory.startswith("/")
        or "\\" in directory
        or "\x00" in directory
        or ".." in PurePosixPath(directory).parts
        or str(PurePosixPath(directory)) != directory
    ):
        raise BindingBlocked("EXACT_LOCAL_POSTGRES_SOCKET_REQUIRED")
    if type(data["port"]) is not int or not 1024 <= data["port"] <= 65535:
        raise BindingBlocked("BOUNDED_UI_PORT_REQUIRED")
    try:
        # Reuse existing UI scope validation. This validates reference shape,
        # never the existence/current authority of the referred grant.
        create_project_backend(
            connect=lambda: None,
            project_id=data["project_id"],
            grant_ids=data["grant_ids"],
            emission_timeout=data["emission_timeout"],
        )
    except ValueError:
        raise BindingBlocked("INVALID_PROJECT_GRANT_BINDING") from None
    return copy.deepcopy(data)


def required_functions(profile):
    functions = {
        "company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid)",
        "company_private.r55_cp_context_exit(uuid)",
        "company_private.r58_emission_snapshot()",
        "company_private.r58_emission_check(jsonb)",
    }
    for operation in profile["grant_ids"]:
        name, types = command_host.ROUTES[operation]
        functions.add("company_private." + name + "(" + ",".join(types) + ")")
    if command_host.CONSTRUCTOR_OPERATIONS & profile["grant_ids"].keys():
        functions.add("company_private.r63_constructor_result(uuid)")
    return sorted(functions)


def check_connection(connection, profile):
    """Leaves a verified dedicated connection idle; caller owns it on success."""
    try:
        if connection.autocommit or int(connection.info.transaction_status) != 0:
            raise BindingBlocked("IDLE_KERNEL_CONNECTION_REQUIRED")
        if connection.info.host != profile["socket_directory"]:
            raise BindingBlocked("POSTGRES_SOCKET_MISMATCH")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for setting in (
                "statement_timeout",
                "lock_timeout",
                "idle_in_transaction_session_timeout",
            ):
                cursor.execute("SELECT set_config(%s,%s,true)", (setting, "2000ms"))
            cursor.execute(
                "SELECT session_user,current_user,current_database(),pg_is_in_recovery(),"
                "r.rolsuper,r.rolbypassrls,r.rolcreaterole FROM pg_catalog.pg_roles r WHERE r.rolname=session_user"
            )
            expected = (
                profile["expected_login"],
                profile["expected_login"],
                profile["database"],
                False,
                False,
                False,
                False,
            )
            row = cursor.fetchone()
            if row != expected or any(type(v) is not bool for v in row[3:]):
                raise BindingBlocked("KERNEL_LOGIN_DATABASE_OR_ROLE_MISMATCH")
            functions = required_functions(profile)
            cursor.execute(
                "SELECT name,coalesce(pg_catalog.has_function_privilege(session_user,"
                "pg_catalog.to_regprocedure(name),'EXECUTE'),false) FROM unnest(%s::text[]) AS f(name)",
                (functions,),
            )
            rows = cursor.fetchall()
            if (
                type(rows) is not list
                or len(rows) != len(functions)
                or {name for name, _ in rows} != set(functions)
                or any(allowed is not True for _, allowed in rows)
            ):
                raise BindingBlocked("NATIVE_HTTP_FUNCTION_ACCESS_MISSING")
        connection.rollback()
        return {
            "status": "BINDINGS_PRECHECK_PASSED_NOT_ACCEPTANCE",
            "checked_functions": len(functions),
        }
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass
        raise BindingBlocked("KERNEL_CONNECTION_NOT_VERIFIED") from None


def make_connector(profile, *, driver_connect=None):
    pins = copy.deepcopy(profile)
    if driver_connect is None:
        import psycopg

        driver_connect = psycopg.connect

    def connect():
        try:
            # Credentials remain in the supervisor's libpq service/custody.
            # Host/database/user pins override service defaults; no TCP fallback.
            connection = driver_connect(
                service=pins["postgres_service"],
                host=pins["socket_directory"],
                dbname=pins["database"],
                user=pins["expected_login"],
                connect_timeout=3,
            )
        except Exception:
            raise BindingBlocked("KERNEL_CONNECTION_UNAVAILABLE") from None
        check_connection(connection, pins)
        return connection

    return connect


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Mevcut yetkili Kernel bağlantısıyla yerel görev ekranı"
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = load_binding(args.profile, expected_sha256=args.sha256)
        connect = make_connector(profile)
        connection = connect()
        connection.close()
        if args.check_only:
            print(
                json.dumps(
                    {
                        "status": "BINDINGS_PRECHECK_PASSED_NOT_ACCEPTANCE",
                        "session_and_grants_authorized": False,
                        "task_execution_verified": False,
                    }
                )
            )
            return 0
        backend = create_project_backend(
            connect=connect,
            project_id=profile["project_id"],
            grant_ids=profile["grant_ids"],
            emission_timeout=profile["emission_timeout"],
        )
        with create_server(port=profile["port"], backend=backend) as server:
            print(
                "Görev bağlantısı tanımlandı: http://127.0.0.1:" + str(server.server_port),
                flush=True,
            )
            print("Oturum ve görev yetkileri her işlemde Kernel tarafından doğrulanır.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": "APPROVED_KERNEL_BINDING_NOT_VERIFIED",
                    "task_execution_verified": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
