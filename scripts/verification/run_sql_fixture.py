"""Run a repository SQL probe against a fresh, rollback-only PostgreSQL cluster."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.database.native_bootstrap_acl_fixture import fixture_body


def synthetic_owner_setup() -> str:
    baseline = (ROOT / "evidence/disposable_bootstrap_commit.sql").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != "3e22ab435b1729c8d8dfa0665dc26b27e8a9b56c2355c765d0de19a70f5727b0":
        raise ValueError("Synthetic bootstrap fixture pin mismatch")
    marker = "-- SYNTHETIC_ROOT_SHAPE_TEST:"
    setup = baseline.decode().split(marker, 1)[1].split("\n", 1)[1].rstrip()
    role = "CREATE ROLE company_provisioning_runtime_r55 NOLOGIN NOSUPERUSER NOBYPASSRLS;"
    if setup.count(role) != 1 or not setup.endswith("COMMIT;"):
        raise ValueError("Unexpected synthetic bootstrap fixture")
    # The current provisioning login already exists and is NOINHERIT.
    setup = setup.replace(role, "").removesuffix("COMMIT;")
    before, invocation = setup.rsplit("SET SESSION AUTHORIZATION company_provisioning_runtime_r55;", 1)
    return before + "SET SESSION AUTHORIZATION company_provisioning_runtime_r55;\n SET ROLE company_bootstrap_transport_r56;" + invocation


def fixture_sql(probe: Path, bootstrap: bool) -> str:
    manifest = json.loads((ROOT / "database/assembly/assembly.json").read_text())
    if manifest["automatic_execution"] or manifest["G0"] != "OPEN":
        raise ValueError("Unexpected fixture assembly")
    parts = [
        "BEGIN;",
        "SET LOCAL statement_timeout='30s';",
        "SET LOCAL plpgsql.variable_conflict='error';",
        "CREATE ROLE company_provisioning_runtime_r55 LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;",
    ]
    for index, entry in enumerate(manifest["order"], 1):
        source = (ROOT / entry["path"]).resolve()
        if not source.is_relative_to(ROOT / "database/sources"):
            raise ValueError("SQL source outside assembly directory")
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source pin mismatch: {source.name}")
        parts.append(fixture_body(source, index))
    if bootstrap:
        parts.append(synthetic_owner_setup())
    parts.extend([probe.read_text(encoding="utf-8"), "ROLLBACK;"])
    return "\n".join(parts)


def wait_for_native_clock(execute_sql) -> None:
    query = """BEGIN;
        CREATE FUNCTION pg_temp.observe_clock() RETURNS jsonb
        AS '$libdir/r55_clock_observer','r55_cp_clock_observe_local'
        LANGUAGE C VOLATILE;
        SELECT pg_temp.observe_clock()->>'source_sync_state';
        ROLLBACK;"""
    deadline = time.monotonic() + 90
    while execute_sql(query) != "SYNC":
        if time.monotonic() >= deadline:
            raise RuntimeError("Native clock synchronization unavailable")
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--synthetic-owner", action="store_true")
    args = parser.parse_args()
    probe = (ROOT / args.probe).resolve()
    if not probe.is_relative_to(ROOT) or probe.suffix != ".sql":
        parser.error("Expected a repository SQL probe")
    if sys.platform != "linux" or os.geteuid() == 0:
        parser.error("Use the non-root Linux test account")
    sql = fixture_sql(probe, args.synthetic_owner)
    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool: str, *args: str | Path, query: str | None = None) -> str:
        result = subprocess.run(
            [pg / "lib/postgresql/18/bin" / tool, *args],
            input=query, capture_output=True, text=True, env=env, timeout=120,
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-1800:])
        return result.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="aipof-sql-fixture-") as directory:
        data = Path(directory) / "data"
        run("initdb", "-D", data, "--auth=peer", "--locale=C", "--encoding=UTF8")
        try:
            options = f"-k {directory} -c listen_addresses='' -c unix_socket_permissions=0700"
            run("pg_ctl", "-D", data, "-l", Path(directory) / "postgres.log", "-o", options, "-w", "start")
            args_psql = ("-X", "-h", directory, "-d", "postgres", "-Atq", "-v", "ON_ERROR_STOP=1", "-f", "-")
            if args.synthetic_owner:
                wait_for_native_clock(lambda query: run("psql", *args_psql, query=query))
            print(run("psql", *args_psql, query=sql))
            remaining = run("psql", *args_psql, query="SELECT count(*) FROM pg_namespace WHERE nspname IN ('company','company_private');")
            if remaining != "0":
                raise RuntimeError("Fixture rollback incomplete")
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")
    print("ROLLBACK_AND_SHUTDOWN_VERIFIED")


if __name__ == "__main__":
    main()
