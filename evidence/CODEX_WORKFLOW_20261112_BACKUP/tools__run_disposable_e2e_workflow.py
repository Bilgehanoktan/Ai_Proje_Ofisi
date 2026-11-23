"""Run the disposable native E2E workflow trial on the isolated Linux test cluster.

Follows the exact same precheck and cleanup guarantees as run_disposable_bootstrap_commit.py:
- Bounded resources, finite timeout, private data/socket, no-network, non-root profile (aipof-dbtest).
- Starts PostgreSQL as a background systemd transient service (aipof-pg-e2e.service)
- Verifies 0 existing company% schemas and 0 company% roles before applying disposable_bootstrap_commit.sql.
- Executes disposable_e2e_workflow_trial.py.
- Drops only trial schemas/roles, stops PostgreSQL, and unmounts private storage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SQL_PATH = ROOT / "evidence" / "disposable_bootstrap_commit.sql"
TRIAL_SCRIPT = ROOT / "tools" / "disposable_e2e_workflow_trial.py"
EVIDENCE_OUT = ROOT / "evidence" / "E2E_WORKFLOW_TRIAL_20261108.json"
SOCKET_DIR = "/var/lib/ai-proje-ofisi-dbtest/storage/socket"
DB_PORT = "55439"
PG_BIN = "/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/postgresql/18/bin"
PYTHON_BIN = "/mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python"


EXACT_19_BOOTSTRAP_ROLES = [
    "company_atomic_functions_r55",
    "company_attestation_functions_r58",
    "company_bootstrap_functions_r56",
    "company_bootstrap_transport_r56",
    "company_clock_policy_owner_r57",
    "company_clock_policy_transport_r57",
    "company_clock_runtime_r55",
    "company_context_owner",
    "company_e0_process_functions_r55",
    "company_event_functions_r54",
    "company_execution_functions_r58",
    "company_first_run_functions_r53",
    "company_provisioning_runtime_r55",
    "company_readback_functions_r54",
    "company_receipt_functions_r55",
    "company_receipt_ingest_r55",
    "company_revoke_functions_r53",
    "company_transport_r53",
    "company_transport_r54",
]


def run(cmd: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def run_dbtest(args: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    base = [
        "systemd-run",
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        "--uid=aipof-dbtest",
        "--gid=aipof-dbtest",
        "-p",
        "PrivateNetwork=yes",
        "-p",
        "NoNewPrivileges=yes",
        "-p",
        "MemoryMax=512M",
        "-p",
        "TasksMax=64",
        "-p",
        "RuntimeMaxSec=180",
        "-p",
        "ReadWritePaths=/var/lib/ai-proje-ofisi-dbtest/storage",
        "-p",
        "Environment=LD_LIBRARY_PATH=/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/x86_64-linux-gnu",
        "--",
    ]
    return run(base + args, timeout=timeout, check=check)


def psql_scalar(query: str) -> str:
    proc = run_dbtest(
        [
            f"{PG_BIN}/psql",
            "-h",
            SOCKET_DIR,
            "-p",
            DB_PORT,
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-Atqc",
            query,
        ]
    )
    return proc.stdout.strip()


def main() -> int:
    # Resolve source/port incompatibilities before mount, DB setup or credentials.
    from tools.workflow_preflight import check_workflow
    preflight = check_workflow(TRIAL_SCRIPT)
    if preflight['status'] == 'BLOCKED' or preflight['runtime_blockers']:
        print(json.dumps({'status': 'BLOCKED_BEFORE_ENVIRONMENT_SETUP',
                          'preflight': preflight}, ensure_ascii=False, indent=2))
        return 2
    mounted = run(["mountpoint", "-q", "/var/lib/ai-proje-ofisi-dbtest/storage"], check=False).returncode == 0
    if not mounted:
        run(
            [
                "systemd-mount",
                "--collect",
                "--no-ask-password",
                "--type=ext4",
                "--options=nosuid,nodev,noexec",
                "/var/lib/ai-proje-ofisi-dbtest/storage-1g.ext4",
                "/var/lib/ai-proje-ofisi-dbtest/storage",
            ]
        )
    run(["chown", "aipof-dbtest:aipof-dbtest", "/var/lib/ai-proje-ofisi-dbtest/storage"])
    run(["chmod", "700", "/var/lib/ai-proje-ofisi-dbtest/storage"])

    # Ensure any old transient unit is stopped and reset
    run(["systemctl", "stop", "aipof-pg-e2e.service"], check=False)
    run(["systemctl", "reset-failed", "aipof-pg-e2e.service"], check=False)

    # Start PostgreSQL as a bounded background systemd transient unit
    start_cmd = [
        "systemd-run",
        "--unit=aipof-pg-e2e",
        "--uid=aipof-dbtest",
        "--gid=aipof-dbtest",
        "-p",
        "PrivateNetwork=yes",
        "-p",
        "NoNewPrivileges=yes",
        "-p",
        "MemoryMax=512M",
        "-p",
        "TasksMax=64",
        "-p",
        "RuntimeMaxSec=300",
        "-p",
        "ReadWritePaths=/var/lib/ai-proje-ofisi-dbtest/storage",
        "-p",
        "Environment=LD_LIBRARY_PATH=/var/lib/ai-proje-ofisi-dbtest/binary/usr/lib/x86_64-linux-gnu",
        "--",
        f"{PG_BIN}/postgres",
        "-D",
        "/var/lib/ai-proje-ofisi-dbtest/storage/data",
        "-k",
        SOCKET_DIR,
        "-p",
        DB_PORT,
    ]
    run(start_cmd)

    # Wait for postgres to be ready
    ready = False
    for _ in range(30):
        time.sleep(0.5)
        probe = run_dbtest(
            [
                f"{PG_BIN}/pg_isready",
                "-h",
                SOCKET_DIR,
                "-p",
                DB_PORT,
            ],
            check=False,
        )
        if probe.returncode == 0:
            ready = True
            break

    if not ready:
        run(["systemctl", "stop", "aipof-pg-e2e.service"], check=False)
        raise RuntimeError("POSTGRES_FAILED_TO_START_WITHIN_DEADLINE")

    # Native clock preflight: Wait until the Linux kernel clock reaches SYNC state
    # (adjtimex esterror/maxerror stabilize), otherwise r56_bootstrap_consume rejects with
    # ROOT_TRUSTED_LOCAL_OBSERVATION_REQUIRED.
    clock_synced = False
    for _ in range(15):
        probe_res = run_dbtest(
            [
                f"{PG_BIN}/psql",
                "-h",
                SOCKET_DIR,
                "-p",
                DB_PORT,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atqc",
                "BEGIN; CREATE FUNCTION public.disposable_clock_probe() RETURNS jsonb AS 'r55_clock_observer','r55_cp_clock_observe_local' LANGUAGE C VOLATILE; SELECT public.disposable_clock_probe()->>'source_sync_state'; ROLLBACK;",
            ],
            check=False,
        )
        if probe_res.returncode == 0 and probe_res.stdout.strip() == "SYNC":
            clock_synced = True
            break
        time.sleep(1.0)

    if not clock_synced:
        run(["systemctl", "stop", "aipof-pg-e2e.service"], check=False)
        raise RuntimeError("CLOCK_NOT_SYNCED_NO_INSTALLATION_WRITES")

    cleanup_report: dict[str, str] = {}
    bootstrap_applied = False
    trial_data = {}
    try:
        pre_schemas = psql_scalar(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'company%';"
        )
        pre_roles = psql_scalar(
            "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'company_%';"
        )
        if pre_schemas != "0" or pre_roles != "0":
            raise RuntimeError(f"PRECHECK_NOT_CLEAN schemas={pre_schemas} roles={pre_roles}")

        # Apply disposable_bootstrap_commit.sql
        run_dbtest(
            [
                f"{PG_BIN}/psql",
                "-h",
                SOCKET_DIR,
                "-p",
                DB_PORT,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-q",
                "-f",
                str(SQL_PATH),
            ],
            timeout=120,
        )
        bootstrap_applied = True

        # Execute the full E2E workflow + negative test suite
        trial_proc = run_dbtest(
            [PYTHON_BIN, "-B", str(TRIAL_SCRIPT)],
            timeout=180,
        )
        trial_data = json.loads(trial_proc.stdout)
        trial_data["precheck"] = {"schemas": pre_schemas, "roles": pre_roles}
        trial_data["bootstrap_sql_sha256"] = hashlib.sha256(SQL_PATH.read_bytes()).hexdigest()
        trial_data["trial_script_sha256"] = hashlib.sha256(TRIAL_SCRIPT.read_bytes()).hexdigest()
    finally:
        if bootstrap_applied:
            role_drop_lines = "\n".join(
                f"DROP OWNED BY {r} CASCADE;\nDROP ROLE IF EXISTS {r};"
                for r in EXACT_19_BOOTSTRAP_ROLES
            )
            cleanup_sql = f"""
            DROP SCHEMA IF EXISTS company_private CASCADE;
            DROP SCHEMA IF EXISTS company CASCADE;
            {role_drop_lines}
            """
            run_dbtest(
                [
                    f"{PG_BIN}/psql",
                    "-h",
                    SOCKET_DIR,
                    "-p",
                    DB_PORT,
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-q",
                    "-c",
                    cleanup_sql,
                ],
                check=False,
            )
        cleanup_report["schemas_after_cleanup"] = psql_scalar(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'company%';"
        )
        cleanup_report["roles_after_cleanup"] = psql_scalar(
            "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'company_%';"
        )

        # Stop PostgreSQL transient unit
        run(["systemctl", "stop", "aipof-pg-e2e.service"], check=False)

        # Unmount storage
        run(["systemd-mount", "--umount", "/var/lib/ai-proje-ofisi-dbtest/storage"], check=False)
        cleanup_report["mounted_after_stop"] = (
            "no"
            if run(["mountpoint", "-q", "/var/lib/ai-proje-ofisi-dbtest/storage"], check=False).returncode != 0
            else "yes"
        )

    trial_data["cleanup"] = cleanup_report
    EVIDENCE_OUT.write_text(json.dumps(trial_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(trial_data, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
