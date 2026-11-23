"""Read-only reconciliation of the dedicated local instance; no acceptance."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_postgres import DATABASE, checked_layout, connect_database, inspect


def installation_readiness(connection) -> dict:
    """Diagnostic snapshot only; OS/DB time here never grants authority."""
    boot = Path("/proc/sys/kernel/random/boot_id").read_text("ascii").strip()
    boottime = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    rows = connection.execute(
        "SELECT installation_id::text,generation,host_boot_id=%s::uuid,"
        "(r56_anchor_boottime_ns<=%s AND %s<not_after_boottime_ns),"
        "(not_before<=transaction_timestamp() AND transaction_timestamp()<not_after),"
        "revoked_at IS NOT NULL,compromised_at IS NOT NULL "
        "FROM company_private.r55_setup_root_enrollments ORDER BY installation_id,generation",
        (boot, boottime, boottime),
    ).fetchall()
    roots = []
    for installation, generation, same_boot, boot_window, wall_window, revoked, compromised in rows:
        blockers = []
        for ok, reason in (
            (same_boot, "HOST_BOOT_MISMATCH"),
            (boot_window, "ROOT_BOOTTIME_WINDOW_CLOSED"),
            (wall_window, "ROOT_WALL_TIME_WINDOW_CLOSED"),
            (not revoked, "ROOT_REVOKED"),
            (not compromised, "ROOT_COMPROMISED"),
        ):
            if ok is not True:
                blockers.append(reason)
        roots.append(dict(installation_id=installation, generation=generation, blockers=blockers))
    receipts = connection.execute(
        "SELECT count(*),count(*) FILTER (WHERE e0_valid_until>transaction_timestamp()),"
        "(SELECT count(*) FROM company_private.installation_bootstrap_control WHERE state='CONSUMED') "
        "FROM company_private.bootstrap_receipts"
    ).fetchone()
    return dict(
        scope="DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION",
        roots=roots,
        bootstrap_receipts_total=receipts[0],
        bootstrap_receipts_unexpired=receipts[1],
        consumed_installations=receipts[2],
        rerun_bootstrap_is_recovery=False,
        next_step="SUPPORTED_OWNER_AUTH_OR_RECOVERY_REQUIRED"
        if not any(not root["blockers"] for root in roots) or receipts[1] == 0
        else "CHECK_NATIVE_AUTHORITY_AND_SESSION",
    )


def owner_auth_readiness(connection) -> dict:
    """Read-only diagnostic of post-bootstrap owner-auth v1 native status."""
    native_row = connection.execute(
        "SELECT "
        "pg_catalog.to_regprocedure('company_private.owner_auth_execute_v1(uuid,uuid,uuid,bigint,bytea,bytea)') IS NOT NULL,"
        "pg_catalog.to_regprocedure('company_private.owner_auth_receipt_readback_v1(uuid,uuid,uuid,uuid,uuid,text,uuid,text,text)') IS NOT NULL,"
        "pg_catalog.to_regclass('company_private.owner_auth_receipts_v1') IS NOT NULL"
    ).fetchone()
    native_installed = native_row == (True, True, True)
    signer_row = connection.execute(
        "SELECT count(*) FROM company.signer_enrollments "
        "WHERE purpose='OWNER_AUTH' AND revoked_at IS NULL AND compromised_since IS NULL "
        "AND valid_from<=transaction_timestamp() AND transaction_timestamp()<valid_until"
    ).fetchone()
    clock_row = connection.execute(
        "SELECT count(*) FROM company.clock_epochs WHERE invalidated_at IS NULL"
    ).fetchone()
    active_signers = int(signer_row[0]) if signer_row else 0
    active_clocks = int(clock_row[0]) if clock_row else 0
    if not native_installed:
        next_step = "INSTALL_OWNER_AUTH_V1_AFTER_G0_APPROVAL"
    elif active_signers < 1 or active_clocks < 1:
        next_step = "ENROLL_OWNER_AUTH_SIGNER_AND_CLOCK_REQUIRED"
    else:
        next_step = "READY_FOR_NATIVE_OWNER_AUTH_CHECK"
    return dict(
        scope="DIAGNOSTIC_ONLY_NOT_NATIVE_AUTHORIZATION",
        native_v1_installed=native_installed,
        active_owner_auth_signers=active_signers,
        active_clock_epochs=active_clocks,
        next_step=next_step,
    )


def audit():
    result = {"scope": "READ_ONLY_LOCAL_STATE_NOT_TRUST_ACCEPTANCE", "foundation": inspect()}
    with connect_database(checked_layout(), DATABASE) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        result["read_only"] = connection.execute("SHOW transaction_read_only").fetchone()[0]
        result["postgres_version"] = connection.execute("SHOW server_version").fetchone()[0]
        tables = connection.execute(
            "SELECT schemaname, tablename FROM pg_catalog.pg_tables WHERE schemaname IN ('company','company_private') ORDER BY 1,2"
        ).fetchall()
        result["table_counts"] = {}
        from psycopg import sql

        for schema, table in tables:
            result["table_counts"][schema + "." + table] = connection.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchone()[0]
        result["disabled_user_triggers"] = connection.execute(
            "SELECT n.nspname,c.relname,t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('company','company_private') AND NOT t.tgisinternal AND t.tgenabled='D' ORDER BY 1,2,3"
        ).fetchall()
        result["rls_tables"] = connection.execute(
            "SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('company','company_private') AND c.relkind='r' ORDER BY 1,2"
        ).fetchall()
        result["session_columns"] = [
            r[0]
            for r in connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='company' AND table_name='sessions' ORDER BY ordinal_position"
            )
        ]
        result["sessions_summary"] = dict(
            zip(
                ("total", "unexpired_unrevoked"),
                connection.execute(
                    "SELECT count(*),count(*) FILTER (WHERE revoked_at IS NULL AND expires_at>transaction_timestamp()) FROM company.sessions"
                ).fetchone(),
            )
        )
        result["installation_readiness"] = installation_readiness(connection)
        result["owner_auth_readiness"] = owner_auth_readiness(connection)
        result["acceptance"] = "NOT_VERIFIED; ROW_EXISTENCE_IS_NOT_AUTHORIZED_PROVENANCE"
        connection.rollback()
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="Salt okunur yerel kurulum ve oturum tanısı")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        command = [
            "wsl.exe",
            "-d",
            "Ubuntu-E",
            "--user",
            "aipof-dbtest",
            "--exec",
            "/mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python",
            "-B",
            "/mnt/e/Projeler/Ai_Proje_Ofisi/scripts/database/audit_local_state.py",
        ]
        if args.summary:
            command.append("--summary")
        try:
            completed = subprocess.run(command, capture_output=True, timeout=30)
            if completed.returncode != 0:
                raise RuntimeError()
            result = json.loads(completed.stdout.decode("utf-8"))
        except OSError, ValueError, RuntimeError, subprocess.TimeoutExpired:
            print(json.dumps(dict(status="BLOCKED", reason="LOCAL_WSL_AUDIT_UNAVAILABLE")))
            return 2
    else:
        try:
            result = audit()
        except Exception:
            print(json.dumps(dict(status="BLOCKED", reason="LOCAL_DATABASE_AUDIT_UNAVAILABLE")))
            return 2
    if args.summary:
        result = {
            name: result[name]
            for name in (
                "scope",
                "foundation",
                "postgres_version",
                "sessions_summary",
                "installation_readiness",
                "owner_auth_readiness",
            )
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
