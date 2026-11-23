-- Isolated --synthetic-owner fixture. The repeated x is its public test vector.
DO $probe$
DECLARE
    root_row company_private.r55_setup_root_enrollments%ROWTYPE;
    control company_private.installation_bootstrap_control%ROWTYPE;
    consent uuid := gen_random_uuid();
    test_key bytea := convert_to(repeat('x', 32), 'UTF8');
    statement jsonb;
    wire bytea;
    message bytea;
    item bytea;
    tag bytea;
    result jsonb;
BEGIN
    SELECT * INTO STRICT root_row FROM company_private.r55_setup_root_enrollments;
    SELECT * INTO STRICT control FROM company_private.installation_bootstrap_control;
    INSERT INTO company_private.r57_clock_policy_authority
        (installation_id, tenant_id, human_id)
    VALUES (control.installation_id, control.expected_tenant_id, control.expected_human_id);
    INSERT INTO company_private.r58_key_material (key_id,purpose,secret,fingerprint) VALUES (root_row.key_id,'CLOCK_POLICY',test_key,encode(sha256(test_key),'hex'));
    INSERT INTO company_private.operation_permissions (operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES ('clock.policy.activate','clock.policy.activate','SPECIAL','COMMAND',0,NULL) ON CONFLICT (operation_id) DO NOTHING;
    statement := jsonb_build_object(
        'consent_id', consent, 'installation_id', control.installation_id,
        'action', 'ACTIVATE', 'expected_revision', 0,
        'policy', jsonb_build_object(
            'bounded_handoff_duration_ms',1000,'max_uncertainty_ms',1000,
            'max_sample_age_ms',30000,'max_clock_jump_ms',1000,
            'first_alert_ms',1000,'owner_ack_ms',2000,'manual_reconcile_ms',3000,
            'poll_ms',500,'max_drift_ms',100));
    INSERT INTO company_private.r57_clock_policy_consents
        (consent_id,installation_id,root_generation,action,expected_revision,
         approved_statement_digest,human_consent_evidence_digest,valid_from,valid_until)
    VALUES (consent,control.installation_id,control.generation,'ACTIVATE',0,
            encode(sha256(convert_to(statement::text,'UTF8')),'hex'),
            encode(sha256(convert_to('synthetic test only','UTF8')),'hex'),
            clock_timestamp()-interval '1 minute',clock_timestamp()+interval '1 minute');
    wire := convert_to(jsonb_build_object('statement',statement,'backend_pid',pg_backend_pid(),
        'transaction_id',pg_current_xact_id()::text,'db_login','company_clock_policy_transport_r57')::text,'UTF8');
    message := convert_to('R57-CLOCK-POLICY-v1','UTF8') || decode('00','hex');
    FOREACH item IN ARRAY ARRAY[convert_to(consent::text,'UTF8'),convert_to(root_row.issuer_id::text,'UTF8'),
        convert_to(root_row.key_id::text,'UTF8'),convert_to(root_row.enrollment_revision::text,'UTF8'),wire] LOOP
        message := message || convert_to(octet_length(item)::text || ':','UTF8') || item;
    END LOOP;
    tag := company_private.r55_cp_hmac_sha256(test_key,message);
    SET SESSION AUTHORIZATION company_clock_policy_transport_r57;
    result := company_private.r58_clock_policy_write(consent,wire,tag,root_row.key_id);
    IF result->>'outcome' IS DISTINCT FROM 'ACTIVATE' THEN RAISE EXCEPTION 'missing activation'; END IF;
    result := company_private.r58_clock_policy_write(consent,wire,tag,root_row.key_id);
    IF result->>'outcome' IS DISTINCT FROM 'REPLAY_NO_NEW_REVISION' THEN RAISE EXCEPTION 'missing replay'; END IF;
    RESET SESSION AUTHORIZATION;
    IF (SELECT count(*) FROM company_private.r57_clock_policy_receipts) <> 1 THEN
        RAISE EXCEPTION 'receipt count mismatch';
    END IF;
END $probe$;
SELECT 'CLOCK_POLICY_ACTIVATION_AND_REPLAY_PASS';
