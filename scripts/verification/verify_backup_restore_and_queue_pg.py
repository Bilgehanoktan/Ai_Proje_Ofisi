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
sys.path.insert(0, str(ROOT / "verifier/src"))

from company_os.runtime.worker_daemon import AutonomousWorkerDaemon  # noqa: E402
from company_os.workflows.queue_adapter import MultiWorkTypeQueueRunner  # noqa: E402
from company_os.workflows.templates import WorkType  # noqa: E402
from independent_verifier.research_readback import confirm_receipt, current_read  # noqa: E402


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
                f"BEGIN; SELECT set_config('app.tenant_id', '{tenant_id}', true); "
                "INSERT INTO company.work_template_validations"
                "(tenant_id, work_type, template_id, template_version, validated, evidence_digest) VALUES "
                + ", ".join(values)
                + "; COMMIT;"
            )
            raw_types = psql(
                f"BEGIN; SELECT set_config('app.tenant_id', '{tenant_id}', true); "
                "SELECT json_agg(work_type ORDER BY work_type)::text "
                "FROM company.work_template_validations WHERE validated = true; COMMIT;"
            )
            persisted_types = json.loads(
                [ln.strip() for ln in raw_types.splitlines() if ln.strip().startswith("[")][-1]
            )

            # 4. Verify least-privilege aipof_research_readback Kernel DB receipt readback on restored cluster
            import base64
            import hashlib
            from uuid import uuid4
            import psycopg

            psql(
                """
                BEGIN;
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aipof_research_readback') THEN
                        CREATE ROLE aipof_research_readback LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
                    END IF;
                END $$;
                GRANT USAGE ON SCHEMA company, company_private TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, active_attempt_id, fencing_epoch) ON company.tasks TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, engine_session_id, task_id, attempt_id, fence, process_id) ON company_private.r60_engine_streams TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, engine_session_id, process_id, sequence, frame_digest, frame_bytes, state, effect_attestation_id) ON company_private.r60_tool_consumptions TO aipof_research_readback;
                GRANT SELECT (tenant_id, project_id, id, profile, payload) ON company_private.r58_attestations TO aipof_research_readback;

                DROP POLICY IF EXISTS research_readback_tasks_read ON company.tasks;
                CREATE POLICY research_readback_tasks_read ON company.tasks
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                DROP POLICY IF EXISTS research_readback_streams_read ON company_private.r60_engine_streams;
                CREATE POLICY research_readback_streams_read ON company_private.r60_engine_streams
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                DROP POLICY IF EXISTS research_readback_consumptions_read ON company_private.r60_tool_consumptions;
                CREATE POLICY research_readback_consumptions_read ON company_private.r60_tool_consumptions
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback');
                DROP POLICY IF EXISTS research_readback_attestations_read ON company_private.r58_attestations;
                CREATE POLICY research_readback_attestations_read ON company_private.r58_attestations
                    FOR SELECT TO aipof_research_readback USING (session_user = 'aipof_research_readback' AND profile = 'r60.tool-effect.v1');
                COMMIT;
                """
            )
            ident_path = restore_data / "pg_ident.conf"
            ident_txt = ident_path.read_text("utf-8")
            map_line = "aipof_local     aipof-dbtest            aipof_research_readback"
            if map_line not in ident_txt:
                ident_path.write_text(ident_txt.rstrip() + "\n" + map_line + "\n", encoding="utf-8")
            psql("SELECT pg_reload_conf();")

            stream_info = json.loads(
                psql(
                    """SELECT json_build_object(
                        'tenant_id', s.tenant_id::text,
                        'project_id', s.project_id::text,
                        'task_id', s.task_id::text,
                        'attempt_id', s.attempt_id::text,
                        'engine_session_id', s.engine_session_id::text,
                        'process_id', s.process_id::text,
                        'manifest_digest', s.manifest_digest,
                        'command_id', (SELECT id::text FROM company.commands LIMIT 1),
                        'issuer_id', (SELECT id::text FROM company.principals WHERE kind='WORKER' LIMIT 1)
                    )::text
                    FROM company_private.r60_engine_streams s
                    ORDER BY s.next_sequence DESC LIMIT 1;"""
                )
            )
            consume_id = str(uuid4())
            proof_id = str(uuid4())
            req_id = str(uuid4())
            kreq_id = str(uuid4())
            content_raw = b"def normalize_title(v):\n    return ' '.join(v.split())\n"
            content_digest = hashlib.sha256(content_raw).hexdigest()
            frame_obj = {
                "protocol": "company-tool/1",
                "request_id": req_id,
                "engine_session_id": stream_info["engine_session_id"],
                "attempt_id": stream_info["attempt_id"],
                "fencing_epoch": 1,
                "expected_revision": 1,
                "sequence": 99,
                "tool_manifest_digest": stream_info["manifest_digest"],
                "call": {
                    "tool_id": "workspace.read",
                    "arguments": {"relative_path": "task_title.py", "max_bytes": 4096},
                },
            }
            frame_bytes = (json.dumps(frame_obj, separators=(",", ":")) + "\n").encode("utf-8")
            frame_digest = hashlib.sha256(frame_bytes).hexdigest()
            att_payload = {
                "consume_id": consume_id,
                "frame_digest": frame_digest,
                "process_id": stream_info["process_id"],
                "base_head": content_digest,
                "result_head": content_digest,
                "effect_digest": content_digest,
                "outcome": "SUCCEEDED",
                "effect": {
                    "kind": "READ",
                    "head_digest": content_digest,
                    "content_base64": base64.b64encode(content_raw).decode("ascii"),
                    "content_digest": content_digest,
                    "truncated": False,
                },
            }
            att_bytes = json.dumps(att_payload, separators=(",", ":")).encode("utf-8")
            att_digest = hashlib.sha256(att_bytes).hexdigest()

            with psycopg.connect(
                host=str(restore_sock), port=55499, dbname="ai_proje_ofisi", user="aipof-dbtest"
            ) as aconn:
                with aconn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO company_private.r58_attestations
                           (tenant_id, project_id, id, issuer_id, key_id, enrollment_revision,
                            profile, raw_digest, raw_bytes, auth_tag, payload)
                           VALUES (%s, %s, %s, %s, %s, 1, 'r60.tool-effect.v1', %s, %s, %s, %s::jsonb)""",
                        (
                            stream_info["tenant_id"],
                            stream_info["project_id"],
                            proof_id,
                            stream_info["issuer_id"],
                            str(uuid4()),
                            att_digest,
                            att_bytes,
                            "d" * 64,
                            json.dumps(att_payload),
                        ),
                    )
                    cur.execute(
                        """INSERT INTO company_private.r60_tool_consumptions
                           (tenant_id, project_id, id, engine_session_id, engine_request_id,
                            kernel_request_id, sequence, process_id, frame_digest, frame_bytes,
                            state, effect_attestation_id, command_id)
                           VALUES (%s, %s, %s, %s, %s, %s, 99, %s, %s, %s, 'SUCCEEDED', %s, %s)""",
                        (
                            stream_info["tenant_id"],
                            stream_info["project_id"],
                            consume_id,
                            stream_info["engine_session_id"],
                            req_id,
                            kreq_id,
                            stream_info["process_id"],
                            frame_digest,
                            frame_bytes,
                            proof_id,
                            stream_info["command_id"],
                        ),
                    )
                aconn.commit()

            rb_conn = lambda: psycopg.connect(
                host=str(restore_sock), port=55499, dbname="ai_proje_ofisi", user="aipof_research_readback"
            )
            scope = {
                "tenant_id": stream_info["tenant_id"],
                "project_id": stream_info["project_id"],
                "task_id": stream_info["task_id"],
                "read_path": "task_title.py",
            }
            cur_read = current_read(rb_conn, scope)
            if (
                cur_read["attempt_id"] != stream_info["attempt_id"]
                or cur_read["receipt_id"] != proof_id
                or cur_read["sha256"] != content_digest
            ):
                raise RuntimeError(f"Unexpected current_read: {cur_read}")
            full_scope = {**scope, "attempt_id": stream_info["attempt_id"]}
            if not confirm_receipt(rb_conn, full_scope, proof_id, require_current=True):
                raise RuntimeError("confirm_receipt failed for valid RESEARCH receipt")
            if confirm_receipt(rb_conn, {**full_scope, "read_path": "wrong.py"}, proof_id, require_current=True):
                raise RuntimeError("confirm_receipt accepted wrong read_path")
            if confirm_receipt(rb_conn, {**full_scope, "project_id": str(uuid4())}, proof_id, require_current=True):
                raise RuntimeError("confirm_receipt accepted foreign project_id")

    print(
        json.dumps(
            {
                "scheduled_backup_used": str(latest_backup),
                "pg_verifybackup": "PASS",
                "restored_state": restored_state,
                "daemon_processed": stats.processed,
                "daemon_accepted": stats.accepted,
                "persisted_work_types": persisted_types,
                "research_kernel_receipt_readback": "PASS",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
