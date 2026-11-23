BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Assemble after B process schema + C evaluation receipt primitives.
-- Finite profile extension of the same Company Kernel envelope persistence.
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest)
VALUES('e0.process_proof_persist','e0.process_proof_persist','PROJECT','COMMAND',0,NULL);
GRANT SELECT ON company_private.bootstrap_receipts,company.process_runs TO company_receipt_functions_r55;
GRANT UPDATE(revision) ON company.process_runs TO company_receipt_functions_r55;
GRANT INSERT ON company.artifacts TO company_receipt_functions_r55;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_e0_verified_artifact(uuid,uuid,uuid,uuid,uuid,uuid,text,uuid,text) TO company_receipt_functions_r55;
CREATE POLICY r55_receipt_bootstrap ON company_private.bootstrap_receipts FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=bootstrap_receipts.tenant_id AND x.project_id=bootstrap_receipts.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_process ON company.process_runs FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=process_runs.tenant_id AND x.project_id=process_runs.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_process_lock ON company.process_runs FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=process_runs.tenant_id AND x.project_id=process_runs.project_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_process_artifact_insert ON company.artifacts FOR INSERT TO company_receipt_functions_r55 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=artifacts.tenant_id AND x.project_id=artifacts.project_id AND x.operation_id='e0.process_proof_persist' AND x.writer_generation=54));
GRANT EXECUTE ON FUNCTION company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz) TO company_receipt_functions_r55;
CREATE FUNCTION company_private.r55_cp_persist_process_proof(p_artifact uuid,p_raw jsonb,p_envelope jsonb,p_key_material bytea,p_idempotency text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; e company.evaluation_runs%ROWTYPE; pr company.process_runs%ROWTYPE; en company.signer_enrollments%ROWTYPE; b company_private.bootstrap_receipts%ROWTYPE; c company.commands%ROWTYPE;
 profile text; fields text[]; issuer uuid; task_id uuid; attempt_id uuid; rid uuid; cmd uuid; digest text; binding text; envelope_digest text; request_digest text; raw bytea; tag bytea; item text; n bigint; verified company.artifacts%ROWTYPE;
BEGIN
 IF NOT pg_has_role(session_user,'company_receipt_ingest_r55','MEMBER') THEN RAISE EXCEPTION 'TRUSTED_RECEIPT_INGEST_REQUIRED'; END IF;
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='e0.process_proof_persist';
 IF p_artifact IS NULL OR p_raw IS NULL OR jsonb_typeof(p_raw) IS DISTINCT FROM 'object' OR p_envelope IS NULL OR jsonb_typeof(p_envelope) IS DISTINCT FROM 'object'
 OR p_key_material IS NULL OR octet_length(p_key_material)<>32 OR p_idempotency IS NULL OR p_idempotency !~ '^[A-Za-z0-9_.:-]{16,128}$' OR p_correlation IS NULL THEN RAISE EXCEPTION 'INVALID_PROCESS_PROOF_INPUT'; END IF;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'e0.process_proof_persist',x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_PROCESS_PROOF_AUTHORITY'; END IF;
 profile=p_raw->>'profile';
 IF profile IS NULL OR profile NOT IN ('r55.e0-process-admission.pg-jsonb.v1','r55.e0-process-observation.pg-jsonb.v1') THEN RAISE EXCEPTION 'PROCESS_PROOF_PROFILE_NOT_ALLOWED'; END IF;
 fields=ARRAY['tenant_id','issuer_id','key_id','purpose','profile_id','enrollment_revision','receipt_id','canonical_artifact_digest','expected_binding_digest','envelope_digest','auth_tag'];
 IF NOT(p_envelope ?& fields) OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_envelope) k WHERE k<>ALL(fields)) OR NOT((p_envelope->>'tenant_id'=x.tenant_id::text
 AND p_envelope->>'issuer_id'=x.principal_id::text AND p_envelope->>'purpose'='EVALUATION' AND p_envelope->>'profile_id'=profile
 AND jsonb_typeof(p_envelope->'enrollment_revision')='number' AND p_envelope->>'enrollment_revision' ~ '^[0-9]+$' AND p_envelope->>'auth_tag' ~ '^[A-Za-z0-9_-]{43}$') IS TRUE)
 THEN RAISE EXCEPTION 'PROCESS_PROOF_ENROLLMENT_BINDING_INVALID'; END IF;
 rid=(p_envelope->>'receipt_id')::uuid;
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'PROCESS_PROOF_PROJECT_UNRESOLVED'; END IF;
 IF profile='r55.e0-process-admission.pg-jsonb.v1' THEN
  SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=(p_raw->>'evaluation_run_id')::uuid FOR SHARE;
  SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=e.e0_installation_id AND tenant_id=e.tenant_id AND project_id=e.project_id;
  issuer=b.accepted_human_id; task_id=e.evaluation_task_id; attempt_id=e.evaluation_attempt_id;
  binding=encode(sha256(convert_to(jsonb_build_array(x.tenant_id,x.project_id,e.id,e.evaluation_task_id,e.evaluation_attempt_id,p_artifact)::text,'UTF8')),'hex');
 ELSE
  SELECT * INTO STRICT pr FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=(p_raw->>'process_run_id')::uuid FOR SHARE;
  IF pr.e0_evaluation_run_id IS NULL OR pr.qualification_id IS NOT NULL THEN RAISE EXCEPTION 'E0_PROCESS_PROOF_ONLY'; END IF;
  issuer=pr.controller_id;task_id=pr.task_id;attempt_id=pr.attempt_id;
  binding=encode(sha256(convert_to(jsonb_build_array(pr.tenant_id,pr.project_id,pr.id,pr.task_id,pr.attempt_id,pr.attempt_fencing_epoch,pr.host_registration_id,pr.host_registration_revision,pr.host_generation,pr.r55_host_boot_id,pr.controller_id,pr.controller_generation,pr.manifest_digest)::text,'UTF8')),'hex');
 END IF;
 IF issuer IS NULL OR issuer IS DISTINCT FROM x.principal_id OR p_raw->>'tenant_id' IS DISTINCT FROM x.tenant_id::text OR p_raw->>'project_id' IS DISTINCT FROM x.project_id::text
 OR p_raw->>'task_id' IS DISTINCT FROM task_id::text OR p_raw->>'attempt_id' IS DISTINCT FROM attempt_id::text THEN RAISE EXCEPTION 'PROCESS_PROOF_ISSUER_OR_SCOPE_INVALID'; END IF;
 SELECT * INTO STRICT en FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=issuer AND key_id=(p_envelope->>'key_id')::uuid AND purpose='EVALUATION' AND profile_id=profile AND enrollment_revision=(p_envelope->>'enrollment_revision')::bigint FOR SHARE;
 IF en.revoked_at IS NOT NULL OR en.compromised_since IS NOT NULL OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,en.valid_from,en.valid_until) IS NOT TRUE OR en.key_fingerprint IS DISTINCT FROM encode(sha256(p_key_material),'hex')
 OR NOT EXISTS(SELECT 1 FROM company.principals hp WHERE hp.tenant_id=en.tenant_id AND hp.id=en.approved_by AND hp.kind='HUMAN') THEN RAISE EXCEPTION 'DENIED_PROCESS_PROOF_CURRENT_ENROLLMENT'; END IF;
 digest=encode(sha256(convert_to(p_raw::text,'UTF8')),'hex'); n=octet_length(convert_to(p_raw::text,'UTF8'));
 IF n>52428800 OR digest IS DISTINCT FROM p_envelope->>'canonical_artifact_digest' OR binding IS DISTINCT FROM p_envelope->>'expected_binding_digest' THEN RAISE EXCEPTION 'PROCESS_PROOF_DIGEST_BINDING_INVALID'; END IF;
 raw=convert_to('R54-EVALUATION-v1','UTF8')||decode('00','hex');
 FOREACH item IN ARRAY ARRAY[x.tenant_id::text,issuer::text,en.key_id::text,'EVALUATION',profile,en.enrollment_revision::text,rid::text,digest,binding] LOOP
  raw=raw||convert_to(octet_length(convert_to(item,'UTF8'))::text||':'||item,'UTF8');
 END LOOP;
 envelope_digest=encode(sha256(raw),'hex');tag=decode(translate(p_envelope->>'auth_tag','-_','+/')||'=','base64');
 IF envelope_digest IS DISTINCT FROM p_envelope->>'envelope_digest' OR company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(p_key_material,raw),tag) IS DISTINCT FROM true THEN RAISE EXCEPTION 'INVALID_PROCESS_PROOF_HMAC'; END IF;
 request_digest=encode(sha256(convert_to(jsonb_build_array(p_artifact,p_raw,p_envelope)::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_idempotency;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM request_digest OR c.r55_project_id IS DISTINCT FROM x.project_id OR c.r55_result_payload IS NULL THEN RAISE EXCEPTION 'CONFLICT_PROCESS_PROOF_IDEMPOTENCY'; END IF;
  RETURN company_private.r55_cp_finalize_command(c.id,c.result_ref,0,'E0ProcessProofPersisted',c.r55_result_payload);
 END IF;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'e0.process_proof_persist',x.task_id,true) IS DISTINCT FROM true OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,en.valid_from,en.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'DENIED_PROCESS_PROOF_INSERT_CUT'; END IF;
 INSERT INTO company.artifacts(tenant_id,project_id,task_id,attempt_id,id,storage_key,sha256,size_bytes,state,r55_e0_process_manifest,r55_e0_process_observation)
 VALUES(x.tenant_id,x.project_id,task_id,attempt_id,p_artifact,gen_random_uuid(),digest,n,'AVAILABLE',CASE WHEN profile='r55.e0-process-admission.pg-jsonb.v1' THEN p_raw ELSE NULL END,CASE WHEN profile='r55.e0-process-observation.pg-jsonb.v1' THEN p_raw ELSE NULL END);
 INSERT INTO company.internal_receipt_envelopes(tenant_id,issuer_id,key_id,purpose,enrollment_revision,receipt_id,profile_id,envelope_digest,expected_binding_digest,canonical_artifact_digest,auth_tag,verified_at)
 VALUES(x.tenant_id,issuer,en.key_id,'EVALUATION',en.enrollment_revision,rid,profile,envelope_digest,binding,digest,p_envelope->>'auth_tag',clock_timestamp());
 verified=company_private.r55_cp_e0_verified_artifact(x.tenant_id,x.project_id,task_id,attempt_id,p_artifact,rid,profile,issuer,binding);
 cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_idempotency,request_digest,p_correlation,'SUCCEEDED',p_artifact);
 RETURN company_private.r55_cp_finalize_command(cmd,p_artifact,0,'E0ProcessProofPersisted',jsonb_build_object('artifact_id',p_artifact,'receipt_id',rid,'profile',profile,'sha256',digest));
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'PROCESS_PROOF_CANONICAL_SOURCE_UNRESOLVED';
 WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_PROCESS_PROOF_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_PROCESS_PROOF_IDENTITY';
END $$;
ALTER FUNCTION company_private.r55_cp_persist_process_proof(uuid,jsonb,jsonb,bytea,text,uuid) OWNER TO company_receipt_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_persist_process_proof(uuid,jsonb,jsonb,bytea,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_persist_process_proof(uuid,jsonb,jsonb,bytea,text,uuid) TO company_receipt_ingest_r55;
-- Actual narrow ingest login, SecretAdapter, signer custody and OS attestation
-- producer remain uninstalled/unapproved. No signed sample is fabricated here.
ROLLBACK;
