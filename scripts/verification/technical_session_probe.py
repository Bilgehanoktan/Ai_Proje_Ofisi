"""Native low-level principal session writer inside a private rollback-only fixture."""

import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from uuid import uuid4

import psycopg

from run_sql_fixture import ROOT, fixture_sql

sys.path.insert(0, str(ROOT / "product/backend"))
from company_os.bootstrap.provisioning import ProvisioningBlocked
from company_os.kernel.session_provisioning import issue_principal_session


def check_writer(connection, role):
    installation, tenant = connection.execute(
        "SELECT installation_id, tenant_id FROM company_private.bootstrap_receipts"
    ).fetchone()
    principal = uuid4()
    initial_grants = connection.execute("SELECT count(*) FROM company.project_grants").fetchone()
    connection.execute(
        "INSERT INTO company.principals (tenant_id,id,name,kind) VALUES (%s,%s,'technical session fixture',%s)",
        (tenant, principal, role),
    )
    token = secrets.token_urlsafe(48)
    with connection.cursor() as cursor:
        try:
            issue_principal_session(cursor, installation_id=str(installation), principal_id=str(principal),
                                    role=role, token=token)
        except ProvisioningBlocked as error:
            if str(error) != "CURRENT_BOOTSTRAPPED_MEMBERSHIP_REQUIRED":
                raise
        else:
            raise RuntimeError("Session issued without an existing membership")

        # Membership is a synthetic prerequisite. All subsequent SQL is the product writer.
        cursor.execute("INSERT INTO company.memberships VALUES (%s,%s,%s)", (tenant, principal, role))
        result = issue_principal_session(cursor, installation_id=str(installation),
                                         principal_id=str(principal), role=role, token=token)
    row = connection.execute(
        """SELECT s.token_hash, h.epoch, l.rank, s.expires_at,
              (SELECT count(*) FROM company.audit_events e WHERE e.tenant_id=s.tenant_id
               AND e.actor_id=s.principal_id AND e.kind='PrincipalSessionIssued')
           FROM company.sessions s JOIN company.authority_scope_heads h
             ON h.tenant_id=s.tenant_id AND h.scope_kind='SESSION'
             AND h.scope_ref=s.id AND h.session_id=s.id
           JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
           WHERE s.tenant_id=%s AND s.principal_id=%s AND s.id=%s AND s.revoked_at IS NULL""",
        (tenant, principal, result["session_id"]),
    ).fetchall()
    expected = (hashlib.sha256(token.encode()).hexdigest(), 0, 2, result["expires_at"], 1)
    if row != [expected] or result["new_grants"] or result["new_memberships"]:
        raise RuntimeError("Technical session writer readback mismatch")
    if connection.execute("SELECT count(*) FROM company.project_grants").fetchone() != initial_grants:
        raise RuntimeError("Unexpected project grant change")
    acl = connection.execute(
        """SELECT has_function_privilege('company_provisioning_runtime_r55',
                 'company_private.r56_root_bounds(uuid)','EXECUTE'),
                 has_table_privilege('company_provisioning_runtime_r55','company.sessions','INSERT')"""
    ).fetchone()
    return acl


def main():
    if sys.platform != "linux" or os.getuid() == 0:
        raise SystemExit("Run as the disposable PostgreSQL test account")
    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool, *args):
        subprocess.run([pg / "lib/postgresql/18/bin" / tool, *args], env=env,
                       capture_output=True, check=True, timeout=90)

    with tempfile.TemporaryDirectory(prefix="aipof-technical-session-") as directory:
        data = Path(directory) / "data"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        try:
            run("pg_ctl", "-D", data, "-l", Path(directory) / "pg.log", "-o",
                f"-k {directory} -c listen_addresses='' -c unix_socket_permissions=0700", "-w", "start")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", dir=directory) as empty_probe:
                setup = fixture_sql(Path(empty_probe.name), True)
            if not setup.endswith("ROLLBACK;"):
                raise RuntimeError("Unexpected assembly transaction boundary")
            with psycopg.connect(host=directory, dbname="postgres", autocommit=True) as connection:
                try:
                    connection.execute(setup.removesuffix("ROLLBACK;"))
                    acl = check_writer(connection, "WORKER")
                    check_writer(connection, "VERIFIER")
                finally:
                    connection.execute("ROLLBACK")
                surviving = connection.execute(
                    "SELECT count(*) FROM pg_namespace WHERE nspname IN ('company','company_private')"
                ).fetchone()
                if surviving != (0,):
                    raise RuntimeError("Technical session fixture rollback incomplete")
            print("WORKER_AND_VERIFIER_WRITER_PASS; MISSING_MEMBERSHIPS_DENIED; GRANTS_UNCHANGED")
            print("PROVISIONING_ROLE_ROOT_EXECUTE=%s SESSION_INSERT=%s" % acl)
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")
    print("ROLLBACK_AND_SHUTDOWN_VERIFIED")


if __name__ == "__main__":
    main()
