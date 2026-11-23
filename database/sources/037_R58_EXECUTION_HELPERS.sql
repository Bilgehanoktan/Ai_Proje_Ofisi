BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r58_context(p_operation text) RETURNS company_private.request_contexts
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;perm text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id=p_operation;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=p_operation AND execution_class='COMMAND' AND approved_policy_digest IS NOT NULL AND policy_revision=x.policy_revision;
 IF x.project_id IS NULL OR company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS NOT TRUE THEN RAISE EXCEPTION 'R58_CURRENT_AUTHORITY_REQUIRED'; END IF;
 RETURN x;
END $$;
CREATE FUNCTION company_private.r58_shape(v jsonb,fields text[]) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR NOT ((v ?& fields) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_object_keys(v) k WHERE k<>ALL(fields))
 OR EXISTS(SELECT 1 FROM jsonb_each(v) z WHERE z.value='null'::jsonb) THEN RAISE EXCEPTION 'R58_EXACT_NON_NULL_FIELDS'; END IF;
END $$;
CREATE FUNCTION company_private.r58_unique_json(v json) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE item json;
BEGIN
 IF json_typeof(v)='object' THEN
  IF EXISTS(SELECT key FROM json_each(v) GROUP BY key HAVING count(*)>1) THEN RAISE EXCEPTION 'R58_DUPLICATE_JSON_KEYS'; END IF;
  FOR item IN SELECT value FROM json_each(v) LOOP PERFORM company_private.r58_unique_json(item); END LOOP;
 ELSIF json_typeof(v)='array' THEN
  FOR item IN SELECT value FROM json_array_elements(v) LOOP PERFORM company_private.r58_unique_json(item); END LOOP;
 END IF;
END $$;
CREATE FUNCTION company_private.r58_begin_command(p_key text,p_correlation uuid,p_request jsonb) RETURNS company.commands
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;d text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 IF p_key IS NULL OR p_key !~ '^[A-Za-z0-9_.:-]{16,128}$' OR p_correlation IS NULL OR jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'R58_COMMAND_BINDING'; END IF;
 d=encode(sha256(convert_to(p_request::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state IS DISTINCT FROM 'SUCCEEDED' OR c.r55_result_digest IS NULL THEN RAISE EXCEPTION 'R58_IDEMPOTENCY_CONFLICT_OR_INCOMPLETE'; END IF;
  RETURN c;
 END IF;
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,gen_random_uuid(),x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL) RETURNING * INTO c;
 RETURN c;
END $$;
CREATE FUNCTION company_private.r58_finish(p_command uuid,p_target uuid,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id;
 IF c.state='SUCCEEDED' THEN RETURN company_private.r57_replay_command(c.id); END IF;
 INSERT INTO company_private.r58_execution_receipts(tenant_id,project_id,command_id,operation,target_id,payload) VALUES(x.tenant_id,x.project_id,c.id,x.operation_id,p_target,p_result);
 RETURN company_private.r55_cp_finalize_command(c.id,p_target,0,company_private.r55_cp_event_kind(x.operation_id),p_result);
END $$;
CREATE FUNCTION company_private.r58_qualification(p_q uuid,p_subject uuid,p_binding text) RETURNS company.agent_qualifications
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;q company.agent_qualifications%ROWTYPE;h company.governance_decision_heads%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT q FROM company.agent_qualifications WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_q FOR SHARE;
 IF p_binding IS NULL OR q.subject_principal_id IS DISTINCT FROM p_subject OR q.execution_binding_digest IS DISTINCT FROM p_binding
 OR encode(sha256(convert_to(q.version_binding::text,'UTF8')),'hex') IS DISTINCT FROM p_binding
 THEN RAISE EXCEPTION 'R58_EXACT_QUALIFICATION_BINDING'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,q.valid_until);
 SELECT * INTO STRICT h FROM company.governance_decision_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND decision_kind='QUALIFICATION' AND operation='qualification.activate' AND logical_target_digest=encode(sha256(convert_to(q.id::text,'UTF8')),'hex') FOR SHARE;
 IF h.decision_state IS DISTINCT FROM 'APPROVED' OR NOT EXISTS(SELECT 1 FROM company.artifacts a JOIN company.principals p ON p.tenant_id=a.tenant_id AND p.id=(a.r54_human_decision->>'human_id')::uuid
 WHERE a.tenant_id=x.tenant_id AND a.project_id=h.decision_project_id AND a.task_id=h.decision_task_id AND a.attempt_id=h.decision_attempt_id AND a.id=h.decision_artifact_id AND a.state='AVAILABLE' AND p.kind='HUMAN'
 AND a.r54_human_decision->>'kind'='QUALIFICATION_ACTIVATE' AND a.r54_human_decision->>'qualification_id'=q.id::text AND a.r54_human_decision->>'binding_digest'=p_binding
 AND company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,'-infinity'::timestamptz,(a.r54_human_decision->>'valid_until')::timestamptz)) THEN RAISE EXCEPTION 'R58_CURRENT_HUMAN_QUALIFICATION_HEAD'; END IF;
 RETURN q;
END $$;
CREATE FUNCTION company_private.r58_attempt(p_task uuid,p_attempt uuid,p_fence bigint) RETURNS company.attempts
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;t company.tasks%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task FOR UPDATE;
 SELECT * INTO STRICT a FROM company.attempts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND id=p_attempt FOR UPDATE;
 IF t.execution_kind IS DISTINCT FROM 'ORDINARY' OR a.e0_evaluation_run_id IS NOT NULL OR t.active_attempt_id IS DISTINCT FROM a.id OR t.fencing_epoch IS DISTINCT FROM p_fence OR a.fencing_epoch IS DISTINCT FROM p_fence
 OR x.task_id IS DISTINCT FROM p_task OR x.attempt_id IS DISTINCT FROM p_attempt OR x.fencing_epoch IS DISTINCT FROM p_fence
 OR a.state NOT IN ('CLAIMED','RUNNING','PRODUCED') THEN RAISE EXCEPTION 'R58_STALE_ORDINARY_ATTEMPT'; END IF;
 PERFORM 1 FROM company_private.r58_lease_policies lp WHERE lp.tenant_id=x.tenant_id AND lp.project_id=x.project_id AND lp.revision=a.r58_policy_revision AND lp.enabled AND lp.verification_profile_digest=a.r58_verification_profile_digest AND company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,'-infinity'::timestamptz,lp.valid_until) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ATTEMPT_LEASE_POLICY_REVOKED'; END IF;
 PERFORM 1 FROM company_private.r58_verification_profiles vp WHERE vp.tenant_id=x.tenant_id AND vp.project_id=x.project_id AND vp.profile_digest=a.r58_verification_profile_digest AND vp.enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ATTEMPT_VERIFICATION_PROFILE_REVOKED'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,a.lease_expires_at);
 PERFORM company_private.r58_qualification(a.admission_qualification_id,a.worker_id,a.r58_binding_digest);
 RETURN a;
END $$;

CREATE FUNCTION company_private.r58_key_current(p_key uuid,p_fingerprint text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM 1 FROM company_private.r58_key_material WHERE key_id=p_key AND fingerprint=p_fingerprint AND purpose='EXECUTION_ATTESTATION' AND NOT revoked FOR SHARE;
 RETURN FOUND;
END $$;
CREATE FUNCTION company_private.r58_attestation(p_id uuid,p_profile text) RETURNS company_private.r58_attestations
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company_private.r58_attestations%ROWTYPE;e company.signer_enrollments%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT a FROM company_private.r58_attestations WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_id AND profile=p_profile;
 SELECT * INTO STRICT e FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=a.issuer_id AND key_id=a.key_id AND enrollment_revision=a.enrollment_revision AND purpose='TASK_VERIFICATION' FOR SHARE;
 IF e.revoked_at IS NOT NULL OR e.compromised_since IS NOT NULL OR e.profile_id IS DISTINCT FROM a.profile OR company_private.r58_key_current(a.key_id,e.key_fingerprint) IS NOT TRUE OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,e.valid_from,e.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'R58_ATTESTATION_SIGNER_NOT_CURRENT'; END IF;
 RETURN a;
END $$;
CREATE FUNCTION company_private.r58_process_current(p_process uuid) RETURNS company.process_runs
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;r company.process_runs%ROWTYPE;ch company_private.r58_controller_heads%ROWTYPE;b jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR SHARE;
 SELECT * INTO STRICT ch FROM company_private.r58_controller_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND controller_id=r.controller_id AND generation=r.controller_generation AND enabled FOR SHARE;
 b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 IF r.r55_host_boot_id IS DISTINCT FROM ch.host_boot_id OR b->>'host_boot_id' IS DISTINCT FROM ch.host_boot_id::text
 OR r.host_registration_id IS DISTINCT FROM ch.host_id OR r.host_registration_revision IS DISTINCT FROM ch.host_revision OR r.host_generation IS DISTINCT FROM ch.host_generation
 OR r.e0_evaluation_run_id IS NOT NULL OR r.kind IS DISTINCT FROM 'TASK_EXECUTION'
 OR NOT EXISTS(SELECT 1 FROM company.projects p JOIN company.host_registrations h ON h.tenant_id=p.tenant_id AND h.project_id=p.id AND h.id=p.host_registration_id AND h.revision=p.host_registration_revision AND h.bound_generation=p.instance_generation WHERE p.tenant_id=x.tenant_id AND p.id=x.project_id AND h.id=r.host_registration_id AND h.revision=r.host_registration_revision AND h.bound_generation=r.host_generation AND h.state='BOUND_NOT_LEASED')
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=ch.approved_by AND kind='HUMAN') THEN RAISE EXCEPTION 'R58_PROCESS_HOST_CONTROLLER_FENCED'; END IF;
 IF ch.controller_id=ch.approved_by OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=ch.controller_id AND kind IN ('WORKER','VERIFIER')) THEN RAISE EXCEPTION 'R58_TECHNICAL_CONTROLLER_REQUIRED'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
 RETURN r;
END $$;
CREATE FUNCTION company_private.r58_attestation_ingest(p_id uuid,p_issuer uuid,p_key_id uuid,p_revision bigint,p_profile text,p_raw bytea,p_tag bytea,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.signer_enrollments%ROWTYPE;k company_private.r58_key_material%ROWTYPE;c company.commands%ROWTYPE;j jsonb;msg bytea;part bytea;d text;
BEGIN
 x=company_private.r58_context('evidence.attestation_ingest');
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=x.principal_id AND kind IN ('WORKER','VERIFIER')) THEN RAISE EXCEPTION 'R58_TECHNICAL_SIGNER_REQUIRED'; END IF;
 IF p_id IS NULL OR p_issuer IS DISTINCT FROM x.principal_id OR p_key_id IS NULL OR p_revision IS NULL OR p_revision<0 OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 65536 OR p_tag IS NULL OR octet_length(p_tag)<>32
 OR p_profile NOT IN ('r58.workspace.v1','r58.launch-manifest.v1','r58.launch-callback.v1','r58.patch.v1','r58.verification.v1','r58.evidence.v1','r58.quiescence.v1') THEN RAISE EXCEPTION 'R58_ATTESTATION_WIRE'; END IF;
 SELECT * INTO STRICT e FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=p_issuer AND key_id=p_key_id AND enrollment_revision=p_revision AND purpose='TASK_VERIFICATION' FOR SHARE;
 SELECT * INTO STRICT k FROM company_private.r58_key_material WHERE key_id=p_key_id AND purpose='EXECUTION_ATTESTATION' AND NOT revoked FOR SHARE;
 IF e.profile_id IS DISTINCT FROM p_profile OR e.revoked_at IS NOT NULL OR e.compromised_since IS NOT NULL OR e.key_fingerprint IS DISTINCT FROM k.fingerprint
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=e.approved_by AND kind='HUMAN') OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,e.valid_from,e.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'R58_SIGNER_ENROLLMENT'; END IF;
 PERFORM company_private.r58_unique_json(convert_from(p_raw,'UTF8')::json);
 j=convert_from(p_raw,'UTF8')::jsonb;
 PERFORM company_private.r58_shape(j,ARRAY['tenant_id','project_id','receipt_id','profile','binding']);
 IF j->>'tenant_id' IS DISTINCT FROM x.tenant_id::text OR j->>'project_id' IS DISTINCT FROM x.project_id::text OR j->>'receipt_id' IS DISTINCT FROM p_id::text OR j->>'profile' IS DISTINCT FROM p_profile OR jsonb_typeof(j->'binding') IS DISTINCT FROM 'object'
 OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1) THEN RAISE EXCEPTION 'R58_ATTESTATION_SCOPE'; END IF;
 msg=convert_to('R58-EXECUTION-ATTESTATION-v1','UTF8')||decode('00','hex');
 FOREACH part IN ARRAY ARRAY[convert_to(p_issuer::text,'UTF8'),convert_to(p_key_id::text,'UTF8'),convert_to(p_revision::text,'UTF8'),convert_to(p_profile,'UTF8'),p_raw] LOOP msg=msg||convert_to(octet_length(part)::text||':','UTF8')||part; END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(k.secret,msg),p_tag) IS NOT TRUE THEN RAISE EXCEPTION 'R58_INVALID_ATTESTATION_HMAC'; END IF;
 d=encode(sha256(p_raw),'hex');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('receipt_id',p_id,'issuer',p_issuer,'key',p_key_id,'revision',p_revision,'profile',p_profile,'raw_digest',d));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 INSERT INTO company_private.r58_attestations(tenant_id,project_id,id,issuer_id,key_id,enrollment_revision,profile,raw_digest,raw_bytes,auth_tag,payload) VALUES(x.tenant_id,x.project_id,p_id,p_issuer,p_key_id,p_revision,p_profile,d,p_raw,encode(p_tag,'hex'),j->'binding');
 PERFORM company_private.r58_store_signed_artifact(p_id);
 RETURN company_private.r58_finish(c.id,p_id,jsonb_build_object('receipt_id',p_id,'raw_digest',d,'profile',p_profile));
END $$;
CREATE FUNCTION company_private.r58_store_signed_artifact(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='evidence.attestation_ingest';
 SELECT * INTO STRICT m FROM company_private.r58_attestations WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_id AND issuer_id=x.principal_id;
 IF x.task_id IS NOT NULL AND x.attempt_id IS NOT NULL THEN
  -- These are real DB-resident signed-statement bytes, not an invented file.
  INSERT INTO company.artifacts(tenant_id,project_id,task_id,attempt_id,id,storage_key,sha256,size_bytes,state)
  VALUES(x.tenant_id,x.project_id,x.task_id,x.attempt_id,m.id,gen_random_uuid(),m.raw_digest,octet_length(m.raw_bytes),'AVAILABLE');
  INSERT INTO company.verifier_receipts(tenant_id,project_id,task_id,attempt_id,id,purpose,signer_id,key_id,receipt_digest,signature) VALUES(x.tenant_id,x.project_id,x.task_id,x.attempt_id,m.id,'TASK_VERIFICATION',m.issuer_id,m.key_id,m.raw_digest,m.auth_tag);
 END IF;
END $$;
CREATE FUNCTION company_private.r58_signed_artifact_read(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;art company.artifacts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='candidate.r58.artifacts.read';
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'artifacts.read',x.task_id,false) IS NOT TRUE THEN RAISE EXCEPTION 'R58_ARTIFACT_READ_DENIED'; END IF;
 SELECT * INTO STRICT art FROM company.artifacts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=x.task_id AND attempt_id=x.attempt_id AND id=p_id AND state='AVAILABLE';
 SELECT * INTO STRICT m FROM company_private.r58_attestations WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=art.id AND raw_digest=art.sha256;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:SignedStatementArtifact');
 RETURN jsonb_build_object('artifact_id',art.id,'sha256',art.sha256,'size_bytes',art.size_bytes,'content_base64',encode(m.raw_bytes,'base64'),'kind','SIGNED_STATEMENT_ONLY','access_audit_correlation',correlation);
END $$;
ROLLBACK;
