-- Domain regression only. Separate schema-local doubles supply context, proof
-- and command receipts. The installed domain tables/functions are left intact.
CREATE SCHEMA reconcile_probe;
CREATE TABLE reconcile_probe.process_runs AS TABLE company.process_runs WITH NO DATA;
CREATE TABLE reconcile_probe.principals AS TABLE company.principals WITH NO DATA;
CREATE TABLE reconcile_probe.commands AS TABLE company.commands WITH NO DATA;
CREATE TABLE reconcile_probe.request_contexts AS TABLE company_private.request_contexts WITH NO DATA;
CREATE TABLE reconcile_probe.r58_launch_capabilities AS TABLE company_private.r58_launch_capabilities WITH NO DATA;
CREATE TABLE reconcile_probe.r58_attestations AS TABLE company_private.r58_attestations WITH NO DATA;
CREATE TABLE reconcile_probe.r60_process_reconciliations AS TABLE company_private.r60_process_reconciliations WITH NO DATA;

CREATE TRIGGER check_process_transition BEFORE UPDATE ON reconcile_probe.process_runs
FOR EACH ROW EXECUTE FUNCTION company.r51f_process_identity();

CREATE FUNCTION reconcile_probe.r58_context(wanted text) RETURNS reconcile_probe.request_contexts
LANGUAGE sql STABLE AS $$
    SELECT * FROM reconcile_probe.request_contexts WHERE operation_id = wanted
$$;
CREATE FUNCTION reconcile_probe.r58_attestation(wanted uuid, wanted_profile text)
RETURNS reconcile_probe.r58_attestations LANGUAGE sql STABLE AS $$
    SELECT * FROM reconcile_probe.r58_attestations WHERE id = wanted AND profile = wanted_profile
$$;
CREATE FUNCTION reconcile_probe.r58_begin_command(text, uuid, jsonb)
RETURNS reconcile_probe.commands LANGUAGE sql STABLE AS $$
    SELECT * FROM reconcile_probe.commands
$$;
CREATE FUNCTION reconcile_probe.r58_finish(command_id uuid, target_id uuid, result jsonb)
RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_build_object('command_id', command_id, 'target_id', target_id, 'result', result)
$$;

-- Keep the complete installed routine, including early rejects, CAS and
-- insert/readback. Redirect only its object names to fixture-owned objects.
DO $copy$
DECLARE
    definition text;
BEGIN
    SELECT pg_get_functiondef('company_private.r60_process_reconcile(uuid,uuid,text,uuid)'::regprocedure)
      INTO STRICT definition;
    definition := replace(definition, 'company_private.', 'reconcile_probe.');
    definition := replace(definition, 'company.', 'reconcile_probe.');
    definition := replace(definition, 'reconcile_probe.r58_shape(', 'company_private.r58_shape(');
    EXECUTE definition;
END
$copy$;

DO $test$
DECLARE
    tenant uuid := gen_random_uuid();
    project uuid := gen_random_uuid();
    observer uuid := gen_random_uuid();
    worker uuid := gen_random_uuid();
    controller uuid := gen_random_uuid();
    boot uuid := gen_random_uuid();
    command_id uuid := gen_random_uuid();
    run_id uuid;
    capability uuid;
    proof uuid;
    scenario record;
    returned jsonb;
    result_row reconcile_probe.r60_process_reconciliations%ROWTYPE;
    process_row reconcile_probe.process_runs%ROWTYPE;
BEGIN
    INSERT INTO reconcile_probe.request_contexts(tenant_id,project_id,principal_id,operation_id)
    VALUES (tenant,project,observer,'process.reconcile');
    INSERT INTO reconcile_probe.principals(tenant_id,id,kind) VALUES (tenant,observer,'VERIFIER');
    INSERT INTO reconcile_probe.commands(id,state) VALUES (command_id,'RUNNING');
    FOR scenario IN SELECT * FROM (VALUES
        ('STARTING','EXITED','STOPPED',3),
        ('RUNNING','EXITED','STOPPED',3),
        ('STARTING','NOT_STARTED','STOPPED',3),
        ('STOP_REQUESTED','EXITED','STOPPED',2),
        ('UNKNOWN_LOCAL','EXITED','STOPPED',2),
        ('RUNNING','RUNNING','UNKNOWN_LOCAL',2)
    ) AS cases(start_state,outcome,end_state,end_revision)
    LOOP
        run_id := gen_random_uuid();
        capability := gen_random_uuid();
        proof := gen_random_uuid();
        INSERT INTO reconcile_probe.process_runs
            (tenant_id,project_id,id,worker_id,controller_id,controller_generation,r55_host_boot_id,state,revision)
        VALUES (tenant,project,run_id,worker,controller,1,boot,scenario.start_state,1);
        INSERT INTO reconcile_probe.r58_launch_capabilities(tenant_id,project_id,id,process_id,tuple_digest)
        VALUES (tenant,project,capability,run_id,repeat('a',64));
        INSERT INTO reconcile_probe.r58_attestations(id,profile,issuer_id,payload)
        VALUES (proof,'r60.process-observation.v1',observer,jsonb_build_object(
            'process_id',run_id,'capability_id',capability,'tuple_digest',repeat('a',64),
            'host_boot_id',boot,'controller_generation',1,'process_identity_digest',repeat('b',64),
            'cgroup_inode',123,'observer_id',observer,'outcome',scenario.outcome,'cgroup_populated',0,
            'workspace_fenced',true,'no_respawn_intent',true,'usage_zero',true
        ));

        IF scenario.start_state='RUNNING' AND scenario.outcome='EXITED' THEN
            UPDATE reconcile_probe.r58_attestations
               SET payload=jsonb_set(payload,'{cgroup_populated}','1') WHERE id=proof;
            BEGIN
                PERFORM reconcile_probe.r60_process_reconcile(run_id,proof,'synthetic-reconcile',gen_random_uuid());
                RAISE EXCEPTION 'Expected quiescence rejection';
            EXCEPTION WHEN raise_exception THEN
                IF SQLERRM <> 'R60_ACTUAL_QUIESCENCE_REQUIRED' THEN RAISE; END IF;
            END;
            IF EXISTS(SELECT FROM reconcile_probe.r60_process_reconciliations WHERE process_id=run_id)
               OR (SELECT revision FROM reconcile_probe.process_runs WHERE id=run_id) <> 1 THEN
                RAISE EXCEPTION 'Rejected observation changed state';
            END IF;
            UPDATE reconcile_probe.r58_attestations
               SET payload=jsonb_set(payload,'{cgroup_populated}','0') WHERE id=proof;
        END IF;

        returned := reconcile_probe.r60_process_reconcile(run_id,proof,'synthetic-reconcile',gen_random_uuid());
        SELECT * INTO STRICT result_row FROM reconcile_probe.r60_process_reconciliations WHERE process_id=run_id;
        SELECT * INTO STRICT process_row FROM reconcile_probe.process_runs WHERE id=run_id;
        IF (process_row.state,process_row.revision) IS DISTINCT FROM (scenario.end_state,scenario.end_revision::bigint)
           OR (result_row.attestation_id,result_row.command_id,result_row.outcome) IS DISTINCT FROM (proof,command_id,scenario.outcome)
           OR returned IS DISTINCT FROM jsonb_build_object('command_id',command_id,'target_id',result_row.id,
                'result',jsonb_build_object('process_id',run_id,'observation',scenario.outcome,
                                            'respawn_permitted',false,'release_performed',false)) THEN
            RAISE EXCEPTION 'Reconciliation result mismatch for %, %',scenario.start_state,scenario.outcome;
        END IF;
    END LOOP;
END
$test$;
SELECT 'RECONCILE_DOMAIN_BODY_WITH_SYNTHETIC_PORTS: SIX_TRANSITIONS_AND_QUIESCENCE_REJECTION_PASS';
