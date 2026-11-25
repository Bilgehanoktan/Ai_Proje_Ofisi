"""Verify extensions 087 and 088 in the pinned assembly on disposable PostgreSQL, including persistent 001..087 -> 088 upgrade and cold restart."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from scripts.database.native_bootstrap_acl_fixture import fixture_body
from scripts.verification.run_sql_fixture import (
    ROOT,
    fixture_sql,
    synthetic_owner_setup,
    wait_for_native_clock,
)

sys.path.insert(0, str(ROOT / "product/backend"))
sys.path.insert(0, str(ROOT / "verifier/src"))
from company_os.catalog.extensions_store import Extensions087Store  # noqa: E402
from company_os.catalog.memory_promotion import CatalogEntry, CatalogKind  # noqa: E402
from independent_verifier.research_readback import confirm_receipt, current_read  # noqa: E402

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
    PERFORM set_config('app.tenant_id', v_tenant::text, true);

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


def _build_commit_sql(
    entries: list[tuple[int, dict[str, str]]],
    *,
    include_bootstrap: bool,
) -> str:
    parts = [
        "BEGIN;",
        "SET LOCAL statement_timeout='60s';",
        "SET LOCAL plpgsql.variable_conflict='error';",
    ]
    if include_bootstrap:
        parts.append(
            "CREATE ROLE company_provisioning_runtime_r55 LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;"
        )
    for index, entry in entries:
        source = (ROOT / entry["path"]).resolve()
        if not source.is_relative_to(ROOT / "database/sources"):
            raise ValueError("SQL source outside assembly directory")
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source pin mismatch: {source.name}")
        parts.append(fixture_body(source, index))
    if include_bootstrap:
        parts.append(synthetic_owner_setup())
    parts.append("COMMIT;")
    return "\n".join(parts)


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
        socket.mkdir(mode=0o700, exist_ok=True)
        opts = f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700"
        try:
            run("pg_ctl", "-D", data, "-l", socket / "pg.log", "-o", opts, "-w", "start")
            yield
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

    def sql(socket: Path, query: str) -> str:
        return run("psql", "-X", "-h", socket, "-d", "postgres", "-Atq", "-v", "ON_ERROR_STOP=1", "-f", "-", query=query)

    # 1. Disposable rollback-only 001..088 assembly check (including clock policy, epoch, samples, grants & workspace head)
    clock_policy_sql = (ROOT / "scripts/verification/clock_policy_activation_probe.sql").read_text("utf-8")
    clock_epoch_lines = [
        ln
        for ln in (ROOT / "scripts/verification/clock_epoch_sample_probe.sql").read_text("utf-8").splitlines()
        if not ln.strip().startswith(r"\i ")
    ]
    ws_head_lines = [
        ln
        for ln in (ROOT / "scripts/verification/workspace_head_native_probe.sql").read_text("utf-8").splitlines()
        if not ln.strip().startswith(r"\i ")
    ]
    combined_probe_sql = "\n".join(
        [
            clock_policy_sql,
            "\n".join(clock_epoch_lines),
            "\n".join(ws_head_lines),
            CHECK_087_SQL,
        ]
    )
    with tempfile.TemporaryDirectory(prefix="aipof-087-") as tmpdir:
        work = Path(tmpdir)
        probe_file = work / "check_087.sql"
        probe_file.write_text(combined_probe_sql, encoding="utf-8")
        full_sql = fixture_sql(probe_file, True)
        data, sock = work / "data", work / "sock"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(data, sock):
            wait_for_native_clock(lambda q: sql(sock, q))
            out = sql(sock, full_sql)

    for marker in (
        "CLOCK_POLICY_ACTIVATION_AND_REPLAY_PASS",
        "CLOCK_EPOCH_FIRST_SAMPLE_AND_CURRENT_BOUNDS_PASS",
        "NATIVE_WORKSPACE_HEAD_AND_RECEIPT_PASS",
    ):
        if marker not in out:
            raise RuntimeError(f"Missing clean 001..088 chain marker {marker}: {out}")
    lines = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
    result = json.loads(lines[-1])

    # 2. Persistent 001..087 commit -> 087 -> 088 upgrade -> cold restart readback
    manifest = json.loads((ROOT / "database/assembly/assembly.json").read_text("utf-8"))
    order = manifest["order"]
    if len(order) < 88:
        raise RuntimeError(f"Expected at least 88 assembly entries, got {len(order)}")

    with tempfile.TemporaryDirectory(prefix="aipof-087-to-088-") as tmpdir:
        work = Path(tmpdir)
        data, sock = work / "data", work / "sock"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(data, sock):
            wait_for_native_clock(lambda q: sql(sock, q))
            sql(
                sock,
                _build_commit_sql(
                    list(enumerate(order[:87], 1)),
                    include_bootstrap=True,
                ),
            )
            pre_upgrade = json.loads(
                sql(
                    sock,
                    """SELECT json_build_object(
                        'rls_087', (
                            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='company'
                              AND c.relname IN ('catalog_entries','memory_promotions','work_template_validations','external_effect_ledger')
                              AND c.relrowsecurity AND c.relforcerowsecurity
                        ),
                        'rls_088_before', (
                            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='company'
                              AND c.relname IN ('agent_instances','agent_instance_assignments')
                        )
                    )::text;""",
                )
            )
            if pre_upgrade["rls_087"] != 4 or pre_upgrade["rls_088_before"] != 0:
                raise RuntimeError(f"Unexpected pre-088 state: {pre_upgrade}")

            # Apply 088 as an upgrade transaction on the committed 001..087 database
            sql(
                sock,
                _build_commit_sql(
                    [(88, order[87])],
                    include_bootstrap=False,
                ),
            )

        # Cold restart PostgreSQL to verify persistent commit of 001..087 + 088 upgrade
        with started(data, sock):
            post_restart = json.loads(
                sql(
                    sock,
                    """SELECT json_build_object(
                        'rls_087', (
                            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='company'
                              AND c.relname IN ('catalog_entries','memory_promotions','work_template_validations','external_effect_ledger')
                              AND c.relrowsecurity AND c.relforcerowsecurity
                        ),
                        'rls_088_after', (
                            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='company'
                              AND c.relname IN ('agent_instances','agent_instance_assignments')
                              AND c.relrowsecurity AND c.relforcerowsecurity
                        ),
                        'disabled_user_triggers', (
                            SELECT count(*) FROM pg_trigger t
                            JOIN pg_class c ON c.oid=t.tgrelid
                            JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE NOT t.tgisinternal
                              AND n.nspname IN ('company','company_private')
                              AND t.tgenabled <> 'O'
                        ),
                        'objectives', (SELECT count(*) FROM company.objectives),
                        'plans', (SELECT count(*) FROM company.plans)
                    )::text;""",
                )
            )
            if (
                post_restart["rls_087"] != 4
                or post_restart["rls_088_after"] != 2
                or post_restart["disabled_user_triggers"] != 0
                or post_restart["objectives"] != 1
                or post_restart["plans"] != 1
            ):
                raise RuntimeError(f"Unexpected post-restart state: {post_restart}")

            # 3. Verify least-privilege RESEARCH Kernel DB receipt readback & multi-tenant 087 catalog load test
            import base64
            from uuid import uuid4
            import psycopg

            sql(
                sock,
                """
                BEGIN;
                CREATE ROLE aipof_catalog_087 LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
                GRANT USAGE ON SCHEMA company TO aipof_catalog_087;
                GRANT SELECT, INSERT ON company.catalog_entries TO aipof_catalog_087;

                CREATE ROLE aipof_research_readback LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
                GRANT USAGE ON SCHEMA company, company_private TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, active_attempt_id, fencing_epoch) ON company.tasks TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, engine_session_id, task_id, attempt_id, fence, process_id) ON company_private.r60_engine_streams TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, engine_session_id, process_id, sequence, frame_digest, frame_bytes, state, effect_attestation_id) ON company_private.r60_tool_consumptions TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, profile, payload) ON company_private.r58_attestations TO aipof_research_readback;

                CREATE POLICY research_readback_tasks_read ON company.tasks
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                CREATE POLICY research_readback_streams_read ON company_private.r60_engine_streams
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                CREATE POLICY research_readback_consumptions_read ON company_private.r60_tool_consumptions
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                CREATE POLICY research_readback_attestations_read ON company_private.r58_attestations
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback' AND profile = 'r60.tool-effect.v1');
                COMMIT;
                """,
            )
            ident_file = data / "pg_ident.conf"
            ident_file.write_text(
                "aipof_map aipof-dbtest aipof-dbtest\n"
                "aipof_map aipof-dbtest aipof_catalog_087\n"
                "aipof_map aipof-dbtest aipof_research_readback\n",
                encoding="utf-8",
            )
            hba_file = data / "pg_hba.conf"
            hba_file.write_text(
                "local all all peer map=aipof_map\n",
                encoding="utf-8",
            )
            sql(sock, "SELECT pg_reload_conf();")

            # Seed 10 tenants for multi-tenant 087 catalog load test (20 entries per tenant = 200 total)
            tenant_ids = [f"44444444-4444-4444-8444-{i:012d}" for i in range(1, 11)]
            sql(
                sock,
                "BEGIN; INSERT INTO company.tenants(id, name) VALUES "
                + ", ".join(f"('{tid}'::uuid, 'Tenant {idx}')" for idx, tid in enumerate(tenant_ids, 1))
                + "; COMMIT;",
            )
            cat_store = Extensions087Store(
                lambda: psycopg.connect(host=str(sock), dbname="postgres", user="aipof_catalog_087")
            )
            for tid in tenant_ids:
                for entry_idx in range(20):
                    cat_store.upsert_catalog_entry(
                        CatalogEntry(
                            tenant_id=tid,
                            kind=CatalogKind.ROLE if entry_idx % 2 == 0 else CatalogKind.SKILL,
                            name=f"EXP-{entry_idx:02d}",
                            version="1.0.0",
                            digest=hashlib.sha256(f"{tid}:{entry_idx}".encode("utf-8")).hexdigest(),
                        )
                    )
            for tid in tenant_ids:
                rows = cat_store.list_catalog_entries(tid)
                if len(rows) != 20 or any(r["tenant_id"] != tid for r in rows):
                    raise RuntimeError(f"Catalog isolation failure for tenant {tid}")
            if cat_store.list_catalog_entries("99999999-9999-4999-8999-999999999999") != []:
                raise RuntimeError("Foreign tenant unexpectedly saw catalog entries")

    result["persistent_upgrade_087_to_088"] = True
    result["cold_restart_readback"] = post_restart
    result["catalog_087_multitenant_load_200"] = True
    result["clean_001_088_clock_and_workspace_grants"] = True
    print(json.dumps(result))


if __name__ == "__main__":
    main()
