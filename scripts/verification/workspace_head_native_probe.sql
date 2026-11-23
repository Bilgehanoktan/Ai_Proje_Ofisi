-- Synthetic technical session, membership, policy, signer and grant are fixture inputs.
-- Actual transport context, HMAC ingestion, workspace command and readback are exercised.
\i scripts/verification/clock_epoch_sample_probe.sql
CREATE ROLE workspace_probe_transport LOGIN NOSUPERUSER NOBYPASSRLS;
GRANT company_transport_r54 TO workspace_probe_transport;
DO $probe$
DECLARE
    project company.projects%ROWTYPE;
    worker uuid := gen_random_uuid();
    session_id uuid := gen_random_uuid();
    session_token text := gen_random_uuid()::text || gen_random_uuid()::text;
    lock_id bigint;
    owner_id uuid;
    grant_id uuid;
    proof_key uuid := gen_random_uuid();
    proof_id uuid := gen_random_uuid();
    secret bytea := uuid_send(gen_random_uuid()) || uuid_send(gen_random_uuid());
    nonce uuid;
    binding jsonb;
    raw bytea;
    msg bytea;
    part bytea;
    tag bytea;
    operation text;
    result jsonb;
BEGIN
    SELECT * INTO STRICT project FROM company.projects;
    SELECT human_id INTO STRICT owner_id FROM company_private.r57_clock_policy_authority;
    INSERT INTO company.principals VALUES (project.tenant_id,worker,'fixture worker','WORKER');
    INSERT INTO company.memberships VALUES(project.tenant_id,worker,'WORKER');
    INSERT INTO company_private.scope_lock_registry(rank,identity_key) VALUES
      (2,jsonb_build_object('kind','SESSION','tenant_id',project.tenant_id,'session_id',session_id))
      RETURNING scope_lock_registry.lock_id INTO lock_id;
    INSERT INTO company.sessions(tenant_id,id,principal_id,token_hash,expires_at)
      VALUES(project.tenant_id,session_id,worker,encode(sha256(convert_to(session_token,'UTF8')),'hex'),clock_timestamp()+interval '5 minutes');
    INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision)
      VALUES(project.tenant_id,'SESSION',session_id,session_id,0,lock_id,0);
    INSERT INTO company_private.r58_key_material(key_id,purpose,secret,fingerprint)
      VALUES(proof_key,'EXECUTION_ATTESTATION',secret,encode(sha256(secret),'hex'));
    INSERT INTO company.signer_enrollments(tenant_id,issuer_id,key_id,purpose,profile_id,secret_ref,
      key_fingerprint,enrollment_revision,valid_from,valid_until,approved_by)
      VALUES(project.tenant_id,worker,proof_key,'TASK_VERIFICATION','r58.workspace.v1','fixture-only',
        encode(sha256(secret),'hex'),1,clock_timestamp()-interval '1 minute',clock_timestamp()+interval '5 minutes',owner_id);
    binding := jsonb_build_object('workspace_id',project.workspace_id,'expected_revision',0,'previous_head','INITIAL',
      'head_digest',repeat('a',64),'host_id',project.host_registration_id,'host_revision',project.host_registration_revision,
      'host_generation',project.instance_generation,'host_boot_id',company_private.r55_cp_clock_observe_local()->>'host_boot_id',
      'supervisor_id',worker);
    raw := convert_to(jsonb_build_object('tenant_id',project.tenant_id,'project_id',project.id,'receipt_id',proof_id,
      'profile','r58.workspace.v1','binding',binding)::text,'UTF8');
    msg := convert_to('R58-EXECUTION-ATTESTATION-v1','UTF8') || decode('00','hex');
    FOREACH part IN ARRAY ARRAY[convert_to(worker::text,'UTF8'),convert_to(proof_key::text,'UTF8'),
      convert_to('1','UTF8'),convert_to('r58.workspace.v1','UTF8'),raw] LOOP
      msg := msg || convert_to(octet_length(part)::text||':','UTF8') || part;
    END LOOP;
    tag := company_private.r55_cp_hmac_sha256(secret,msg);
    FOREACH operation IN ARRAY ARRAY['evidence.attestation_ingest','workspace.current_head'] LOOP
      UPDATE company_private.operation_permissions SET approved_policy_digest=repeat('b',64),policy_revision=1
        WHERE operation_id=operation;
      INSERT INTO company.project_grants(tenant_id,project_id,principal_id,permission,revision,valid_from,valid_until,
        granted_by,grant_id,base_permission)
        SELECT project.tenant_id,project.id,worker,op.permission,1,clock_timestamp()-interval '1 minute',
          clock_timestamp()+interval '5 minutes',owner_id,gen_random_uuid(),op.permission
        FROM company_private.operation_permissions op WHERE op.operation_id=operation
        RETURNING project_grants.grant_id INTO STRICT grant_id;
      SET SESSION AUTHORIZATION workspace_probe_transport;
      nonce := company_private.r54_context_enter(session_token,operation,project.id,'PROJECT',project.id,NULL,NULL,NULL,grant_id);
      IF operation='evidence.attestation_ingest' THEN
        result := company_private.r58_attestation_ingest(proof_id,worker,proof_key,1,'r58.workspace.v1',raw,tag,
          'fixture.workspace.proof',gen_random_uuid());
      ELSE
        result := company_private.r58_workspace_current_head(proof_id,'fixture.workspace.head',gen_random_uuid());
      END IF;
      PERFORM company_private.r54_context_exit(nonce);
      RESET SESSION AUTHORIZATION;
    END LOOP;
    IF NOT EXISTS(SELECT FROM company_private.r58_workspace_heads h WHERE h.tenant_id=project.tenant_id AND
      h.project_id=project.id AND h.revision=1 AND h.head_digest=binding->>'head_digest' AND h.attestation_id=proof_id)
      OR NOT EXISTS(SELECT FROM company.commands c WHERE c.operation='workspace.current_head' AND c.state='SUCCEEDED'
        AND c.principal_id=worker AND c.r55_audit_id IS NOT NULL AND c.r55_event_sequence IS NOT NULL)
    THEN RAISE EXCEPTION 'workspace receipt mismatch'; END IF;
END $probe$;
SELECT 'NATIVE_WORKSPACE_HEAD_AND_RECEIPT_PASS';
