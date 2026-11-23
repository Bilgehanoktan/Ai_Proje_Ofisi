-- External provisioning inputs are synthetic and rollback-only.
\i scripts/verification/clock_policy_activation_probe.sql
DO $clock$
DECLARE
    project company.projects%ROWTYPE;
    policy company_private.r57_clock_policy_receipts%ROWTYPE;
    command_id uuid;
    observer uuid := gen_random_uuid();
    signing_key uuid := gen_random_uuid();
    epoch uuid := gen_random_uuid();
    host uuid := gen_random_uuid();
    sample uuid := gen_random_uuid();
    secret bytea := uuid_send(gen_random_uuid()) || uuid_send(gen_random_uuid());
    local_obs jsonb;
    statement jsonb;
    wire bytea;
    msg bytea;
    item bytea;
    tag bytea;
    result jsonb;
    utc timestamptz;
    tick bigint;
    phase integer;
BEGIN
    SELECT * INTO STRICT project FROM company.projects;
    SELECT * INTO STRICT policy FROM company_private.r57_clock_policy_receipts;
    SELECT id INTO STRICT command_id FROM company.commands WHERE tenant_id=project.tenant_id LIMIT 1;
    INSERT INTO company.host_registrations(tenant_id,project_id,id,revision,host_identity_digest,
        attestation_digest,state,command_id,bound_generation,binding_command_id)
    VALUES(project.tenant_id,project.id,host,1,repeat('a',64),repeat('b',64),
        'BOUND_NOT_LEASED',command_id,1,command_id);
    UPDATE company.projects SET host_registration_id=host,host_registration_revision=1,
        instance_generation=1 WHERE tenant_id=project.tenant_id AND id=project.id;
    INSERT INTO company.principals(tenant_id,id,name,kind)
    VALUES(project.tenant_id,observer,'fixture-clock-observer','AGENT');
    local_obs := company_private.r55_cp_clock_observe_local();
    INSERT INTO company.signer_enrollments(tenant_id,issuer_id,key_id,purpose,profile_id,secret_ref,
        key_fingerprint,enrollment_revision,valid_from,valid_until,approved_by,r55_project_id,r55_host_id,
        r55_host_revision,r55_host_generation,r55_host_boot_id)
    VALUES(project.tenant_id,observer,signing_key,'CLOCK_OBSERVATION','R55_CLOCK_V1_RAW_JSON','fixture-only',
        encode(sha256(secret),'hex'),1,clock_timestamp()-interval '1 minute',
        clock_timestamp()+interval '5 minutes',policy.human_id,project.id,host,1,1,
        (local_obs->>'host_boot_id')::uuid);
    FOR phase IN 1..3 LOOP
        sample := gen_random_uuid();
        local_obs := company_private.r55_cp_clock_observe_local();
        tick := (local_obs->>'boottime_after_ns')::bigint;
        utc := clock_timestamp();
        statement := jsonb_build_object('tenant_id',project.tenant_id,'project_id',project.id,
            'epoch_id',epoch,'sample_id',sample,'host_boot_id',local_obs->>'host_boot_id',
            'backend_pid',pg_backend_pid(),'transaction_id',pg_current_xact_id()::text,
            'db_login','company_clock_runtime_r55','phase','FINAL_AFTER_LOCKS',
            'current_boottime_ns',tick,'valid_until_boottime_ns',tick+1000000000,
            'utc_lower_bound',utc-interval '1 millisecond','utc_upper_bound',utc+interval '1 millisecond',
            'host_registration_id',host,'host_registration_revision',1,'host_generation',1,
            'policy_digest',policy.policy_digest);
        IF phase>=2 THEN
            statement := statement || jsonb_build_object('cut_nonce',gen_random_uuid(),'source_sequence',phase-1,
                'sampled_at',utc,'sample_boottime_ns',tick,'sample_uncertainty_ms',2,
                'frequency_error_ppm_bound',50,'sampling_error_margin_ns',100000,
                'source_sync_state',local_obs->>'source_sync_state');
        END IF;
        wire := convert_to(statement::text,'UTF8');
        msg := convert_to('R55-CP-PROOF-v1','UTF8') || decode('00','hex');
        FOREACH item IN ARRAY ARRAY[convert_to('CLOCK_OBSERVATION','UTF8'),
            convert_to(observer::text,'UTF8'),convert_to(signing_key::text,'UTF8'),
            convert_to('1','UTF8'),wire] LOOP
            msg := msg || convert_to(octet_length(item)::text||':','UTF8') || item;
        END LOOP;
        tag := company_private.r55_cp_hmac_sha256(secret,msg);
        SET SESSION AUTHORIZATION company_clock_runtime_r55;
        IF phase=1 THEN
            IF company_private.r55_cp_clock_epoch_register(observer,signing_key,1,wire,tag,secret,
                 host,1,1,policy.policy) IS DISTINCT FROM epoch THEN
                RAISE EXCEPTION 'fixture epoch mismatch';
            END IF;
        ELSE
            result := company_private.r55_cp_clock_sample_persist(observer,signing_key,1,wire,tag,secret);
            IF result->>'sample_id' IS DISTINCT FROM sample::text THEN
                RAISE EXCEPTION 'fixture sample not persisted';
            END IF;
        END IF;
        RESET SESSION AUTHORIZATION;
    END LOOP;
    result := company_private.r55_cp_clock_current_bounds(project.tenant_id,project.id);
    IF result->>'host_boot_id' IS DISTINCT FROM local_obs->>'host_boot_id' THEN
        RAISE EXCEPTION 'fixture boot mismatch';
    END IF;
END $clock$;
SELECT 'CLOCK_EPOCH_FIRST_SAMPLE_AND_CURRENT_BOUNDS_PASS';
