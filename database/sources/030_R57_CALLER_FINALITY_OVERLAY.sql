BEGIN;
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='objectives.create' AND idempotency_key=v_key;
 IF FOUND THEN
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='plans.create' AND idempotency_key=k;
 IF FOUND THEN
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='tasks.create' AND idempotency_key=k;
 IF FOUND THEN
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
ROLLBACK;
