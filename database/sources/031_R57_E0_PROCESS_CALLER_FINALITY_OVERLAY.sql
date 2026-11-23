BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r57_replay_command(p_command uuid) RETURNS jsonb
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id
 AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
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
