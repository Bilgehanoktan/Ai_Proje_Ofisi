BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r53_objectives_create(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; v_project uuid; v_correlation uuid;
 v_key text; v_digest text; v_id uuid; v_command uuid; v_revision bigint; element jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='objectives.create';
 IF p_request IS NULL OR jsonb_typeof(p_request)<>'object' OR NOT (p_request ?& ARRAY['idempotency_key','correlation_id','project_id','goal','constraints','expected_outputs'])
 OR (SELECT count(*) FROM jsonb_object_keys(p_request))<>6 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF jsonb_typeof(p_request->'idempotency_key')<>'string' OR jsonb_typeof(p_request->'correlation_id')<>'string' OR jsonb_typeof(p_request->'project_id')<>'string'
 OR jsonb_typeof(p_request->'goal')<>'string' OR jsonb_typeof(p_request->'constraints')<>'array' OR jsonb_typeof(p_request->'expected_outputs')<>'array' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 v_project=(p_request->>'project_id')::uuid; v_correlation=(p_request->>'correlation_id')::uuid; v_key=p_request->>'idempotency_key';
 IF v_project IS DISTINCT FROM x.project_id OR x.resource_kind<>'PROJECT' OR NOT company_private.r54_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF length(v_key) NOT BETWEEN 16 AND 128 OR v_key !~ '^[A-Za-z0-9_.:-]+$' OR length(p_request->>'goal') NOT BETWEEN 10 AND 4000
 OR jsonb_array_length(p_request->'constraints') NOT BETWEEN 1 AND 20 OR jsonb_array_length(p_request->'expected_outputs') NOT BETWEEN 1 AND 10 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 FOR element IN SELECT value FROM jsonb_array_elements((p_request->'constraints')||(p_request->'expected_outputs')) LOOP
  IF jsonb_typeof(element)<>'string' OR length(element#>>'{}') NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 END LOOP;
 -- Server-owned profile PG_JSONB_TEXT_UTF8_R53; JCS veya caller digest iddiası yok.
 -- correlation_id semantik payload dışıdır: replay ilk correlation id'yi döndürür.
 v_digest=encode(sha256(convert_to((p_request-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 -- Project authority advisory lock context enter'da alınmıştır; row lock bundan sonra.
 SELECT revision INTO STRICT v_revision FROM company.projects WHERE tenant_id=x.tenant_id AND id=v_project FOR UPDATE;
 c=company_private.r60_find_command(v_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest<>v_digest THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  IF c.r55_result_payload IS NULL OR c.r55_result_payload->>'project_revision' IS NULL THEN RAISE EXCEPTION 'BLOCKED_LEGACY_UNFINALIZED_COMMAND'; END IF;
  RETURN company_private.r55_cp_finalize_command(c.id,c.result_ref,(c.r55_result_payload->>'project_revision')::bigint,'ObjectiveCreated',c.r55_result_payload);
 END IF;
 v_id=gen_random_uuid(); v_command=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,v_command,x.principal_id,'objectives.create',v_key,v_digest,v_correlation,'RUNNING',NULL);
 INSERT INTO company.objectives(tenant_id,project_id,id,goal,constraints,expected_outputs,created_by)
 VALUES(x.tenant_id,v_project,v_id,p_request->>'goal',p_request->'constraints',p_request->'expected_outputs',x.principal_id);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=v_project AND revision=v_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT'; END IF;
 PERFORM company_private.r55_cp_finalize_command(v_command,v_id,v_revision+1,'ObjectiveCreated',jsonb_build_object('objective_id',v_id,'project_revision',v_revision+1));
 IF NOT company_private.r54_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',v_command,'correlation_id',v_correlation,'state','SUCCEEDED','result_ref',v_id);
EXCEPTION WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
WHEN INVALID_TEXT_REPRESENTATION THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_plans_create(q jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; pid uuid; parent_id uuid; rid uuid; cid uuid; correlation uuid; k text; d text; rev bigint; dep uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='plans.create';
 IF q IS NULL OR jsonb_typeof(q)<>'object' OR NOT(q ?& ARRAY['idempotency_key','correlation_id','project_id','objective_id','expected_revision','assumptions','acceptance_criteria']) OR EXISTS(SELECT 1 FROM jsonb_object_keys(q) key WHERE key<>ALL(ARRAY['idempotency_key','correlation_id','project_id','objective_id','expected_revision','assumptions','acceptance_criteria'])) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 pid=(q->>'project_id')::uuid; parent_id=(q->>'objective_id')::uuid; correlation=(q->>'correlation_id')::uuid; k=q->>'idempotency_key';
 IF pid IS DISTINCT FROM x.project_id OR x.task_id IS NOT NULL OR k IS NULL OR k !~ '^[A-Za-z0-9_.:-]{16,128}$' OR NOT company_private.r54_allowed(x.tenant_id,pid,'plans.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF jsonb_typeof(q->'acceptance_criteria') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'acceptance_criteria') NOT BETWEEN 1 AND 20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'acceptance_criteria') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 d=encode(sha256(convert_to((q-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 SELECT revision INTO STRICT rev FROM company.projects WHERE tenant_id=x.tenant_id AND id=pid FOR UPDATE;
 c=company_private.r60_find_command(k);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest<>d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  IF c.r55_result_payload IS NULL THEN RAISE EXCEPTION 'BLOCKED_LEGACY_UNFINALIZED_COMMAND'; END IF;
  RETURN company_private.r55_cp_finalize_command(c.id,c.result_ref,0,'PlanCreated',c.r55_result_payload);
 END IF;
 PERFORM 1 FROM company.objectives WHERE tenant_id=x.tenant_id AND project_id=pid AND id=parent_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'PARENT_NOT_FOUND_OR_DENIED'; END IF;
 IF jsonb_typeof(q->'expected_revision') IS DISTINCT FROM 'number' OR (q->>'expected_revision') !~ '^[0-9]+$' OR (q->>'expected_revision')::bigint<>rev THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 IF jsonb_typeof(q->'assumptions') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'assumptions')>20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'assumptions') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 rid=gen_random_uuid(); cid=gen_random_uuid();
 INSERT INTO company.plans(tenant_id,project_id,id,objective_id,revision,assumptions,acceptance_criteria) VALUES(x.tenant_id,pid,rid,parent_id,0,q->'assumptions',q->'acceptance_criteria');
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cid,x.principal_id,'plans.create',k,d,correlation,'RUNNING',NULL);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=pid AND revision=rev;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 PERFORM company_private.r55_cp_finalize_command(cid,rid,0,'PlanCreated',jsonb_build_object('resource_id',rid,'project_revision',rev+1));
 IF NOT company_private.r54_allowed(x.tenant_id,pid,'plans.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',cid,'correlation_id',correlation,'state','SUCCEEDED','result_ref',rid);
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_tasks_create(q jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; pid uuid; parent_id uuid; rid uuid; cid uuid; correlation uuid; k text; d text; rev bigint; dep uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='tasks.create';
 IF q IS NULL OR jsonb_typeof(q)<>'object' OR NOT(q ?& ARRAY['idempotency_key','correlation_id','project_id','plan_id','title','role_id','acceptance_criteria']) OR EXISTS(SELECT 1 FROM jsonb_object_keys(q) key WHERE key<>ALL(ARRAY['idempotency_key','correlation_id','project_id','plan_id','title','role_id','acceptance_criteria','depends_on'])) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 pid=(q->>'project_id')::uuid; parent_id=(q->>'plan_id')::uuid; correlation=(q->>'correlation_id')::uuid; k=q->>'idempotency_key';
 IF pid IS DISTINCT FROM x.project_id OR x.task_id IS NOT NULL OR k IS NULL OR k !~ '^[A-Za-z0-9_.:-]{16,128}$' OR NOT company_private.r54_allowed(x.tenant_id,pid,'tasks.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF jsonb_typeof(q->'acceptance_criteria') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'acceptance_criteria') NOT BETWEEN 1 AND 20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'acceptance_criteria') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 d=encode(sha256(convert_to((q-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 SELECT revision INTO STRICT rev FROM company.projects WHERE tenant_id=x.tenant_id AND id=pid FOR UPDATE;
 c=company_private.r60_find_command(k);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest<>d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  IF c.r55_result_payload IS NULL THEN RAISE EXCEPTION 'BLOCKED_LEGACY_UNFINALIZED_COMMAND'; END IF;
  RETURN company_private.r55_cp_finalize_command(c.id,c.result_ref,0,'TaskCreated',c.r55_result_payload);
 END IF;
 PERFORM 1 FROM company.plans WHERE tenant_id=x.tenant_id AND project_id=pid AND id=parent_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'PARENT_NOT_FOUND_OR_DENIED'; END IF;
 IF jsonb_typeof(q->'title') IS DISTINCT FROM 'string' OR length(q->>'title') NOT BETWEEN 3 AND 200 OR jsonb_typeof(q->'role_id') IS DISTINCT FROM 'string' OR (q->>'role_id') !~ '^(MGR|EXP)-[0-9]{2,3}$' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF q ? 'depends_on' THEN
  IF jsonb_typeof(q->'depends_on') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
  IF jsonb_array_length(q->'depends_on')>32 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'depends_on') e WHERE jsonb_typeof(e)<>'string') OR (SELECT count(*)<>count(DISTINCT value) FROM jsonb_array_elements_text(q->'depends_on')) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 END IF;
 rid=gen_random_uuid(); cid=gen_random_uuid();
 INSERT INTO company.tasks(tenant_id,project_id,id,plan_id,title,role_id,state,revision,fencing_epoch,acceptance_criteria) VALUES(x.tenant_id,pid,rid,parent_id,q->>'title',q->>'role_id','DRAFT',0,0,q->'acceptance_criteria');
 -- Existing dependency rows cannot point to a not-yet-created rid; only outgoing edges added => no cycle introduced.
 FOR dep IN SELECT value::uuid FROM jsonb_array_elements_text(COALESCE(q->'depends_on','[]'::jsonb)) ORDER BY value LOOP
  PERFORM 1 FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=pid AND id=dep;
  IF NOT FOUND THEN RAISE EXCEPTION 'DEPENDENCY_NOT_FOUND_OR_DENIED'; END IF;
  INSERT INTO company.task_dependencies(tenant_id,project_id,task_id,depends_on_task_id) VALUES(x.tenant_id,pid,rid,dep);
 END LOOP;
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cid,x.principal_id,'tasks.create',k,d,correlation,'RUNNING',NULL);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=pid AND revision=rev;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 PERFORM company_private.r55_cp_finalize_command(cid,rid,0,'TaskCreated',jsonb_build_object('resource_id',rid,'project_revision',rev+1));
 IF NOT company_private.r54_allowed(x.tenant_id,pid,'tasks.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',cid,'correlation_id',correlation,'state','SUCCEEDED','result_ref',rid);
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;

CREATE OR REPLACE FUNCTION company_private.r55_cp_persist_process_proof(p_artifact uuid,p_raw jsonb,p_envelope jsonb,p_key_material bytea,p_idempotency text,p_correlation uuid)
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
 c=company_private.r60_find_command(p_idempotency);
 IF c.id IS NOT NULL THEN
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
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_idempotency,request_digest,p_correlation,'RUNNING',NULL);
 RETURN company_private.r55_cp_finalize_command(cmd,p_artifact,0,'E0ProcessProofPersisted',jsonb_build_object('artifact_id',p_artifact,'receipt_id',rid,'profile',profile,'sha256',digest));
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'PROCESS_PROOF_CANONICAL_SOURCE_UNRESOLVED';
 WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_PROCESS_PROOF_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_PROCESS_PROOF_IDENTITY';
END $$;

CREATE OR REPLACE FUNCTION company_private.r55_cp_persist_evaluation_envelope(p_evaluation uuid,p_binding jsonb,p_envelope jsonb,p_key_material bytea,p_idempotency text,p_correlation uuid)
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
 VALUES(x.tenant_id,cid,x.principal_id,x.operation_id,p_idempotency,request_digest,p_correlation,'RUNNING',NULL);
 RETURN company_private.r55_cp_finalize_command(cid,rid,0,'E0EnvelopePersisted',jsonb_build_object('receipt_id',rid,'envelope_digest',envelope_digest,'verified_profile',en.profile_id));
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'RECEIPT_CANONICAL_SOURCE_UNRESOLVED';
 WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_RECEIPT_TYPED_BINDING';
END $$;


DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r57_replay_command(p_command uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;e company.outbox%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id;
 SELECT * INTO STRICT e FROM company.outbox WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND event_instance_id=c.id AND project_sequence=c.r55_event_sequence;
 RETURN company_private.r55_cp_finalize_command(c.id,c.result_ref,e.aggregate_revision,e.kind,c.r55_result_payload);
END $$;
ALTER FUNCTION company_private.r57_replay_command(uuid) OWNER TO company_atomic_functions_r55;
REVOKE ALL ON FUNCTION company_private.r57_replay_command(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r57_replay_command(uuid) TO company_e0_process_functions_r55;
CREATE OR REPLACE FUNCTION company_private.r55_cp_e0_process_admit(
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
 c=company_private.r60_find_command(p_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context('e0.process_admit',true,true);
  PERFORM company_private.r57_replay_command(c.id);
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
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL);
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

CREATE OR REPLACE FUNCTION company_private.r55_cp_e0_process_observe(
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
 c=company_private.r60_find_command(p_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context(p_operation,false,true);
  PERFORM company_private.r57_replay_command(c.id);
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
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL);
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

CREATE OR REPLACE FUNCTION company_private.r55_cp_e0_process_release(p_process uuid,p_expected_revision bigint,p_key text,p_correlation uuid)
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
 c=company_private.r60_find_command(p_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state<>'SUCCEEDED' THEN RAISE EXCEPTION 'CONFLICT_PROCESS_COMMAND'; END IF;
  PERFORM company_private.r54_b_context('e0.process_release',false,true);
  PERFORM company_private.r57_replay_command(c.id);
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
 VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL);
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

ROLLBACK;
