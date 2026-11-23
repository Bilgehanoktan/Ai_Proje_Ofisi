BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Requires A/r55_cp_hmac_sha256(bytea,bytea). No pgcrypto extension assumed.
CREATE ROLE company_receipt_ingest_r55 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE ROLE company_receipt_functions_r55 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest)
VALUES('e0.evaluation_envelope_persist','e0.evaluation_envelope_persist','PROJECT','COMMAND',0,NULL);
GRANT USAGE ON SCHEMA company,company_private TO company_receipt_functions_r55;
GRANT SELECT ON company_private.request_contexts,company_private.operation_permissions,company.evaluation_runs,company.evidence,company.verification_runs,company.artifacts,company.principals,company.signer_enrollments TO company_receipt_functions_r55;
GRANT SELECT,INSERT ON company.commands,company.verifier_receipts,company.internal_receipt_envelopes TO company_receipt_functions_r55;
-- Row-lock privilege with UPDATE USING exact scope / WITH CHECK(false):
-- SELECT FOR SHARE/UPDATE is permitted; actual UPDATE remains prohibited.
GRANT UPDATE(enrollment_revision) ON company.signer_enrollments TO company_receipt_functions_r55;
GRANT UPDATE(state) ON company.evaluation_runs TO company_receipt_functions_r55;
GRANT UPDATE(artifact_id) ON company.evidence TO company_receipt_functions_r55;
GRANT UPDATE(profile_version) ON company.verification_runs TO company_receipt_functions_r55;
GRANT UPDATE(state) ON company.artifacts TO company_receipt_functions_r55;
GRANT SELECT,UPDATE(revision) ON company.projects TO company_receipt_functions_r55;
GRANT EXECUTE ON FUNCTION company_private.r54_schema_check(jsonb,jsonb) TO company_receipt_functions_r55;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean),company_private.r55_cp_hmac_sha256(bytea,bytea),company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) TO company_receipt_functions_r55;
CREATE POLICY r55_receipt_context ON company_private.request_contexts FOR SELECT TO company_receipt_functions_r55 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r55_receipt_registry ON company_private.operation_permissions FOR SELECT TO company_receipt_functions_r55 USING(true);
CREATE POLICY r55_receipt_project ON company.projects FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=projects.tenant_id AND x.project_id=projects.id AND x.writer_generation=54));
CREATE POLICY r55_receipt_principals ON company.principals FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=principals.tenant_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_enrollments ON company.signer_enrollments FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=signer_enrollments.tenant_id AND x.principal_id=signer_enrollments.issuer_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_commands ON company.commands TO company_receipt_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND x.writer_generation=54));
-- Per-table scoped SELECT policies avoid treating table grants as RLS acceptance.
CREATE POLICY r55_receipt_evaluations ON company.evaluation_runs FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=evaluation_runs.tenant_id AND x.project_id=evaluation_runs.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_evidence ON company.evidence FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=evidence.tenant_id AND x.project_id=evidence.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_verification ON company.verification_runs FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=verification_runs.tenant_id AND x.project_id=verification_runs.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_artifacts ON company.artifacts FOR SELECT TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=artifacts.tenant_id AND x.project_id=artifacts.project_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_project_lock ON company.projects FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=projects.tenant_id AND x.project_id=projects.id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_enrollment_lock ON company.signer_enrollments FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=signer_enrollments.tenant_id AND x.principal_id=signer_enrollments.issuer_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_evaluation_lock ON company.evaluation_runs FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=evaluation_runs.tenant_id AND x.project_id=evaluation_runs.project_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_evidence_lock ON company.evidence FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=evidence.tenant_id AND x.project_id=evidence.project_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_verification_lock ON company.verification_runs FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=verification_runs.tenant_id AND x.project_id=verification_runs.project_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_artifact_lock ON company.artifacts FOR UPDATE TO company_receipt_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=artifacts.tenant_id AND x.project_id=artifacts.project_id AND x.writer_generation=54)) WITH CHECK(false);
CREATE POLICY r55_receipt_envelope ON company.internal_receipt_envelopes TO company_receipt_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=internal_receipt_envelopes.tenant_id AND x.principal_id=internal_receipt_envelopes.issuer_id AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=internal_receipt_envelopes.tenant_id AND x.principal_id=internal_receipt_envelopes.issuer_id AND x.writer_generation=54));
CREATE POLICY r55_receipt_verifier ON company.verifier_receipts TO company_receipt_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=verifier_receipts.tenant_id AND x.project_id=verifier_receipts.project_id AND x.principal_id=verifier_receipts.signer_id AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=verifier_receipts.tenant_id AND x.project_id=verifier_receipts.project_id AND x.principal_id=verifier_receipts.signer_id AND x.writer_generation=54));
GRANT EXECUTE ON FUNCTION company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz) TO company_receipt_functions_r55;
CREATE FUNCTION company_private.r55_cp_tag_equal(a bytea,b bytea) RETURNS boolean LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE i integer; difference integer=0;
BEGIN
 IF a IS NULL OR b IS NULL OR octet_length(a)<>32 OR octet_length(b)<>32 THEN RETURN false; END IF;
 FOR i IN 0..31 LOOP difference=difference | (get_byte(a,i) # get_byte(b,i)); END LOOP;
 RETURN difference=0;
END $$;
REVOKE ALL ON FUNCTION company_private.r55_cp_tag_equal(bytea,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_tag_equal(bytea,bytea) TO company_receipt_functions_r55;

CREATE FUNCTION company_private.r55_cp_persist_evaluation_envelope(p_evaluation uuid,p_binding jsonb,p_envelope jsonb,p_key_material bytea,p_idempotency text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; e company.evaluation_runs%ROWTYPE; ev company.evidence%ROWTYPE; v company.verification_runs%ROWTYPE; a company.artifacts%ROWTYPE; en company.signer_enrollments%ROWTYPE; old company.internal_receipt_envelopes%ROWTYPE; cmd company.commands%ROWTYPE;
 raw bytea; tag bytea; item text; binding_digest text; artifact_digest text; envelope_digest text; request_digest text; rid uuid; cid uuid; revision bigint; fields text[]; now_at timestamptz;
BEGIN
 IF NOT pg_has_role(session_user,'company_receipt_ingest_r55','MEMBER') THEN RAISE EXCEPTION 'TRUSTED_RECEIPT_INGEST_REQUIRED'; END IF;
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='e0.evaluation_envelope_persist';
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'e0.evaluation_envelope_persist',x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_RECEIPT_AUTHORITY'; END IF;
 fields=ARRAY['tenant_id','issuer_id','key_id','purpose','profile_id','enrollment_revision','receipt_id','canonical_artifact_digest','expected_binding_digest','envelope_digest','auth_tag'];
 IF p_binding IS NULL OR jsonb_typeof(p_binding) IS DISTINCT FROM 'object' OR p_envelope IS NULL OR jsonb_typeof(p_envelope) IS DISTINCT FROM 'object' OR NOT(p_envelope ?& fields) OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_envelope) k WHERE k<>ALL(fields))
 OR p_key_material IS NULL OR octet_length(p_key_material)<>32 OR p_idempotency IS NULL OR p_idempotency !~ '^[A-Za-z0-9_.:-]{16,128}$' OR p_correlation IS NULL THEN RAISE EXCEPTION 'INVALID_RECEIPT_INPUT'; END IF;
 IF NOT ((p_envelope->>'tenant_id'=x.tenant_id::text AND p_envelope->>'issuer_id'=x.principal_id::text AND p_envelope->>'purpose'='EVALUATION' AND p_envelope->>'profile_id'='r54.evaluation-report.pg-jsonb.v1'
 AND jsonb_typeof(p_envelope->'enrollment_revision')='number' AND p_envelope->>'enrollment_revision' ~ '^[0-9]+$' AND p_envelope->>'auth_tag' ~ '^[A-Za-z0-9_-]{43}$') IS TRUE) THEN RAISE EXCEPTION 'WRONG_ENROLLMENT_BINDING'; END IF;
 PERFORM company_private.r54_schema_check(p_binding,'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"schema_version":{"const":"r53.execution-binding.v1"},"subject_principal_id":{"type":"string","format":"uuid"},"role_definition":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"agent_profile":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"model":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"engine":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"tools":{"type":"array","items":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"minItems":1,"uniqueItems":true},"suite":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"policy":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"resource_scope":{"type":"object","properties":{"tenant_id":{"type":"string","format":"uuid"},"project_id":{"type":"string","format":"uuid"},"workspace_id":{"type":"string","format":"uuid"}},"required":["tenant_id","project_id","workspace_id"],"additionalProperties":false},"independent_evidence":{"type":"object","properties":{"task_id":{"type":"string","format":"uuid"},"attempt_id":{"type":"string","format":"uuid"},"evidence_id":{"type":"string","format":"uuid"},"verification_run_id":{"type":"string","format":"uuid"},"producer_id":{"type":"string","format":"uuid"},"verifier_id":{"type":"string","format":"uuid"},"artifact_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["task_id","attempt_id","evidence_id","verification_run_id","producer_id","verifier_id","artifact_sha256"],"additionalProperties":false},"source_revision":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["schema_version","subject_principal_id","role_definition","agent_profile","model","engine","tools","suite","policy","resource_scope","independent_evidence","source_revision"],"additionalProperties":false}'::jsonb);
 revision=(p_envelope->>'enrollment_revision')::bigint; rid=(p_envelope->>'receipt_id')::uuid;
 -- Domain project row precedes enrollment locks, command and event-head locks.
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_PROJECT_UNRESOLVED'; END IF;
 -- Lock enrollment through commit so revoke/rotation cannot race verified INSERT.
 SELECT * INTO STRICT en FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=x.principal_id AND key_id=(p_envelope->>'key_id')::uuid AND purpose='EVALUATION' AND enrollment_revision=revision AND profile_id='r54.evaluation-report.pg-jsonb.v1' FOR SHARE;
 now_at=clock_timestamp();
 IF en.revoked_at IS NOT NULL OR en.compromised_since IS NOT NULL OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,en.valid_from,en.valid_until) IS NOT TRUE
 OR en.key_fingerprint IS DISTINCT FROM encode(sha256(p_key_material),'hex') OR NOT EXISTS(SELECT 1 FROM company.principals hp WHERE hp.tenant_id=en.tenant_id AND hp.id=en.approved_by AND hp.kind='HUMAN') THEN RAISE EXCEPTION 'DENIED_CURRENT_SIGNER_ENROLLMENT'; END IF;
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR SHARE;
 SELECT * INTO STRICT ev FROM company.evidence WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND task_id=e.evaluation_task_id AND attempt_id=e.evaluation_attempt_id AND id=(p_binding#>>'{independent_evidence,evidence_id}')::uuid FOR SHARE;
 SELECT * INTO STRICT v FROM company.verification_runs WHERE tenant_id=ev.tenant_id AND project_id=ev.project_id AND task_id=ev.task_id AND attempt_id=ev.attempt_id AND id=ev.verification_run_id FOR SHARE;
 SELECT * INTO STRICT a FROM company.artifacts WHERE tenant_id=ev.tenant_id AND project_id=ev.project_id AND task_id=ev.task_id AND attempt_id=ev.attempt_id AND id=ev.artifact_id FOR SHARE;
 IF NOT((v.producer_id=e.subject_principal_id AND v.verifier_id=x.principal_id AND v.producer_id<>v.verifier_id AND a.state='AVAILABLE' AND a.r54_evaluation_report IS NOT NULL AND a.r54_evaluation_report->>'receipt_id'=rid::text AND ev.command_receipt IS NOT NULL) IS TRUE) THEN RAISE EXCEPTION 'DENIED_CANONICAL_REPORT_BINDING'; END IF;
 artifact_digest=encode(sha256(convert_to(a.r54_evaluation_report::text,'UTF8')),'hex');
 binding_digest=encode(sha256(convert_to(p_binding::text,'UTF8')),'hex');
 IF artifact_digest IS DISTINCT FROM a.sha256 OR artifact_digest IS DISTINCT FROM p_envelope->>'canonical_artifact_digest' OR binding_digest IS DISTINCT FROM p_envelope->>'expected_binding_digest' THEN RAISE EXCEPTION 'WRONG_REPORT_BINDING'; END IF;
 raw=convert_to('R54-EVALUATION-v1','UTF8')||decode('00','hex');
 FOREACH item IN ARRAY ARRAY[x.tenant_id::text,x.principal_id::text,en.key_id::text,'EVALUATION',en.profile_id,revision::text,rid::text,artifact_digest,binding_digest] LOOP
  raw=raw||convert_to(octet_length(convert_to(item,'UTF8'))::text||':'||item,'UTF8');
 END LOOP;
 envelope_digest=encode(sha256(raw),'hex');
 tag=decode(translate(p_envelope->>'auth_tag','-_','+/')||'=','base64');
 IF envelope_digest IS DISTINCT FROM p_envelope->>'envelope_digest' OR company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(p_key_material,raw),tag) IS DISTINCT FROM true THEN RAISE EXCEPTION 'INVALID_ENVELOPE_HMAC'; END IF;
 request_digest=encode(sha256(convert_to(jsonb_build_array(p_evaluation,p_envelope,p_binding)::text,'UTF8')),'hex');
 -- Shared project row serializes idempotency before INSERT, not global outbox IDs.
 SELECT * INTO cmd FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_idempotency;
 IF FOUND THEN
  IF cmd.payload_digest IS DISTINCT FROM request_digest OR cmd.r55_project_id IS DISTINCT FROM x.project_id OR cmd.r55_result_digest IS NULL THEN RAISE EXCEPTION 'CONFLICT_RECEIPT_COMMAND'; END IF;
  IF company_private.r54_allowed(x.tenant_id,x.project_id,'e0.evaluation_envelope_persist',x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_RECEIPT_REPLAY_CUT'; END IF;
  RETURN jsonb_build_object('command_id',cmd.id,'correlation_id',cmd.correlation_id,'state',cmd.state,'result_ref',cmd.result_ref);
 END IF;
 SELECT * INTO old FROM company.internal_receipt_envelopes WHERE tenant_id=x.tenant_id AND receipt_id=rid;
 IF FOUND THEN RAISE EXCEPTION 'RECEIPT_ID_ALREADY_PERSISTED_DIFFERENT_COMMAND'; END IF;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'e0.evaluation_envelope_persist',x.task_id,true) IS DISTINCT FROM true OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,en.valid_from,en.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'DENIED_RECEIPT_AFTER_LOCK_WAIT'; END IF;
 INSERT INTO company.internal_receipt_envelopes(tenant_id,issuer_id,key_id,purpose,enrollment_revision,receipt_id,profile_id,envelope_digest,expected_binding_digest,canonical_artifact_digest,auth_tag,verified_at)
 VALUES(x.tenant_id,x.principal_id,en.key_id,'EVALUATION',revision,rid,en.profile_id,envelope_digest,binding_digest,artifact_digest,p_envelope->>'auth_tag',clock_timestamp());
 INSERT INTO company.verifier_receipts(tenant_id,project_id,task_id,attempt_id,id,purpose,signer_id,key_id,receipt_digest,signature)
 VALUES(x.tenant_id,x.project_id,e.evaluation_task_id,e.evaluation_attempt_id,rid,'EVALUATION',x.principal_id,en.key_id,envelope_digest,p_envelope->>'auth_tag');
 cid=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,cid,x.principal_id,x.operation_id,p_idempotency,request_digest,p_correlation,'SUCCEEDED',rid);
 RETURN company_private.r55_cp_finalize_command(cid,rid,0,'E0EnvelopePersisted',jsonb_build_object('receipt_id',rid,'envelope_digest',envelope_digest,'verified_profile',en.profile_id));
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'RECEIPT_CANONICAL_SOURCE_UNRESOLVED';
 WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_RECEIPT_TYPED_BINDING';
END $$;
ALTER FUNCTION company_private.r55_cp_persist_evaluation_envelope(uuid,jsonb,jsonb,bytea,text,uuid) OWNER TO company_receipt_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_persist_evaluation_envelope(uuid,jsonb,jsonb,bytea,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_persist_evaluation_envelope(uuid,jsonb,jsonb,bytea,text,uuid) TO company_receipt_ingest_r55;
CREATE TRIGGER r55_immutable_internal_receipt BEFORE UPDATE OR DELETE ON company.internal_receipt_envelopes FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();
CREATE TRIGGER r55_immutable_verifier_receipt BEFORE UPDATE OR DELETE ON company.verifier_receipts FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();
-- Missing runtime identity/secret adapter/approved registry row remains BLOCKED.
-- No login is assigned to company_receipt_ingest_r55 here.
ROLLBACK;
