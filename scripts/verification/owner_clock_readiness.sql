-- Read only after the shared disposable owner setup. Report no key material.
DO $check$
DECLARE
    project company.projects%ROWTYPE;
    observation jsonb;
BEGIN
    SELECT * INTO STRICT project FROM company.projects;
    observation := company_private.r55_cp_clock_observe_local();
    IF observation->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text
       OR observation->>'host_boot_id' IS NULL THEN
        RAISE EXCEPTION 'native clock observation missing process or boot binding';
    END IF;
    BEGIN
        PERFORM company_private.r55_cp_clock_current_bounds(project.tenant_id,project.id);
        RAISE EXCEPTION 'expected initial clock dependency';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'BLOCKED_TIME_DEPENDENCY' THEN RAISE; END IF;
    END;
END $check$;
SELECT json_build_object(
    'native_clock_observer','PASS',
    'initial_runtime_bounds','BLOCKED_TIME_DEPENDENCY',
    'boot_sync_state',company_private.r55_cp_clock_observe_local()->>'source_sync_state',
    'clock_policy_authorities',(SELECT count(*) FROM company_private.r57_clock_policy_authority),
    'clock_policy_consents',(SELECT count(*) FROM company_private.r57_clock_policy_consents),
    'clock_policy_receipts',(SELECT count(*) FROM company_private.r57_clock_policy_receipts),
    'clock_epoch_count',(SELECT count(*) FROM company.clock_epochs),
    'clock_sample_count',(SELECT count(*) FROM company.clock_samples),
    'bound_host_count',(SELECT count(*) FROM company.projects p JOIN company.host_registrations h
      ON h.tenant_id=p.tenant_id AND h.project_id=p.id AND h.id=p.host_registration_id
      AND h.revision=p.host_registration_revision AND h.bound_generation=p.instance_generation
      WHERE h.state='BOUND_NOT_LEASED')
);
