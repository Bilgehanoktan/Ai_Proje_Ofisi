BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- SOURCE CANDIDATE ONLY. r53 unified schema + r54 E0 delta precede this file.
-- No new canonical relation. Add proof metadata to the existing immutable artifact
-- owner; current process journal remains the sole local process/resource owner.
ALTER TABLE company.artifacts ADD COLUMN r55_e0_process_manifest jsonb;
ALTER TABLE company.artifacts ADD COLUMN r55_e0_process_observation jsonb;
ALTER TABLE company.process_runs ADD COLUMN r55_host_boot_id uuid;
ALTER TABLE company.process_runs ADD COLUMN r55_process_identity_digest text
 CHECK(r55_process_identity_digest IS NULL OR r55_process_identity_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE company.process_runs ADD COLUMN r55_admission_receipt_id uuid;
ALTER TABLE company.process_runs ADD COLUMN r55_stop_receipt_id uuid;
ALTER TABLE company.process_runs ADD COLUMN r55_isolation_artifact_id uuid;
ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,r55_admission_receipt_id)
 REFERENCES company.internal_receipt_envelopes(tenant_id,receipt_id);
ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,r55_stop_receipt_id)
 REFERENCES company.internal_receipt_envelopes(tenant_id,receipt_id);
ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,r55_isolation_artifact_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

CREATE ROLE company_e0_process_functions_r55 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_e0_process_functions_r55;
GRANT SELECT ON company_private.request_contexts,company_private.operation_permissions,
 company_private.bootstrap_receipts,company.internal_receipt_envelopes,
 company.signer_enrollments,company.principals,company.clock_epochs,company.workspaces
 TO company_e0_process_functions_r55;
GRANT SELECT,INSERT ON company.commands TO company_e0_process_functions_r55;
GRANT UPDATE(id) ON company.commands TO company_e0_process_functions_r55;
GRANT SELECT,INSERT,UPDATE ON company.budget_reservations,
 company.process_runs,company.resource_claims TO company_e0_process_functions_r55;
GRANT SELECT ON company.budget_versions,
 company.evaluation_runs,company.tasks,company.attempts,company.projects,
 company.host_registrations TO company_e0_process_functions_r55;
GRANT UPDATE(id) ON company.budget_versions,company.evaluation_runs,company.tasks,
 company.attempts,company.host_registrations TO company_e0_process_functions_r55;
GRANT SELECT,UPDATE(reserved) ON company.resource_slots TO company_e0_process_functions_r55;
GRANT SELECT ON company.artifacts TO company_e0_process_functions_r55;
GRANT UPDATE(id) ON company.artifacts TO company_e0_process_functions_r55;
GRANT UPDATE(enrollment_revision) ON company.signer_enrollments TO company_e0_process_functions_r55;
GRANT UPDATE(receipt_id) ON company.internal_receipt_envelopes TO company_e0_process_functions_r55;
GRANT EXECUTE ON FUNCTION company_private.r54_b_context(text,boolean,boolean),
 company_private.r54_allowed(uuid,uuid,text,uuid,boolean),
 company_private.r55_cp_clock_assert_current(uuid,uuid,uuid,uuid),
 company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz),
 company_private.r55_cp_require_not_expired(uuid,uuid,timestamptz),
 company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb)
 TO company_e0_process_functions_r55;
-- Explicit policy-approved identity is still NULL; no runtime command can pass
-- the existing r54 current-authority resolver until real approval/cutover.
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest)
VALUES ('e0.process_admit','e0.process_admit','PROJECT','COMMAND',0,NULL),
 ('e0.process_stop_confirm','e0.process_stop_confirm','PROJECT','COMMAND',0,NULL),
 ('e0.process_release','e0.process_release','PROJECT','COMMAND',0,NULL),
 ('e0.process_reconcile','e0.process_reconcile','PROJECT','COMMAND',0,NULL);

-- Exact artifact+enrollment+profile binding. A receipt row is NOT a new verifier.
-- The trusted persistence producer for these two profiles is an explicit OPEN
-- assembly dependency. Ordinary clients have no INSERT on envelopes/artifacts.
CREATE FUNCTION company_private.r55_cp_e0_verified_artifact(
 p_tenant uuid,p_project uuid,p_task uuid,p_attempt uuid,p_artifact uuid,
 p_receipt uuid,p_profile text,p_issuer uuid,p_binding_digest text)
RETURNS company.artifacts LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a company.artifacts%ROWTYPE; en company.internal_receipt_envelopes%ROWTYPE;
 s company.signer_enrollments%ROWTYPE; raw jsonb; d text; keys text[]; k text; allowed text[];
BEGIN
 IF p_tenant IS NULL OR p_project IS NULL OR p_task IS NULL OR p_attempt IS NULL
 OR p_artifact IS NULL OR p_receipt IS NULL OR p_issuer IS NULL
 OR p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$'
 OR p_profile IS NULL OR p_profile NOT IN ('r55.e0-process-admission.pg-jsonb.v1','r55.e0-process-observation.pg-jsonb.v1')
 THEN RAISE EXCEPTION 'INVALID_PROCESS_PROOF_BINDING'; END IF;
 SELECT * INTO STRICT a FROM company.artifacts WHERE tenant_id=p_tenant AND project_id=p_project
 AND task_id=p_task AND attempt_id=p_attempt AND id=p_artifact AND state='AVAILABLE' FOR SHARE;
 raw=CASE WHEN p_profile='r55.e0-process-admission.pg-jsonb.v1' THEN a.r55_e0_process_manifest ELSE a.r55_e0_process_observation END;
 IF raw IS NULL OR jsonb_typeof(raw)<>'object' OR raw->>'profile' IS DISTINCT FROM p_profile
 THEN RAISE EXCEPTION 'MISSING_TYPED_PROCESS_PROOF'; END IF;
 IF p_profile='r55.e0-process-admission.pg-jsonb.v1' THEN
  keys=ARRAY['profile','tenant_id','project_id','evaluation_run_id','task_id','attempt_id','worker_id',
   'model_digest','fixture_digest','profile_digest','workspace_id','network','external_effects','credentials','live_paths',
   'kind','amount_minor','claims','budget_id','budget_revision','environment_policy_digest','fencing_epoch','valid_until',
   'clock_epoch_id','clock_sample_id','host_boot_id','host_registration_id','host_registration_revision','host_generation',
   'controller_id','controller_generation'];
  allowed=keys;
 ELSE
  keys=ARRAY['profile','tenant_id','project_id','process_run_id','task_id','attempt_id','fencing_epoch','host_generation',
   'host_boot_id','controller_generation','manifest_digest','network','external_effects','observed_state'];
  allowed=keys||ARRAY['process_identity_digest','all_descendants_gone','cgroup_quiescent','workspace_fenced',
   'no_post_fence_spawn','usage_state','settled_minor','never_spawned','isolation_artifact_id','isolation_digest','clock_epoch_id','clock_sample_id'];
 END IF;
 IF NOT(raw ?& keys) OR EXISTS(SELECT 1 FROM jsonb_object_keys(raw) z WHERE NOT(z=ANY(allowed)))
 THEN RAISE EXCEPTION 'PROCESS_PROOF_EXACT_SCHEMA_REQUIRED'; END IF;
 FOREACH k IN ARRAY ARRAY['tenant_id','project_id','task_id','attempt_id','workspace_id','worker_id','evaluation_run_id',
  'budget_id','clock_epoch_id','clock_sample_id','host_boot_id','host_registration_id','controller_id','process_run_id','isolation_artifact_id'] LOOP
  IF raw ? k AND (jsonb_typeof(raw->k) IS DISTINCT FROM 'string' OR raw->>k !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
  THEN RAISE EXCEPTION 'PROCESS_PROOF_UUID_SCHEMA_REQUIRED'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['amount_minor','budget_revision','fencing_epoch','host_registration_revision','host_generation','controller_generation','settled_minor'] LOOP
  IF raw ? k AND (jsonb_typeof(raw->k) IS DISTINCT FROM 'number' OR (raw->>k)::numeric<>floor((raw->>k)::numeric)
   OR (raw->>k)::numeric<0 OR (raw->>k)::numeric>9007199254740991) THEN RAISE EXCEPTION 'PROCESS_PROOF_INTEGER_SCHEMA_REQUIRED'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['model_digest','fixture_digest','profile_digest','environment_policy_digest','manifest_digest','isolation_digest','process_identity_digest'] LOOP
  IF raw ? k AND NOT(k='process_identity_digest' AND raw->k='null'::jsonb AND raw->>'observed_state'='UNKNOWN_LOCAL')
  AND (jsonb_typeof(raw->k) IS DISTINCT FROM 'string' OR raw->>k !~ '^[a-f0-9]{64}$')
  THEN RAISE EXCEPTION 'PROCESS_PROOF_DIGEST_SCHEMA_REQUIRED'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['all_descendants_gone','cgroup_quiescent','workspace_fenced','no_post_fence_spawn','never_spawned'] LOOP
  IF raw ? k AND jsonb_typeof(raw->k) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'PROCESS_PROOF_BOOLEAN_SCHEMA_REQUIRED'; END IF;
 END LOOP;
 IF raw->>'tenant_id' IS DISTINCT FROM p_tenant::text OR raw->>'project_id' IS DISTINCT FROM p_project::text
 OR raw->>'task_id' IS DISTINCT FROM p_task::text OR raw->>'attempt_id' IS DISTINCT FROM p_attempt::text
 THEN RAISE EXCEPTION 'PROCESS_PROOF_EXACT_SCOPE_REQUIRED'; END IF;
 d=encode(sha256(convert_to(raw::text,'UTF8')),'hex');
 IF a.sha256 IS DISTINCT FROM d OR a.size_bytes IS DISTINCT FROM octet_length(convert_to(raw::text,'UTF8'))::bigint
 THEN RAISE EXCEPTION 'PROCESS_PROOF_CONTENT_MISMATCH'; END IF;
 SELECT * INTO STRICT en FROM company.internal_receipt_envelopes WHERE tenant_id=p_tenant
 AND receipt_id=p_receipt AND purpose='EVALUATION' AND profile_id=p_profile FOR SHARE;
 IF en.issuer_id IS DISTINCT FROM p_issuer OR en.canonical_artifact_digest IS DISTINCT FROM d
 OR en.expected_binding_digest IS DISTINCT FROM p_binding_digest THEN RAISE EXCEPTION 'PROCESS_PROOF_ENVELOPE_MISMATCH'; END IF;
 SELECT * INTO STRICT s FROM company.signer_enrollments WHERE tenant_id=en.tenant_id AND issuer_id=en.issuer_id
 AND key_id=en.key_id AND purpose=en.purpose AND enrollment_revision=en.enrollment_revision AND profile_id=en.profile_id FOR SHARE;
 IF s.revoked_at IS NOT NULL OR s.compromised_since IS NOT NULL
 OR company_private.r55_cp_time_window_current(p_tenant,p_project,s.valid_from,s.valid_until) IS DISTINCT FROM true
 OR en.verified_at<s.valid_from OR en.verified_at>=s.valid_until
 OR en.verified_at>clock_timestamp() THEN RAISE EXCEPTION 'PROCESS_PROOF_ENROLLMENT_NOT_CURRENT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=p_tenant AND id=s.approved_by AND kind='HUMAN')
 THEN RAISE EXCEPTION 'PROCESS_PROOF_HUMAN_ENROLLMENT_REQUIRED'; END IF;
 RETURN a;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'PROCESS_PROOF_UNRESOLVED';
END $$;

CREATE FUNCTION company_private.r55_cp_e0_process_admit(
 p_evaluation uuid,p_manifest uuid,p_receipt uuid,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE final_result jsonb; x company_private.request_contexts%ROWTYPE; e company.evaluation_runs%ROWTYPE;
 b company_private.bootstrap_receipts%ROWTYPE; t company.tasks%ROWTYPE; at company.attempts%ROWTYPE;
 art company.artifacts%ROWTYPE; v company.budget_versions%ROWTYPE; h company.host_registrations%ROWTYPE;
 c company.commands%ROWTYPE; sl company.resource_slots%ROWTYPE; m jsonb; item jsonb;
 d text; bind text; exposure numeric; process uuid; reservation uuid; cmd uuid; n integer;
BEGIN
 x=company_private.r54_b_context('e0.process_admit',true,true);
 IF p_evaluation IS NULL OR p_manifest IS NULL OR p_receipt IS NULL OR p_correlation IS NULL
 OR p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_PROCESS_ADMISSION'; END IF;
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation;
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=e.e0_installation_id;
 bind=encode(sha256(convert_to(jsonb_build_array(x.tenant_id,x.project_id,e.id,e.evaluation_task_id,e.evaluation_attempt_id,p_manifest)::text,'UTF8')),'hex');
 art=company_private.r55_cp_e0_verified_artifact(x.tenant_id,x.project_id,e.evaluation_task_id,e.evaluation_attempt_id,
 p_manifest,p_receipt,'r55.e0-process-admission.pg-jsonb.v1',b.accepted_human_id,bind);
 m=art.r55_e0_process_manifest;
 IF NOT ((m->>'tenant_id'=x.tenant_id::text AND m->>'project_id'=x.project_id::text
 AND m->>'evaluation_run_id'=e.id::text AND m->>'task_id'=e.evaluation_task_id::text
 AND m->>'attempt_id'=e.evaluation_attempt_id::text AND m->>'worker_id'=e.subject_principal_id::text
 AND m->>'model_digest'=e.model_digest AND m->>'fixture_digest'=e.fixture_digest
 AND m->>'profile_digest'=b.e0_mandate->>'profile_digest' AND m->>'workspace_id'=b.e0_mandate->>'workspace_id'
 AND m->>'network'='DENY' AND m->>'external_effects'='DENY' AND m->>'credentials'='NONE'
 AND m->>'live_paths'='DENY' AND m->>'kind' IN ('CHECK_SUITE','MUTANT_SUITE')
 AND (m->>'amount_minor')::bigint=0 AND jsonb_typeof(m->'claims')='array'
 AND jsonb_array_length(m->'claims')>0) IS TRUE) THEN RAISE EXCEPTION 'INVALID_FINITE_E0_MANIFEST'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(m->'claims') z GROUP BY (z->>'slot_id')::uuid HAVING count(*)>1)
 THEN RAISE EXCEPTION 'DUPLICATE_RESOURCE_SLOT'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(p_evaluation,p_manifest,p_receipt,m)::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id
 AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context('e0.process_admit',true,true);
  RETURN jsonb_build_object('process_run_id',c.result_ref,'command_id',c.id,'outcome','REPLAY_NO_SPAWN');
 END IF;
 -- Current project authority locks already serialize this budget across revisions.
 SELECT * INTO STRICT v FROM company.budget_versions WHERE tenant_id=x.tenant_id AND project_id=x.project_id
 AND budget_id=(m->>'budget_id')::uuid AND revision=(m->>'budget_revision')::bigint FOR UPDATE;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=v.tenant_id AND id=v.approved_by AND kind='HUMAN')
 OR v.environment_policy_digest IS DISTINCT FROM m->>'environment_policy_digest'
 THEN RAISE EXCEPTION 'BUDGET_HUMAN_POLICY_REQUIRED'; END IF;
 SELECT COALESCE(sum(greatest(amount_minor,settled_minor)-released_minor),0) INTO exposure
 FROM company.budget_reservations WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND budget_id=v.budget_id;
 IF exposure>v.limit_minor THEN RAISE EXCEPTION 'BUDGET_EXPOSURE_EXCEEDED'; END IF;
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND id=e.evaluation_task_id FOR UPDATE;
 SELECT * INTO STRICT at FROM company.attempts WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND task_id=t.id AND id=e.evaluation_attempt_id FOR UPDATE;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,b.e0_valid_until);
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,at.lease_expires_at);
 IF b.accepted_human_id IS DISTINCT FROM x.principal_id OR b.e0_valid_until IS NULL
 OR e.state<>'AUTHORIZED' OR t.execution_kind<>'EVALUATION' OR t.state NOT IN ('READY','RUNNING','VERIFYING')
 OR t.active_attempt_id IS DISTINCT FROM at.id OR t.fencing_epoch IS DISTINCT FROM at.fencing_epoch
 OR at.worker_id IS DISTINCT FROM e.subject_principal_id OR at.e0_evaluation_run_id IS DISTINCT FROM e.id
 OR at.admission_qualification_id IS NOT NULL OR at.state NOT IN ('CLAIMED','RUNNING') OR at.ended_at IS NOT NULL
 OR at.lease_expires_at>b.e0_valid_until
 OR at.fencing_epoch IS DISTINCT FROM (m->>'fencing_epoch')::bigint
 OR NOT isfinite((m->>'valid_until')::timestamptz) OR (m->>'valid_until')::timestamptz<at.lease_expires_at
 OR (m->>'valid_until')::timestamptz>b.e0_valid_until THEN RAISE EXCEPTION 'STALE_E0_ADMISSION_TUPLE'; END IF;
 PERFORM company_private.r55_cp_clock_assert_current(x.tenant_id,x.project_id,(m->>'clock_epoch_id')::uuid,(m->>'clock_sample_id')::uuid);
 IF NOT EXISTS(SELECT 1 FROM company.clock_epochs ce WHERE ce.tenant_id=x.tenant_id AND ce.epoch_id=(m->>'clock_epoch_id')::uuid
 AND ce.host_boot_id=(m->>'host_boot_id')::uuid AND ce.r55_host_registration_id=(m->>'host_registration_id')::uuid
 AND ce.r55_host_registration_revision=(m->>'host_registration_revision')::bigint
 AND ce.r55_host_generation=(m->>'host_generation')::bigint) THEN RAISE EXCEPTION 'PROCESS_CLOCK_BOOT_BINDING_MISMATCH'; END IF;
 SELECT * INTO STRICT h FROM company.host_registrations WHERE tenant_id=x.tenant_id AND project_id=x.project_id
 AND id=(m->>'host_registration_id')::uuid AND revision=(m->>'host_registration_revision')::bigint FOR SHARE;
 IF h.state<>'BOUND_NOT_LEASED' OR h.bound_generation IS DISTINCT FROM (m->>'host_generation')::bigint
 OR NOT EXISTS(SELECT 1 FROM company.projects pr JOIN company.workspaces ws ON ws.tenant_id=pr.tenant_id AND ws.id=pr.workspace_id
 WHERE pr.tenant_id=x.tenant_id AND pr.id=x.project_id AND pr.workspace_id=(m->>'workspace_id')::uuid
 AND ws.trust_class='DISPOSABLE_TEST' AND pr.host_registration_id=h.id AND pr.host_registration_revision=h.revision
 AND pr.instance_generation=h.bound_generation) THEN RAISE EXCEPTION 'E0_HOST_OR_ISOLATION_BINDING_STALE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=(m->>'controller_id')::uuid AND kind IN ('WORKER','VERIFIER'))
 OR (m->>'controller_generation')::bigint<=0 OR (m->>'controller_id')::uuid=e.subject_principal_id
 THEN RAISE EXCEPTION 'E0_INDEPENDENT_CONTROLLER_REQUIRED'; END IF;
 IF EXISTS(SELECT 1 FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id
 AND e0_evaluation_run_id=e.id) THEN RAISE EXCEPTION 'E0_RUN_ALREADY_RESERVED_NO_RESPAWN'; END IF;
 process=gen_random_uuid();reservation=gen_random_uuid();cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'SUCCEEDED',process);
 INSERT INTO company.budget_reservations(tenant_id,project_id,id,budget_id,budget_revision,task_id,attempt_id,attempt_fencing_epoch,
 semantic_key,payload_digest,admission_artifact_id,amount_minor,state,command_id)
 VALUES(x.tenant_id,x.project_id,reservation,v.budget_id,v.revision,t.id,at.id,at.fencing_epoch,
 'e0:'||e.id::text,d,p_manifest,0,'RESERVED',cmd);
 INSERT INTO company.process_runs(tenant_id,project_id,id,task_id,attempt_id,attempt_fencing_epoch,worker_lease_id,worker_id,
 qualification_id,e0_evaluation_run_id,lease_expires_at,workspace_id,host_registration_id,host_registration_revision,host_generation,
 controller_id,controller_generation,kind,state,reservation_id,manifest_artifact_id,manifest_digest,semantic_run_digest,start_command_id,
 r55_host_boot_id,r55_admission_receipt_id)
 VALUES(x.tenant_id,x.project_id,process,t.id,at.id,at.fencing_epoch,gen_random_uuid(),at.worker_id,NULL,e.id,at.lease_expires_at,
 (m->>'workspace_id')::uuid,h.id,h.revision,h.bound_generation,(m->>'controller_id')::uuid,(m->>'controller_generation')::bigint,
 m->>'kind','REQUESTED',reservation,p_manifest,art.sha256,d,cmd,(m->>'host_boot_id')::uuid,p_receipt);
 FOR item IN SELECT value FROM jsonb_array_elements(m->'claims') ORDER BY (value->>'slot_id')::uuid LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR jsonb_typeof(item->'units') IS DISTINCT FROM 'number'
  OR jsonb_typeof(item->'slot_id') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_RESOURCE_CLAIM_SHAPE'; END IF;
  n=(item->>'units')::integer;
  IF n IS NULL OR n<=0 OR item->>'slot_id' IS NULL THEN RAISE EXCEPTION 'INVALID_RESOURCE_UNITS'; END IF;
  SELECT * INTO STRICT sl FROM company.resource_slots WHERE tenant_id=x.tenant_id AND id=(item->>'slot_id')::uuid FOR UPDATE;
  UPDATE company.resource_slots SET reserved=reserved+n WHERE tenant_id=x.tenant_id AND id=sl.id AND reserved=sl.reserved AND capacity-reserved>=n;
  IF NOT FOUND THEN RAISE EXCEPTION 'RESOURCE_CAPACITY_EXCEEDED'; END IF;
  INSERT INTO company.resource_claims(tenant_id,project_id,process_run_id,slot_id,units,state)
  VALUES(x.tenant_id,x.project_id,process,sl.id,n,'HELD');
 END LOOP;
 final_result=company_private.r55_cp_finalize_command(cmd,process,0,'E0ProcessAdmitted',
 jsonb_build_object('process_run_id',process,'reservation_id',reservation,'state','REQUESTED','spawned',false,'ordinary_admission',false));
 -- R55_POST_ALL_LOCKS_CUT: finalizer can wait too; rollback all rows on expiry.
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,b.e0_valid_until);
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,at.lease_expires_at);
 PERFORM company_private.r54_b_context('e0.process_admit',true,true);
 RETURN final_result;
END $$;

-- Fact ingestion must authenticate original process identity; client PID, TTL or
-- boolean "stopped" never suffices. STOPPED proof may arrive after lease expiry:
-- cleanup authorization is current, but the immutable original tuple is retained.
CREATE FUNCTION company_private.r55_cp_e0_process_observe(
 p_operation text,p_process uuid,p_expected_revision bigint,p_artifact uuid,p_receipt uuid,
 p_key text,p_correlation uuid,p_require_stop boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE final_result jsonb; x company_private.request_contexts%ROWTYPE;r company.process_runs%ROWTYPE;
 a company.artifacts%ROWTYPE;c company.commands%ROWTYPE;m jsonb;d text;bind text;cmd uuid;next_state text;
BEGIN
 IF p_operation IS NULL OR p_operation NOT IN ('e0.process_stop_confirm','e0.process_reconcile') OR p_require_stop IS NULL
 OR (p_operation='e0.process_stop_confirm') IS DISTINCT FROM p_require_stop
 OR p_process IS NULL OR p_expected_revision IS NULL OR p_expected_revision<0 OR p_artifact IS NULL OR p_receipt IS NULL
 OR p_correlation IS NULL OR p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_PROCESS_OBSERVATION'; END IF;
 x=company_private.r54_b_context(p_operation,false,true);
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 IF r.e0_evaluation_run_id IS NULL OR r.qualification_id IS NOT NULL OR r.controller_id IS DISTINCT FROM x.principal_id
 THEN RAISE EXCEPTION 'E0_CONTROLLER_TUPLE_REQUIRED'; END IF;
 bind=encode(sha256(convert_to(jsonb_build_array(r.tenant_id,r.project_id,r.id,r.task_id,r.attempt_id,r.attempt_fencing_epoch,
 r.host_registration_id,r.host_registration_revision,r.host_generation,r.r55_host_boot_id,r.controller_id,r.controller_generation,r.manifest_digest)::text,'UTF8')),'hex');
 a=company_private.r55_cp_e0_verified_artifact(r.tenant_id,r.project_id,r.task_id,r.attempt_id,p_artifact,p_receipt,
 'r55.e0-process-observation.pg-jsonb.v1',r.controller_id,bind);
 m=a.r55_e0_process_observation;
 d=encode(sha256(convert_to(jsonb_build_array(p_process,p_expected_revision,p_artifact,p_receipt,p_operation)::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context(p_operation,false,true);
  RETURN jsonb_build_object('process_run_id',r.id,'command_id',c.id,'outcome','REPLAY_ORIGINAL_FACT_NO_RESPAWN');
 END IF;
 IF r.revision IS DISTINCT FROM p_expected_revision OR r.state IN ('STOPPED','COMPLETED','FAILED_NOT_STARTED')
 OR r.release_command_id IS NOT NULL THEN RAISE EXCEPTION 'STALE_OR_TERMINAL_PROCESS'; END IF;
 IF NOT ((m->>'process_run_id'=r.id::text AND m->>'task_id'=r.task_id::text AND m->>'attempt_id'=r.attempt_id::text
 AND (m->>'fencing_epoch')::bigint=r.attempt_fencing_epoch AND (m->>'host_generation')::bigint=r.host_generation
 AND m->>'host_boot_id'=r.r55_host_boot_id::text AND (m->>'controller_generation')::bigint=r.controller_generation
 AND m->>'manifest_digest'=r.manifest_digest AND m->>'network'='DENY'
 AND m->>'external_effects'='DENY' AND ((m->>'observed_state'='UNKNOWN_LOCAL' AND m->>'process_identity_digest' IS NULL)
 OR m->>'process_identity_digest' ~ '^[a-f0-9]{64}$')) IS TRUE)
 THEN RAISE EXCEPTION 'PROCESS_OBSERVATION_TUPLE_MISMATCH'; END IF;
 IF r.r55_process_identity_digest IS NOT NULL AND r.r55_process_identity_digest IS DISTINCT FROM m->>'process_identity_digest'
 THEN RAISE EXCEPTION 'ORIGINAL_PROCESS_IDENTITY_CHANGED'; END IF;
 next_state=m->>'observed_state';
 IF next_state NOT IN ('RUNNING','STOPPED','UNKNOWN_LOCAL','FAILED_NOT_STARTED') OR next_state IS NULL
 OR (p_require_stop AND next_state<>'STOPPED') THEN RAISE EXCEPTION 'INVALID_PROCESS_OBSERVATION_STATE'; END IF;
 IF next_state='RUNNING' AND r.state='STOP_REQUESTED' THEN RAISE EXCEPTION 'STALE_RUN_CANNOT_RESUME'; END IF;
 IF next_state='RUNNING' THEN
  PERFORM company_private.r55_cp_require_not_expired(r.tenant_id,r.project_id,r.lease_expires_at);
  PERFORM company_private.r55_cp_clock_assert_current(r.tenant_id,r.project_id,(m->>'clock_epoch_id')::uuid,(m->>'clock_sample_id')::uuid);
  IF NOT EXISTS(SELECT 1 FROM company.clock_epochs ce WHERE ce.tenant_id=r.tenant_id AND ce.epoch_id=(m->>'clock_epoch_id')::uuid
   AND ce.host_boot_id=r.r55_host_boot_id AND ce.r55_host_registration_id=r.host_registration_id
   AND ce.r55_host_registration_revision=r.host_registration_revision AND ce.r55_host_generation=r.host_generation)
  THEN RAISE EXCEPTION 'REBOOTED_HOST_CANNOT_RESUME_ORIGINAL_PROCESS'; END IF;
 END IF;
 IF next_state='RUNNING' AND NOT EXISTS(SELECT 1 FROM company.tasks t JOIN company.attempts at
 ON at.tenant_id=t.tenant_id AND at.project_id=t.project_id AND at.task_id=t.id AND at.id=t.active_attempt_id
 JOIN company.host_registrations h ON h.tenant_id=t.tenant_id AND h.project_id=t.project_id
 JOIN company.projects pr ON pr.tenant_id=t.tenant_id AND pr.id=t.project_id
 WHERE t.tenant_id=r.tenant_id AND t.project_id=r.project_id AND t.id=r.task_id AND t.execution_kind='EVALUATION'
 AND t.state IN ('READY','RUNNING','VERIFYING') AND at.id=r.attempt_id AND at.fencing_epoch=r.attempt_fencing_epoch
 AND t.fencing_epoch=at.fencing_epoch AND at.worker_id=r.worker_id AND at.state IN ('CLAIMED','RUNNING')
 AND at.ended_at IS NULL AND at.lease_expires_at=r.lease_expires_at
 AND h.id=r.host_registration_id AND h.revision=r.host_registration_revision AND h.bound_generation=r.host_generation
 AND h.state='BOUND_NOT_LEASED' AND pr.instance_generation=r.host_generation
 AND pr.host_registration_id=h.id AND pr.host_registration_revision=h.revision)
 THEN RAISE EXCEPTION 'STALE_OR_REVOKED_RUN_BINDING'; END IF;
 IF next_state='STOPPED' AND NOT ((m->'all_descendants_gone'='true'::jsonb AND m->'cgroup_quiescent'='true'::jsonb
 AND m->'workspace_fenced'='true'::jsonb AND m->'no_post_fence_spawn'='true'::jsonb
 AND m->>'usage_state'='VERIFIED_ZERO_LOCAL' AND (m->>'settled_minor')::bigint=0) IS TRUE)
 THEN RAISE EXCEPTION 'PROCESS_STOP_QUIESCENCE_PROOF_REQUIRED'; END IF;
 IF next_state='FAILED_NOT_STARTED' AND NOT ((m->'never_spawned'='true'::jsonb AND m->'all_descendants_gone'='true'::jsonb
 AND m->'cgroup_quiescent'='true'::jsonb AND m->'workspace_fenced'='true'::jsonb
 AND m->'no_post_fence_spawn'='true'::jsonb AND m->>'usage_state'='VERIFIED_ZERO_LOCAL'
 AND (m->>'settled_minor')::bigint=0) IS TRUE) THEN RAISE EXCEPTION 'NO_SPAWN_PROOF_REQUIRED'; END IF;
 IF next_state='RUNNING' AND NOT EXISTS(SELECT 1 FROM company.artifacts ia WHERE ia.tenant_id=r.tenant_id AND ia.project_id=r.project_id
 AND ia.task_id=r.task_id AND ia.attempt_id=r.attempt_id AND ia.id=(m->>'isolation_artifact_id')::uuid AND ia.state='AVAILABLE'
 AND ia.sha256=m->>'isolation_digest') THEN RAISE EXCEPTION 'ISOLATION_PROOF_REQUIRED'; END IF;
 cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'SUCCEEDED',r.id);
 UPDATE company.process_runs SET state=next_state,revision=revision+1,
 r55_process_identity_digest=m->>'process_identity_digest',
 stop_command_id=CASE WHEN next_state IN ('STOPPED','FAILED_NOT_STARTED') THEN cmd ELSE stop_command_id END,
 stop_artifact_id=CASE WHEN next_state IN ('STOPPED','FAILED_NOT_STARTED') THEN a.id ELSE stop_artifact_id END,
 r55_stop_receipt_id=CASE WHEN next_state IN ('STOPPED','FAILED_NOT_STARTED') THEN p_receipt ELSE r55_stop_receipt_id END,
 r55_isolation_artifact_id=CASE WHEN next_state='RUNNING' THEN (m->>'isolation_artifact_id')::uuid ELSE r55_isolation_artifact_id END
 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=p_expected_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'PROCESS_REVISION_CONFLICT'; END IF;
 final_result=company_private.r55_cp_finalize_command(cmd,r.id,p_expected_revision+1,
 CASE WHEN p_require_stop THEN 'E0ProcessStopConfirmed' ELSE 'E0ProcessReconciled' END,
 jsonb_build_object('process_run_id',r.id,'state',next_state,'spawned',false,'resources_released',false));
 -- R55_POST_ALL_LOCKS_CUT: finalizer can wait too; rollback all rows on expiry.
 IF next_state='RUNNING' THEN
  PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
 END IF;
 PERFORM company_private.r54_b_context(p_operation,false,true);
 RETURN final_result;
END $$;

CREATE FUNCTION company_private.r55_cp_e0_process_stop_confirm(uuid,bigint,uuid,uuid,text,uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT company_private.r55_cp_e0_process_observe('e0.process_stop_confirm',$1,$2,$3,$4,$5,$6,true);
$$;
CREATE FUNCTION company_private.r55_cp_e0_process_reconcile(uuid,bigint,uuid,uuid,text,uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT company_private.r55_cp_e0_process_observe('e0.process_reconcile',$1,$2,$3,$4,$5,$6,false);
$$;

CREATE FUNCTION company_private.r55_cp_e0_process_release(p_process uuid,p_expected_revision bigint,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE final_result jsonb; x company_private.request_contexts%ROWTYPE;r company.process_runs%ROWTYPE;b company.budget_reservations%ROWTYPE;
 cl company.resource_claims%ROWTYPE;v company.budget_versions%ROWTYPE;art company.artifacts%ROWTYPE;
 c company.commands%ROWTYPE;cmd uuid;d text;bind text;
BEGIN
 x=company_private.r54_b_context('e0.process_release',false,true);
 IF p_process IS NULL OR p_expected_revision IS NULL OR p_expected_revision<0 OR p_key IS NULL
 OR length(p_key) NOT BETWEEN 16 AND 128 OR p_correlation IS NULL THEN RAISE EXCEPTION 'INVALID_PROCESS_RELEASE'; END IF;
 -- Read immutable identity first, lock budget before process and slots.
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process;
 SELECT * INTO STRICT b FROM company.budget_reservations WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.reservation_id;
 SELECT * INTO STRICT v FROM company.budget_versions WHERE tenant_id=b.tenant_id AND project_id=b.project_id AND budget_id=b.budget_id AND revision=b.budget_revision FOR UPDATE;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 d=encode(sha256(convert_to(jsonb_build_array(p_process,p_expected_revision,r.stop_artifact_id,r.r55_stop_receipt_id)::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context('e0.process_release',false,true);
  RETURN jsonb_build_object('process_run_id',r.id,'command_id',c.id,'outcome','REPLAY_NO_SECOND_RELEASE');
 END IF;
 IF r.e0_evaluation_run_id IS NULL OR r.qualification_id IS NOT NULL OR r.revision IS DISTINCT FROM p_expected_revision
 OR r.state NOT IN ('STOPPED','FAILED_NOT_STARTED') OR r.stop_artifact_id IS NULL OR r.r55_stop_receipt_id IS NULL
 OR r.release_command_id IS NOT NULL THEN RAISE EXCEPTION 'STOP_PROOF_REQUIRED_NO_TTL_RELEASE'; END IF;
 bind=encode(sha256(convert_to(jsonb_build_array(r.tenant_id,r.project_id,r.id,r.task_id,r.attempt_id,r.attempt_fencing_epoch,
 r.host_registration_id,r.host_registration_revision,r.host_generation,r.r55_host_boot_id,r.controller_id,r.controller_generation,r.manifest_digest)::text,'UTF8')),'hex');
 art=company_private.r55_cp_e0_verified_artifact(r.tenant_id,r.project_id,r.task_id,r.attempt_id,r.stop_artifact_id,r.r55_stop_receipt_id,
 'r55.e0-process-observation.pg-jsonb.v1',r.controller_id,bind);
 IF NOT ((art.r55_e0_process_observation->>'usage_state'='VERIFIED_ZERO_LOCAL'
 AND (art.r55_e0_process_observation->>'settled_minor')::bigint=0) IS TRUE) THEN RAISE EXCEPTION 'UNKNOWN_USAGE_NO_RELEASE'; END IF;
 SELECT * INTO STRICT b FROM company.budget_reservations WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.reservation_id FOR UPDATE;
 IF b.task_id IS DISTINCT FROM r.task_id OR b.attempt_id IS DISTINCT FROM r.attempt_id OR b.attempt_fencing_epoch IS DISTINCT FROM r.attempt_fencing_epoch
 OR b.state<>'RESERVED' OR b.amount_minor<>0 OR b.settled_minor<>0 OR b.released_minor<>0 THEN RAISE EXCEPTION 'RESERVATION_NOT_RELEASABLE'; END IF;
 cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'SUCCEEDED',r.id);
 FOR cl IN SELECT * FROM company.resource_claims WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND process_run_id=r.id ORDER BY slot_id FOR UPDATE LOOP
  IF cl.state<>'HELD' THEN RAISE EXCEPTION 'CLAIM_ALREADY_RELEASED'; END IF;
  UPDATE company.resource_slots SET reserved=reserved-cl.units WHERE tenant_id=cl.tenant_id AND id=cl.slot_id AND reserved>=cl.units;
  IF NOT FOUND THEN RAISE EXCEPTION 'CLAIM_CAPACITY_ACCOUNTING_CONFLICT'; END IF;
  UPDATE company.resource_claims SET state='RELEASED',revision=revision+1,release_command_id=cmd
  WHERE tenant_id=cl.tenant_id AND project_id=cl.project_id AND process_run_id=cl.process_run_id AND slot_id=cl.slot_id AND revision=cl.revision AND state='HELD';
  IF NOT FOUND THEN RAISE EXCEPTION 'CLAIM_REVISION_CONFLICT'; END IF;
 END LOOP;
 UPDATE company.budget_reservations SET state='RELEASED',revision=revision+1,released_minor=0,
 settlement_command_id=cmd,release_command_id=cmd,release_op_id=cmd
 WHERE tenant_id=b.tenant_id AND project_id=b.project_id AND id=b.id AND revision=b.revision AND state='RESERVED';
 IF NOT FOUND THEN RAISE EXCEPTION 'RESERVATION_REVISION_CONFLICT'; END IF;
 UPDATE company.process_runs SET release_command_id=cmd,revision=revision+1
 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=p_expected_revision AND release_command_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'PROCESS_REVISION_CONFLICT'; END IF;
 final_result=company_private.r55_cp_finalize_command(cmd,r.id,p_expected_revision+1,'E0ProcessReleased',
 jsonb_build_object('process_run_id',r.id,'state',r.state,'released',true,'ordinary_admission',false));
 -- R55_POST_ALL_LOCKS_CUT: finalizer can wait too; rollback all rows on expiry.
 PERFORM company_private.r55_cp_e0_verified_artifact(r.tenant_id,r.project_id,r.task_id,r.attempt_id,r.stop_artifact_id,r.r55_stop_receipt_id,
 'r55.e0-process-observation.pg-jsonb.v1',r.controller_id,bind);
 PERFORM company_private.r54_b_context('e0.process_release',false,true);
 RETURN final_result;
END $$;

-- Ownership and revocation are candidate DDL, not proof of live DB privileges.
ALTER FUNCTION company_private.r55_cp_e0_verified_artifact(uuid,uuid,uuid,uuid,uuid,uuid,text,uuid,text) OWNER TO company_e0_process_functions_r55;
ALTER FUNCTION company_private.r55_cp_e0_process_admit(uuid,uuid,uuid,text,uuid) OWNER TO company_e0_process_functions_r55;
ALTER FUNCTION company_private.r55_cp_e0_process_observe(text,uuid,bigint,uuid,uuid,text,uuid,boolean) OWNER TO company_e0_process_functions_r55;
ALTER FUNCTION company_private.r55_cp_e0_process_stop_confirm(uuid,bigint,uuid,uuid,text,uuid) OWNER TO company_e0_process_functions_r55;
ALTER FUNCTION company_private.r55_cp_e0_process_reconcile(uuid,bigint,uuid,uuid,text,uuid) OWNER TO company_e0_process_functions_r55;
ALTER FUNCTION company_private.r55_cp_e0_process_release(uuid,bigint,text,uuid) OWNER TO company_e0_process_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_e0_verified_artifact(uuid,uuid,uuid,uuid,uuid,uuid,text,uuid,text),
 company_private.r55_cp_e0_process_admit(uuid,uuid,uuid,text,uuid),
 company_private.r55_cp_e0_process_observe(text,uuid,bigint,uuid,uuid,text,uuid,boolean),
 company_private.r55_cp_e0_process_stop_confirm(uuid,bigint,uuid,uuid,text,uuid),
 company_private.r55_cp_e0_process_reconcile(uuid,bigint,uuid,uuid,text,uuid),
 company_private.r55_cp_e0_process_release(uuid,bigint,text,uuid) FROM PUBLIC;
-- No transport EXECUTE is granted. RLS policies, operation grants, proof profile
-- enrollment and final physical catalog verification must be admitted together.

-- R55_B_FINAL_OVERLAY: context-only RLS; trusted helper owner cannot login.
CREATE POLICY r55_e0_process_context ON company_private.request_contexts FOR SELECT TO company_e0_process_functions_r55 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r55_e0_process_ops ON company_private.operation_permissions FOR SELECT TO company_e0_process_functions_r55 USING(operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile'));
CREATE POLICY r55_e0_process_principals ON company.principals FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=principals.tenant_id));
CREATE POLICY r55_e0_process_internal_receipt_envelopes ON company.internal_receipt_envelopes FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=internal_receipt_envelopes.tenant_id));
CREATE POLICY r55_e0_process_internal_receipt_envelopes_lock ON company.internal_receipt_envelopes FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=internal_receipt_envelopes.tenant_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_signer_enrollments ON company.signer_enrollments FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=signer_enrollments.tenant_id));
CREATE POLICY r55_e0_process_signer_enrollments_lock ON company.signer_enrollments FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=signer_enrollments.tenant_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_resource_slots ON company.resource_slots TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=resource_slots.tenant_id)) WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=resource_slots.tenant_id));
CREATE POLICY r55_e0_process_commands ON company.commands FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=commands.tenant_id));
CREATE POLICY r55_e0_process_commands_insert ON company.commands FOR INSERT TO company_e0_process_functions_r55 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=commands.tenant_id));
CREATE POLICY r55_e0_process_commands_lock ON company.commands FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=commands.tenant_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_artifacts ON company.artifacts FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=artifacts.tenant_id AND x.project_id=artifacts.project_id));
CREATE POLICY r55_e0_process_artifacts_lock ON company.artifacts FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=artifacts.tenant_id AND x.project_id=artifacts.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_budget_reservations ON company.budget_reservations TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=budget_reservations.tenant_id AND x.project_id=budget_reservations.project_id)) WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=budget_reservations.tenant_id AND x.project_id=budget_reservations.project_id));
CREATE POLICY r55_e0_process_process_runs ON company.process_runs TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=process_runs.tenant_id AND x.project_id=process_runs.project_id)) WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=process_runs.tenant_id AND x.project_id=process_runs.project_id));
CREATE POLICY r55_e0_process_resource_claims ON company.resource_claims TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=resource_claims.tenant_id AND x.project_id=resource_claims.project_id)) WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=resource_claims.tenant_id AND x.project_id=resource_claims.project_id));
CREATE POLICY r55_e0_process_budget_versions ON company.budget_versions FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=budget_versions.tenant_id AND x.project_id=budget_versions.project_id));
CREATE POLICY r55_e0_process_budget_versions_lock ON company.budget_versions FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=budget_versions.tenant_id AND x.project_id=budget_versions.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_evaluation_runs ON company.evaluation_runs FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=evaluation_runs.tenant_id AND x.project_id=evaluation_runs.project_id));
CREATE POLICY r55_e0_process_evaluation_runs_lock ON company.evaluation_runs FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=evaluation_runs.tenant_id AND x.project_id=evaluation_runs.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_tasks ON company.tasks FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=tasks.tenant_id AND x.project_id=tasks.project_id));
CREATE POLICY r55_e0_process_tasks_lock ON company.tasks FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=tasks.tenant_id AND x.project_id=tasks.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_attempts ON company.attempts FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=attempts.tenant_id AND x.project_id=attempts.project_id));
CREATE POLICY r55_e0_process_attempts_lock ON company.attempts FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=attempts.tenant_id AND x.project_id=attempts.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_host_registrations ON company.host_registrations FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=host_registrations.tenant_id AND x.project_id=host_registrations.project_id));
CREATE POLICY r55_e0_process_host_registrations_lock ON company.host_registrations FOR UPDATE TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=host_registrations.tenant_id AND x.project_id=host_registrations.project_id)) WITH CHECK(false);
CREATE POLICY r55_e0_process_projects ON company.projects FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=projects.tenant_id AND x.project_id=projects.id));
CREATE POLICY r55_e0_process_workspaces ON company.workspaces FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=workspaces.tenant_id AND workspaces.id=(SELECT pr.workspace_id FROM company.projects pr WHERE pr.tenant_id=x.tenant_id AND pr.id=x.project_id)));
CREATE POLICY r55_e0_process_clock_epochs ON company.clock_epochs FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=clock_epochs.tenant_id AND x.project_id=clock_epochs.r55_project_id));
CREATE POLICY r55_e0_process_bootstrap ON company_private.bootstrap_receipts FOR SELECT TO company_e0_process_functions_r55 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id IN ('e0.process_admit','e0.process_stop_confirm','e0.process_release','e0.process_reconcile','e0.evaluation_worker_admit') AND x.tenant_id=bootstrap_receipts.tenant_id AND x.project_id=bootstrap_receipts.project_id));
CREATE FUNCTION company_private.r55_cp_e0_process_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.e0_evaluation_run_id IS NOT NULL THEN
  IF (to_jsonb(NEW)-ARRAY['state','revision','stop_command_id','stop_artifact_id','release_command_id',
    'r55_process_identity_digest','r55_stop_receipt_id','r55_isolation_artifact_id']) IS DISTINCT FROM
   (to_jsonb(OLD)-ARRAY['state','revision','stop_command_id','stop_artifact_id','release_command_id',
    'r55_process_identity_digest','r55_stop_receipt_id','r55_isolation_artifact_id'])
   OR (OLD.r55_process_identity_digest IS NOT NULL AND NEW.r55_process_identity_digest IS DISTINCT FROM OLD.r55_process_identity_digest)
   OR (OLD.release_command_id IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD))
   OR (OLD.state IN ('STOPPED','COMPLETED','FAILED_NOT_STARTED') AND NEW.state IS DISTINCT FROM OLD.state)
  THEN RAISE EXCEPTION 'IMMUTABLE_E0_PROCESS_IDENTITY'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER r55_e0_process_identity_immutable BEFORE UPDATE ON company.process_runs
FOR EACH ROW EXECUTE FUNCTION company_private.r55_cp_e0_process_identity_immutable();
ALTER FUNCTION company_private.r55_cp_e0_process_identity_immutable() OWNER TO company_e0_process_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_e0_process_identity_immutable() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_e0_verified_artifact(uuid,uuid,uuid,uuid,uuid,uuid,text,uuid,text) TO company_first_run_functions_r53;

-- Exact worker_admit consumer fix: artifact digest is not profile digest.
CREATE OR REPLACE FUNCTION company_private.r54_e0_evaluation_worker_admit(p_evaluation uuid,p_process uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE;r company.process_runs%ROWTYPE;b company_private.bootstrap_receipts%ROWTYPE;
BEGIN
 x=company_private.r54_b_context('e0.evaluation_worker_admit',true);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=e.e0_installation_id;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,b.e0_valid_until);
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
 IF b.accepted_human_id IS DISTINCT FROM x.principal_id OR b.e0_valid_until IS NULL OR e.state NOT IN ('AUTHORIZED','RUNNING')
 OR r.e0_evaluation_run_id IS DISTINCT FROM e.id OR r.qualification_id IS NOT NULL OR r.worker_id IS DISTINCT FROM e.subject_principal_id OR r.task_id IS DISTINCT FROM e.evaluation_task_id OR r.attempt_id IS DISTINCT FROM e.evaluation_attempt_id OR r.kind NOT IN ('CHECK_SUITE','MUTANT_SUITE') OR r.state NOT IN ('LEASED','REQUESTED') OR r.lease_expires_at>b.e0_valid_until
 OR r.workspace_id IS DISTINCT FROM (b.e0_mandate->>'workspace_id')::uuid OR r.r55_admission_receipt_id IS NULL OR NOT EXISTS(SELECT 1 FROM company.artifacts ma WHERE ma.tenant_id=r.tenant_id AND ma.project_id=r.project_id AND ma.task_id=r.task_id AND ma.attempt_id=r.attempt_id AND ma.id=r.manifest_artifact_id AND ma.state='AVAILABLE' AND ma.sha256=r.manifest_digest AND ma.r55_e0_process_manifest->>'profile_digest'=b.e0_mandate->>'profile_digest') THEN RAISE EXCEPTION 'DENIED_E0_PROCESS_BINDING'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.attempts at JOIN company.tasks t ON t.tenant_id=at.tenant_id AND t.project_id=at.project_id AND t.id=at.task_id WHERE at.tenant_id=e.tenant_id AND at.project_id=e.project_id AND at.task_id=e.evaluation_task_id AND at.id=e.evaluation_attempt_id AND at.fencing_epoch=r.attempt_fencing_epoch AND at.worker_id=r.worker_id AND at.ended_at IS NULL AND at.lease_expires_at=r.lease_expires_at AND t.execution_kind='EVALUATION' AND t.active_attempt_id=at.id AND t.fencing_epoch=at.fencing_epoch) THEN RAISE EXCEPTION 'STALE_E0_ATTEMPT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.budget_reservations z WHERE z.tenant_id=r.tenant_id AND z.project_id=r.project_id AND z.id=r.reservation_id AND z.task_id=r.task_id AND z.attempt_id=r.attempt_id AND z.attempt_fencing_epoch=r.attempt_fencing_epoch AND z.state='RESERVED') THEN RAISE EXCEPTION 'E0_BUDGET_NOT_RESERVED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.resource_claims c JOIN company.resource_slots sl ON sl.tenant_id=c.tenant_id AND sl.id=c.slot_id WHERE c.tenant_id=r.tenant_id AND c.project_id=r.project_id AND c.process_run_id=r.id AND c.state='HELD' AND c.units>0 AND sl.reserved>=c.units AND sl.reserved<=sl.capacity) THEN RAISE EXCEPTION 'E0_RESOURCE_NOT_HELD'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.host_registrations h JOIN company.projects pr ON pr.tenant_id=h.tenant_id AND pr.id=h.project_id WHERE h.tenant_id=r.tenant_id AND h.project_id=r.project_id AND h.id=r.host_registration_id AND h.revision=r.host_registration_revision AND h.bound_generation=r.host_generation AND pr.instance_generation=r.host_generation AND pr.host_registration_id=h.id AND pr.host_registration_revision=h.revision AND h.state='BOUND_NOT_LEASED') THEN RAISE EXCEPTION 'E0_HOST_GENERATION_STALE'; END IF;
 PERFORM company_private.r55_cp_e0_verified_artifact(r.tenant_id,r.project_id,r.task_id,r.attempt_id,r.manifest_artifact_id,
 r.r55_admission_receipt_id,'r55.e0-process-admission.pg-jsonb.v1',b.accepted_human_id,
 encode(sha256(convert_to(jsonb_build_array(r.tenant_id,r.project_id,e.id,e.evaluation_task_id,e.evaluation_attempt_id,r.manifest_artifact_id)::text,'UTF8')),'hex'));
 UPDATE company.evaluation_runs SET state='RUNNING' WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND id=e.id;
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,e.id,2,'E0WorkerAdmitted',jsonb_build_object('process_run_id',r.id,'network','DENY','external_effects','DENY','ordinary_admission',false));
 PERFORM company_private.r54_b_context(x.operation_id,true);
 RETURN jsonb_build_object('evaluation_run_id',e.id,'process_run_id',r.id,'outcome','EVALUATION_ADMISSION_ONLY_NOT_SPAWNED','ordinary_qualification',NULL);
END $$;
ALTER FUNCTION company_private.r54_e0_evaluation_worker_admit(uuid,uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_e0_evaluation_worker_admit(uuid,uuid) FROM PUBLIC;
ROLLBACK;
