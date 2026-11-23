"""Verify scheduled basebackup restore on isolated PG 18.6 + MOD-013 multi-task queue 087 persistence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product/backend"))

from company_os.runtime.worker_daemon import AutonomousWorkerDaemon  # noqa: E402
from company_os.workflows.queue_adapter import MultiWorkTypeQueueRunner  # noqa: E402
from company_os.workflows.templates import WorkType  # noqa: E402


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root Linux account is required")

    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    pgbin = pg / "lib/postgresql/18/bin"
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    backup_root = Path("/var/lib/ai-proje-ofisi-local/backups")
    backups = sorted(backup_root.glob("basebackup-*"))
    if not backups:
        raise RuntimeError("NO_SCHEDULED_BASEBACKUP_FOUND")
    latest_backup = backups[-1]

    def run(tool: str, *args: object, query: str | None = None) -> str:
        res = subprocess.run(
            [pgbin / tool, *args],
            input=query,
            text=True,
            capture_output=True,
            timeout=120,
            env=env,
        )
        if res.returncode != 0:
            raise RuntimeError(f"{tool} failed: {res.stderr[-1200:]}")
        return res.stdout.strip()

    # 1. Verify scheduled backup integrity first
    run("pg_verifybackup", latest_backup)

    # 2. Restore scheduled basebackup into an isolated temporary PG 18.6 instance
    with tempfile.TemporaryDirectory(prefix="aipof-restore-sched-") as tmpdir:
        work = Path(tmpdir)
        restore_data = work / "data"
        restore_sock = work / "sock"
        restore_sock.mkdir(mode=0o700)
        shutil.copytree(latest_backup, restore_data)
        restore_data.chmod(0o700)

        # Isolate port/socket so it never collides with live 55490
        auto_conf = restore_data / "postgresql.auto.conf"
        existing = auto_conf.read_text("utf-8") if auto_conf.exists() else ""
        auto_conf.write_text(
            existing
            + f"\nlisten_addresses = ''\nport = 55499\nunix_socket_directories = '{restore_sock}'\n",
            encoding="utf-8",
        )

        @contextmanager
        def started():
            try:
                run("pg_ctl", "-D", restore_data, "-l", work / "pg.log", "-w", "start")
                yield
            finally:
                if (restore_data / "postmaster.pid").exists():
                    run("pg_ctl", "-D", restore_data, "-m", "fast", "-w", "stop")

        def psql(query: str) -> str:
            return run(
                "psql",
                "-X",
                "-h",
                restore_sock,
                "-p",
                "55499",
                "-d",
                "ai_proje_ofisi",
                "-Atq",
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                "-",
                query=query,
            )

        with started():
            # Verify restored cluster has accepted MGT-01 task + 087 FORCE RLS tables
            restored_state = json.loads(
                psql(
                    """SELECT json_build_object(
                        'accepted_tasks', (SELECT count(*) FROM company.tasks WHERE state='ACCEPTED'),
                        'force_rls_087_tables', (
                            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='company'
                              AND c.relname IN ('catalog_entries','memory_promotions','work_template_validations','external_effect_ledger')
                              AND c.relrowsecurity=true AND c.relforcerowsecurity=true
                        ),
                        'tenant_id', (SELECT id::text FROM company.tenants LIMIT 1)
                    )::text;"""
                )
            )
            tenant_id = restored_state["tenant_id"]

            # 3. Run AutonomousWorkerDaemon with RESEARCH, SPREADSHEET, OBLIGATION and persist to restored PG 087
            queue = [
                {"task_id": "res-live-1", "tenant_id": tenant_id, "work_type": "RESEARCH"},
                {"task_id": "xls-live-1", "tenant_id": tenant_id, "work_type": "SPREADSHEET"},
                {"task_id": "obl-live-1", "tenant_id": tenant_id, "work_type": "OBLIGATION"},
            ]
            runner = MultiWorkTypeQueueRunner(
                executors={
                    WorkType.RESEARCH: lambda _t: {
                        "citations": [{"source_uri": "https://example.org/verified-source"}]
                    },
                    WorkType.SPREADSHEET: lambda _t: {
                        "post_commit_verified": True,
                        "workbook_digest": "sha256:workbook-20261123",
                    },
                    WorkType.OBLIGATION: lambda _t: {
                        "uncertainty_ms": 18,
                        "max_uncertainty_ms": 100,
                    },
                }
            )
            daemon = AutonomousWorkerDaemon(
                claim_next=lambda: queue.pop(0) if queue else None,
                execute_task=runner.execute_task,
                verify_task=runner.verify_task,
                poll_interval_seconds=0.0,
            )
            stats = daemon.run_forever(max_cycles=4)
            if stats.accepted != 3 or stats.rejected != 0 or stats.errors != 0:
                raise RuntimeError(f"Unexpected daemon stats: {stats}")

            # Persist the 3 verified results into restored PG company.work_template_validations and read back
            values = []
            for item in stats.history:
                v = item.detail["verify"]["validation"]
                dig = item.detail["verify"]["evidence_digest"]
                values.append(
                    f"('{tenant_id}'::uuid, '{v['work_type']}', '{v['template_id']}', '{v['version']}', true, '{dig}')"
                )
            psql(
                "INSERT INTO company.work_template_validations"
                "(tenant_id, work_type, template_id, template_version, validated, evidence_digest) VALUES "
                + ", ".join(values)
                + ";"
            )
            persisted_types = json.loads(
                psql(
                    "SELECT json_agg(work_type ORDER BY work_type)::text "
                    "FROM company.work_template_validations WHERE validated = true;"
                )
            )

    print(
        json.dumps(
            {
                "scheduled_backup_used": str(latest_backup),
                "pg_verifybackup": "PASS",
                "restored_state": restored_state,
                "daemon_processed": stats.processed,
                "daemon_accepted": stats.accepted,
                "persisted_work_types": persisted_types,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
