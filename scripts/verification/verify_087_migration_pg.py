"""Verify extensions 087 and 088 in the pinned assembly on disposable PostgreSQL."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from scripts.verification.run_sql_fixture import ROOT, fixture_sql, wait_for_native_clock

CHECK_087_SQL = """
DO $chk087$
DECLARE
    v_rls_count int;
    v_tenant uuid := '33333333-3333-4333-8333-333333333301'::uuid;
    v_sod_rejected boolean := false;
BEGIN
    SELECT count(*) INTO v_rls_count
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'company'
       AND c.relname IN (
           'catalog_entries',
           'memory_promotions',
           'work_template_validations',
           'external_effect_ledger'
       )
       AND c.relrowsecurity = true
       AND c.relforcerowsecurity = true;
    IF v_rls_count <> 4 THEN
        RAISE EXCEPTION 'Expected 4 FORCE RLS tables in 087, got %', v_rls_count;
    END IF;

    SELECT count(*) INTO v_rls_count
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'company'
       AND c.relname IN ('agent_instances', 'agent_instance_assignments')
       AND c.relrowsecurity AND c.relforcerowsecurity;
    IF v_rls_count <> 2 THEN
        RAISE EXCEPTION 'Expected 2 FORCE RLS tables in 088, got %', v_rls_count;
    END IF;

    INSERT INTO company.tenants(id, name) VALUES (v_tenant, 'Eval 087');

    -- Separation-of-duties negative check: verified_by == promoted_by must fail.
    BEGIN
        INSERT INTO company.memory_promotions(
            tenant_id, record_id, summary, evidence_digest, state, verified_by, promoted_by
        ) VALUES (
            v_tenant, 'm-bad', 'same actor', 'sha256:bad', 'PROMOTED', 'actor-1', 'actor-1'
        );
    EXCEPTION WHEN check_violation THEN
        v_sod_rejected := true;
    END;
    IF NOT v_sod_rejected THEN
        RAISE EXCEPTION 'Expected CHECK violation when verified_by == promoted_by';
    END IF;

    -- Positive check: distinct verified_by and promoted_by succeeds.
    INSERT INTO company.memory_promotions(
        tenant_id, record_id, summary, evidence_digest, state, verified_by, promoted_by
    ) VALUES (
        v_tenant, 'm-ok', 'distinct actors', 'sha256:ok', 'PROMOTED', 'verifier-1', 'approver-1'
    );
END $chk087$;
SELECT json_build_object(
    'migration_087_applied', true,
    'force_rls_tables', 4,
    'migration_088_applied', true,
    'agent_force_rls_tables', 2,
    'sod_check_enforced', true
)::text;
"""


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root Linux account is required")

    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool: str, *args: object, query: str | None = None) -> str:
        res = subprocess.run(
            [pg / "lib/postgresql/18/bin" / tool, *args],
            input=query,
            text=True,
            capture_output=True,
            timeout=120,
            env=env,
        )
        if res.returncode != 0:
            raise RuntimeError(f"{tool} failed: {res.stderr[-1200:]}")
        return res.stdout.strip()

    @contextmanager
    def started(data: Path, socket: Path):
        socket.mkdir(mode=0o700)
        opts = f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700"
        try:
            run("pg_ctl", "-D", data, "-l", socket / "pg.log", "-o", opts, "-w", "start")
            yield
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

    def sql(socket: Path, query: str) -> str:
        return run("psql", "-X", "-h", socket, "-d", "postgres", "-Atq", "-v", "ON_ERROR_STOP=1", "-f", "-", query=query)

    with tempfile.TemporaryDirectory(prefix="aipof-087-") as tmpdir:
        work = Path(tmpdir)
        probe_file = work / "check_087.sql"
        probe_file.write_text(CHECK_087_SQL, encoding="utf-8")
        full_sql = fixture_sql(probe_file, True)
        data, sock = work / "data", work / "sock"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(data, sock):
            wait_for_native_clock(lambda q: sql(sock, q))
            out = sql(sock, full_sql)

    lines = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
    print(lines[-1])


if __name__ == "__main__":
    main()
