"""Physical backup and restore of a newly created synthetic PostgreSQL cluster."""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from scripts.verification.run_sql_fixture import ROOT, fixture_sql, wait_for_native_clock


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root test account is required")
    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool, *args, query=None):
        result = subprocess.run(
            [pg / "lib/postgresql/18/bin" / tool, *args], input=query,
            text=True, capture_output=True, timeout=120, env=env,
        )
        if result.returncode:
            raise RuntimeError(f"{tool} failed: {result.stderr[-1200:]}")
        return result.stdout.strip()

    @contextmanager
    def started(data, socket):
        socket.mkdir(mode=0o700)
        options = f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700"
        try:
            run("pg_ctl", "-D", data, "-l", socket / "postgres.log", "-o", options, "-w", "start")
            yield
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

    def sql(socket, query):
        return run("psql", "-X", "-h", socket, "-d", "postgres", "-Atq",
                   "-v", "ON_ERROR_STOP=1", "-f", "-", query=query)

    tables = ("company_private.bootstrap_receipts", "company.commands", "company.audit_events",
              "company.outbox", "company.objectives", "company.plans", "company.clock_epochs",
              "company.clock_samples", "company_private.r57_clock_policy_receipts")

    def readback(socket):
        rows = {}
        for table in tables:
            query = f"""SELECT json_build_array(count(*),
                encode(sha256(convert_to(string_agg(to_jsonb(t)::text, E'\\n'
                    ORDER BY to_jsonb(t)::text COLLATE "C"), 'UTF8')), 'hex'))
                FROM {table} AS t;"""
            count, digest = json.loads(sql(socket, query))
            if count < 1 or not digest:
                raise RuntimeError(f"Missing fixture witness in {table}")
            rows[table] = (count, digest)
        return rows

    with tempfile.TemporaryDirectory(prefix="aipof-restore-") as directory:
        work = Path(directory)
        source, restored = work / "source", work / "restored"
        socket, recovery_socket = work / "s1", work / "s2"
        run("initdb", "-D", source, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(source, socket):
            wait_for_native_clock(lambda query: sql(socket, query))
            # Commit only this fixed synthetic dataset so the physical backup includes it.
            setup = fixture_sql(ROOT / "scripts/verification/clock_epoch_sample_probe.sql", True)
            if not setup.endswith("\nROLLBACK;"):
                raise RuntimeError("Unexpected fixture boundary")
            sql(socket, setup.removesuffix("ROLLBACK;") + "COMMIT;")
            before = readback(socket)
            run("pg_basebackup", "-h", socket, "-D", restored, "-X", "stream", "--checkpoint=fast",
                "--manifest-checksums=SHA256")
        run("pg_verifybackup", restored)
        with started(restored, recovery_socket):
            if readback(recovery_socket) != before:
                raise RuntimeError("Restored application rows differ")
            active_epochs = int(sql(recovery_socket,
                "SELECT count(*) FROM company.clock_epochs WHERE invalidated_at IS NULL;"))
    print(json.dumps({"backup_verified": True, "restored_table_counts":
                      {table: result[0] for table, result in before.items()},
                      "unretired_epochs_after_same_host_restore": active_epochs,
                      "servers_stopped": True}))


if __name__ == "__main__":
    main()
