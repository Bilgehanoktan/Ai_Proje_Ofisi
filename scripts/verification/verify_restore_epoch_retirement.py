"""Verify post-restore clock epoch retirement, fresh epoch activation, and stale epoch rejection."""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from scripts.verification.run_sql_fixture import ROOT, fixture_sql, wait_for_native_clock


RETIRE_AND_REFRESH_SQL = """
DO $retire$
DECLARE
    v_old company.clock_epochs%ROWTYPE;
    v_sample company.clock_samples%ROWTYPE;
    v_new_epoch uuid := '22222222-2222-4222-8222-222222222201'::uuid;
    v_new_sample uuid := '22222222-2222-4222-8222-222222222202'::uuid;
    v_active_after int;
    v_bounds_rejected boolean := false;
    v_reopen_rejected boolean := false;
    v_stale_sample_rejected boolean := false;
    v_obs jsonb;
    v_fresh_bounds jsonb;
BEGIN
    SELECT * INTO STRICT v_old
      FROM company.clock_epochs
     WHERE invalidated_at IS NULL;

    SELECT * INTO STRICT v_sample
      FROM company.clock_samples
     WHERE tenant_id = v_old.tenant_id AND epoch_id = v_old.epoch_id
     ORDER BY boottime_ns DESC LIMIT 1;

    -- 1. Retire the pre-restore clock epoch.
    UPDATE company.clock_epochs
       SET invalidated_at = clock_timestamp()
     WHERE tenant_id = v_old.tenant_id AND epoch_id = v_old.epoch_id AND invalidated_at IS NULL;

    SELECT count(*) INTO v_active_after
      FROM company.clock_epochs
     WHERE tenant_id = v_old.tenant_id AND invalidated_at IS NULL;
    IF v_active_after <> 0 THEN
        RAISE EXCEPTION 'Expected 0 active epochs after retirement, got %', v_active_after;
    END IF;

    -- 2. Verify current bounds lookup rejects when no active epoch exists.
    BEGIN
        PERFORM company_private.r55_cp_clock_current_bounds(v_old.tenant_id, v_old.r55_project_id);
    EXCEPTION WHEN OTHERS THEN
        v_bounds_rejected := true;
    END;
    IF NOT v_bounds_rejected THEN
        RAISE EXCEPTION 'Expected r55_cp_clock_current_bounds to reject after epoch retirement';
    END IF;

    -- 3. Verify immutability trigger blocks re-opening an invalidated epoch.
    BEGIN
        UPDATE company.clock_epochs
           SET invalidated_at = NULL
         WHERE tenant_id = v_old.tenant_id AND epoch_id = v_old.epoch_id;
    EXCEPTION WHEN OTHERS THEN
        v_reopen_rejected := true;
    END;
    IF NOT v_reopen_rejected THEN
        RAISE EXCEPTION 'Expected immutability trigger to reject reopening invalidated epoch';
    END IF;

    -- 4. Verify stale (retired) epoch rejects new sample persistence via r55_cp_clock_sample_persist.
    BEGIN
        PERFORM company_private.r55_cp_clock_sample_persist(
            v_old.supervisor_id,
            v_sample.r55_source_key,
            v_sample.r55_source_enrollment_revision,
            '{}'::bytea,
            '\\x00'::bytea,
            '\\x00'::bytea
        );
    EXCEPTION WHEN OTHERS THEN
        v_stale_sample_rejected := true;
    END;
    IF NOT v_stale_sample_rejected THEN
        RAISE EXCEPTION 'Expected stale epoch sample persist to be rejected';
    END IF;

    -- 5. Open a fresh post-restore clock epoch and initial sample on the restored cluster.
    INSERT INTO company.clock_epochs(
        tenant_id, epoch_id, supervisor_id, host_boot_id, writer_generation,
        policy_digest, registered_at, r55_project_id, r55_host_registration_id,
        r55_host_registration_revision, r55_host_generation, r55_policy
    ) VALUES (
        v_old.tenant_id, v_new_epoch, v_old.supervisor_id, v_old.host_boot_id,
        v_old.writer_generation, v_old.policy_digest, clock_timestamp(),
        v_old.r55_project_id, v_old.r55_host_registration_id,
        v_old.r55_host_registration_revision, v_old.r55_host_generation, v_old.r55_policy
    );

    v_obs := company_private.r55_cp_clock_observe_local();
    INSERT INTO company.clock_samples(
        tenant_id, epoch_id, sample_id, sampled_at, utc_lower_bound, utc_upper_bound,
        boottime_ns, uncertainty_ms, sample_digest, r55_raw_proof_digest,
        r55_source_sequence, r55_source_enrollment_revision, r55_source_issuer,
        r55_source_key, r55_frequency_error_ppm_bound, r55_sampling_error_margin_ns
    ) VALUES (
        v_old.tenant_id, v_new_epoch, v_new_sample, clock_timestamp(),
        clock_timestamp() - interval '1 millisecond',
        clock_timestamp() + interval '1 millisecond',
        (v_obs->>'boottime_after_ns')::bigint,
        v_sample.uncertainty_ms,
        encode(sha256('post-restore-fresh-sample-1'::bytea), 'hex'),
        encode(sha256('post-restore-fresh-sample-1'::bytea), 'hex'),
        1, v_sample.r55_source_enrollment_revision, v_sample.r55_source_issuer,
        v_sample.r55_source_key, v_sample.r55_frequency_error_ppm_bound,
        v_sample.r55_sampling_error_margin_ns
    );
    PERFORM pg_sleep(0.01);
    v_obs := company_private.r55_cp_clock_observe_local();
    INSERT INTO company.clock_samples(
        tenant_id, epoch_id, sample_id, sampled_at, utc_lower_bound, utc_upper_bound,
        boottime_ns, uncertainty_ms, sample_digest, r55_raw_proof_digest,
        r55_source_sequence, r55_source_enrollment_revision, r55_source_issuer,
        r55_source_key, r55_frequency_error_ppm_bound, r55_sampling_error_margin_ns
    ) VALUES (
        v_old.tenant_id, v_new_epoch, '22222222-2222-4222-8222-222222222203'::uuid, clock_timestamp(),
        clock_timestamp() - interval '1 millisecond',
        clock_timestamp() + interval '1 millisecond',
        (v_obs->>'boottime_after_ns')::bigint,
        v_sample.uncertainty_ms,
        encode(sha256('post-restore-fresh-sample-2'::bytea), 'hex'),
        encode(sha256('post-restore-fresh-sample-2'::bytea), 'hex'),
        2, v_sample.r55_source_enrollment_revision, v_sample.r55_source_issuer,
        v_sample.r55_source_key, v_sample.r55_frequency_error_ppm_bound,
        v_sample.r55_sampling_error_margin_ns
    );

    -- 6. Confirm fresh epoch is active and has 2 fresh post-restore samples.
    IF (SELECT count(*) FROM company.clock_samples WHERE tenant_id = v_old.tenant_id AND epoch_id = v_new_epoch) <> 2 THEN
        RAISE EXCEPTION 'Expected 2 fresh samples on post-restore epoch %', v_new_epoch;
    END IF;
END $retire$;
SELECT json_build_object(
    'active_epochs_after_refresh', (SELECT count(*) FROM company.clock_epochs WHERE invalidated_at IS NULL),
    'retired_epochs_total', (SELECT count(*) FROM company.clock_epochs WHERE invalidated_at IS NOT NULL),
    'fresh_epoch_samples', (SELECT count(*) FROM company.clock_samples WHERE epoch_id = '22222222-2222-4222-8222-222222222201'::uuid),
    'bounds_rejected_after_retire', true,
    'reopen_rejected_by_trigger', true,
    'stale_epoch_sample_rejected', true,
    'fresh_epoch_activated', true
)::text;
"""


def main() -> None:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise RuntimeError("A non-root test account is required")
    pg = Path("/var/lib/ai-proje-ofisi-dbtest/binary/usr")
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": str(pg / "lib/x86_64-linux-gnu")}

    def run(tool: str, *args: object, query: str | None = None) -> str:
        result = subprocess.run(
            [pg / "lib/postgresql/18/bin" / tool, *args],
            input=query,
            text=True,
            capture_output=True,
            timeout=120,
            env=env,
        )
        if result.returncode:
            raise RuntimeError(f"{tool} failed: {result.stderr[-1200:]}")
        return result.stdout.strip()

    @contextmanager
    def started(data: Path, socket: Path):
        socket.mkdir(mode=0o700)
        options = f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700"
        try:
            run("pg_ctl", "-D", data, "-l", socket / "postgres.log", "-o", options, "-w", "start")
            yield
        finally:
            if (data / "postmaster.pid").exists():
                run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

    def sql(socket: Path, query: str) -> str:
        return run(
            "psql", "-X", "-h", socket, "-d", "postgres", "-Atq",
            "-v", "ON_ERROR_STOP=1", "-f", "-", query=query,
        )

    with tempfile.TemporaryDirectory(prefix="aipof-retire-") as directory:
        work = Path(directory)
        source, restored = work / "source", work / "restored"
        socket, recovery_socket = work / "s1", work / "s2"
        run("initdb", "-D", source, "--auth=peer", "--locale=C", "--encoding=UTF8")
        with started(source, socket):
            wait_for_native_clock(lambda query: sql(socket, query))
            setup = fixture_sql(ROOT / "scripts/verification/clock_epoch_sample_probe.sql", True)
            if not setup.endswith("\nROLLBACK;"):
                raise RuntimeError("Unexpected fixture boundary")
            sql(socket, setup.removesuffix("ROLLBACK;") + "COMMIT;")
            run(
                "pg_basebackup", "-h", socket, "-D", restored, "-X", "stream",
                "--checkpoint=fast", "--manifest-checksums=SHA256",
            )
        run("pg_verifybackup", restored)
        with started(restored, recovery_socket):
            retirement_result = json.loads(sql(recovery_socket, RETIRE_AND_REFRESH_SQL))

    output = {
        "backup_verified": True,
        "servers_stopped": True,
        **retirement_result,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
