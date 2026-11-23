BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

-- Apply after A clock helpers and r54 baseline. Does NOT replace C Objective/Plan/Task finality or B worker admission.

CREATE OR REPLACE FUNCTION company_private.r54_grant_chain(p_tenant uuid,p_project uuid,p_principal uuid,p_permission text,p_task uuid,p_leaf uuid)
RETURNS uuid[] LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g company.project_grants%ROWTYPE; child company.project_grants%ROWTYPE;
 ids uuid[]='{}'; next_id uuid=p_leaf; first_row boolean=true;
BEGIN
 IF p_leaf IS NULL OR p_permission IS NULL OR p_permission='' OR position('*' IN p_permission)>0 THEN RAISE EXCEPTION 'GRANT_ID_REQUIRED'; END IF;
 LOOP
  IF next_id=ANY(ids) THEN RAISE EXCEPTION 'DELEGATION_CYCLE'; END IF;
  SELECT * INTO STRICT g FROM company.project_grants WHERE tenant_id=p_tenant AND project_id=p_project AND grant_id=next_id;
  IF NOT EXISTS(SELECT 1 FROM company.memberships WHERE tenant_id=p_tenant AND principal_id=g.principal_id) THEN RAISE EXCEPTION 'ANCESTOR_MEMBERSHIP_REVOKED'; END IF;
  IF g.revoked_at IS NOT NULL OR g.valid_from>((company_private.r55_cp_clock_current_bounds(p_tenant,p_project)->>'utc_lower_bound')::timestamptz) OR g.valid_until<=((company_private.r55_cp_clock_current_bounds(p_tenant,p_project)->>'utc_upper_bound')::timestamptz)
     OR COALESCE(g.base_permission,g.permission)<>p_permission THEN RAISE EXCEPTION 'GRANT_NOT_CURRENT'; END IF;
  IF g.task_scope_id IS NOT NULL AND g.task_scope_id IS DISTINCT FROM p_task THEN RAISE EXCEPTION 'GRANT_WRONG_TASK'; END IF;
  IF first_row THEN
   IF g.principal_id<>p_principal THEN RAISE EXCEPTION 'GRANT_WRONG_PRINCIPAL'; END IF;
  ELSE
   IF child.granted_by<>g.principal_id OR child.valid_from<g.valid_from OR child.valid_until>g.valid_until
      OR (g.task_scope_id IS NOT NULL AND child.task_scope_id IS DISTINCT FROM g.task_scope_id)
      THEN RAISE EXCEPTION 'CHILD_EXCEEDS_PARENT'; END IF;
  END IF;
  ids=array_append(ids,g.grant_id);
  IF g.parent_grant_id IS NULL THEN RETURN ids; END IF;
  child=g; first_row=false; next_id=g.parent_grant_id;
 END LOOP;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'GRANT_CHAIN_UNRESOLVED';
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_context_enter(p_token text,p_operation text,p_project uuid,p_kind text,p_resource uuid,p_task uuid,p_attempt uuid,p_fence bigint,p_grant uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE s company.sessions%ROWTYPE; op company_private.operation_permissions%ROWTYPE;
 t company.tasks%ROWTYPE; a company.attempts%ROWTYPE; h record; ids uuid[]; nonce uuid; pk text; te bigint; pe bigint; se bigint;
BEGIN
 IF NOT pg_has_role(session_user,'company_transport_r54','MEMBER') THEN RAISE EXCEPTION 'TRANSPORT_REQUIRED'; END IF;
 IF p_token IS NULL OR octet_length(p_token)<32 OR octet_length(p_token)>4096 THEN RAISE EXCEPTION 'AUTH_REQUIRED'; END IF;
 IF EXISTS(SELECT 1 FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id()) THEN RAISE EXCEPTION 'CONTEXT_ALREADY_BOUND'; END IF;
 SELECT * INTO STRICT s FROM company.sessions WHERE token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex');
 -- Tek authority lock sırası: rank,lock_id. Revoke da aynı üç scope kilidini alır.
 FOR h IN SELECT l.lock_id,l.rank FROM company.authority_scope_heads ah JOIN company_private.scope_lock_registry l ON l.lock_id=ah.lock_id
 WHERE ah.tenant_id=s.tenant_id AND ((ah.scope_kind='TENANT' AND ah.scope_ref=s.tenant_id)
 OR (ah.scope_kind='PROJECT' AND ah.scope_ref=p_project) OR (ah.scope_kind='SESSION' AND ah.scope_ref=s.id)) ORDER BY l.rank,l.lock_id LOOP
  PERFORM pg_advisory_xact_lock(h.lock_id);
 END LOOP;
 SELECT * INTO STRICT s FROM company.sessions WHERE tenant_id=s.tenant_id AND id=s.id AND token_hash=s.token_hash;
 IF s.revoked_at IS NOT NULL OR s.expires_at<=((company_private.r55_cp_clock_current_bounds(s.tenant_id,p_project)->>'utc_upper_bound')::timestamptz) THEN RAISE EXCEPTION 'AUTH_REVOKED'; END IF;
 SELECT pr.kind INTO STRICT pk FROM company.principals pr JOIN company.memberships m ON m.tenant_id=pr.tenant_id AND m.principal_id=pr.id
 WHERE pr.tenant_id=s.tenant_id AND pr.id=s.principal_id;
 SELECT * INTO STRICT op FROM company_private.operation_permissions WHERE operation_id=p_operation;
 -- Yeni DIRECT/TASK/RESOURCE scope enum yaratılmaz. Bunlar PROJECT altındaki exact binding biçimleridir.
 IF op.scope_kind<>'PROJECT' THEN RAISE EXCEPTION 'SEPARATE_SCOPE_RESOLVER_REQUIRED'; END IF;
 IF op.approved_policy_digest IS NULL AND op.execution_class NOT IN ('QUERY','STREAM') THEN RAISE EXCEPTION 'POLICY_NOT_APPROVED'; END IF;
 IF p_project IS NULL OR p_kind IS NULL OR p_resource IS NULL OR p_kind NOT IN ('PROJECT','TASK','ATTEMPT') THEN RAISE EXCEPTION 'RESOURCE_RESOLVER_UNSUPPORTED'; END IF;
 IF p_kind='PROJECT' THEN
  IF p_resource IS DISTINCT FROM p_project OR p_task IS NOT NULL OR p_attempt IS NOT NULL OR p_fence IS NOT NULL THEN RAISE EXCEPTION 'PROJECT_BINDING_INVALID'; END IF;
  PERFORM 1 FROM company.projects WHERE tenant_id=s.tenant_id AND id=p_project;
  IF NOT FOUND THEN RAISE EXCEPTION 'RESOURCE_NOT_FOUND'; END IF;
 ELSE
  SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=s.tenant_id AND project_id=p_project AND id=p_task;
  IF p_kind='TASK' AND (p_resource IS DISTINCT FROM p_task OR p_attempt IS NOT NULL OR p_fence IS NOT NULL) THEN RAISE EXCEPTION 'TASK_BINDING_INVALID'; END IF;
  IF p_kind='ATTEMPT' THEN
   IF p_task IS NULL OR p_attempt IS NULL OR p_fence IS NULL OR p_fence<=0 THEN RAISE EXCEPTION 'ATTEMPT_BINDING_INVALID'; END IF;
   SELECT * INTO STRICT a FROM company.attempts WHERE tenant_id=s.tenant_id AND project_id=p_project AND task_id=p_task AND id=p_attempt;
   IF p_resource IS DISTINCT FROM p_attempt OR t.active_attempt_id IS DISTINCT FROM a.id OR t.fencing_epoch<>p_fence
      OR a.fencing_epoch<>p_fence OR a.worker_id<>s.principal_id OR a.lease_expires_at<=((company_private.r55_cp_clock_current_bounds(s.tenant_id,p_project)->>'utc_upper_bound')::timestamptz)
      OR a.state NOT IN ('CLAIMED','RUNNING') OR a.ended_at IS NOT NULL THEN RAISE EXCEPTION 'STALE_ATTEMPT'; END IF;
  END IF;
 END IF;
 ids=company_private.r54_grant_chain(s.tenant_id,p_project,s.principal_id,op.permission,p_task,p_grant);
 SELECT epoch INTO STRICT te FROM company.authority_scope_heads WHERE tenant_id=s.tenant_id AND scope_kind='TENANT' AND scope_ref=s.tenant_id;
 SELECT epoch INTO STRICT pe FROM company.authority_scope_heads WHERE tenant_id=s.tenant_id AND scope_kind='PROJECT' AND scope_ref=p_project;
 SELECT epoch INTO STRICT se FROM company.authority_scope_heads WHERE tenant_id=s.tenant_id AND scope_kind='SESSION' AND scope_ref=s.id;
 PERFORM company_private.r54_require_clock_health(s.tenant_id,p_project);
 nonce=gen_random_uuid();
 INSERT INTO company_private.request_contexts(backend_pid,transaction_id,request_nonce,db_login,tenant_id,project_id,principal_id,session_id,operation_id,tenant_epoch,project_epoch,session_epoch,writer_generation,authenticated_at,expires_at,grant_id,grant_chain_ids,principal_kind,resource_kind,resource_id,task_id,attempt_id,fencing_epoch,policy_revision)
 VALUES(pg_backend_pid(),pg_current_xact_id(),nonce,session_user,s.tenant_id,p_project,s.principal_id,s.id,p_operation,te,pe,se,54,clock_timestamp(),s.expires_at,p_grant,ids,pk,p_kind,p_resource,p_task,p_attempt,p_fence,op.policy_revision);
 RETURN nonce;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'AUTH_OR_RESOURCE_UNRESOLVED';
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_allowed(p_tenant uuid,p_project uuid,p_permission text,p_task uuid,p_write boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; op company_private.operation_permissions%ROWTYPE; ids uuid[];
BEGIN
 PERFORM company_private.r54_require_clock_health(p_tenant,p_project);
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user;
 SELECT * INTO STRICT op FROM company_private.operation_permissions WHERE operation_id=x.operation_id AND permission=p_permission AND scope_kind='PROJECT';
 IF x.writer_generation<>54 OR x.tenant_id<>p_tenant OR x.project_id IS DISTINCT FROM p_project
 OR x.policy_revision IS DISTINCT FROM op.policy_revision OR x.expires_at<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR (p_write AND op.approved_policy_digest IS NULL)
 OR (x.task_id IS NOT NULL AND x.task_id IS DISTINCT FROM p_task) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.sessions s JOIN company.memberships m ON m.tenant_id=s.tenant_id AND m.principal_id=s.principal_id WHERE s.tenant_id=x.tenant_id AND s.id=x.session_id AND s.principal_id=x.principal_id AND s.revoked_at IS NULL AND s.expires_at>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='TENANT' AND scope_ref=x.tenant_id AND epoch=x.tenant_epoch)
 OR NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND epoch=x.project_epoch)
 OR NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='SESSION' AND scope_ref=x.session_id AND epoch=x.session_epoch) THEN RETURN false; END IF;
 ids=company_private.r54_grant_chain(x.tenant_id,x.project_id,x.principal_id,p_permission,x.task_id,x.grant_id);
 IF ids IS DISTINCT FROM x.grant_chain_ids THEN RETURN false; END IF;
 IF x.attempt_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM company.attempts a JOIN company.tasks t ON t.tenant_id=a.tenant_id AND t.project_id=a.project_id AND t.id=a.task_id AND t.active_attempt_id=a.id
 WHERE a.tenant_id=x.tenant_id AND a.project_id=x.project_id AND a.task_id=x.task_id AND a.id=x.attempt_id AND a.worker_id=x.principal_id AND a.fencing_epoch=x.fencing_epoch AND t.fencing_epoch=x.fencing_epoch AND a.lease_expires_at>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) AND a.ended_at IS NULL AND a.state IN ('CLAIMED','RUNNING')) THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS OR RAISE_EXCEPTION THEN RETURN false;
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_resource_process_context(p_token text,p_operation text,p_project uuid,p_task uuid,p_attempt uuid,p_fence bigint,p_grant uuid,p_process uuid,p_slot uuid,p_process_revision bigint,p_claim_revision bigint)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n uuid; x company_private.request_contexts%ROWTYPE; r company.process_runs%ROWTYPE;
BEGIN
 IF p_process IS NULL OR p_process_revision IS NULL OR p_process_revision<0 THEN RAISE EXCEPTION 'PROCESS_BINDING_REQUIRED'; END IF;
 n=company_private.r54_context_enter(p_token,p_operation,p_project,'ATTEMPT',p_attempt,p_task,p_attempt,p_fence,p_grant);
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND request_nonce=n;
 PERFORM company_private.r54_require_clock_health(x.tenant_id,x.project_id);
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR SHARE;
 IF r.task_id IS DISTINCT FROM p_task OR r.attempt_id IS DISTINCT FROM p_attempt OR r.attempt_fencing_epoch IS DISTINCT FROM p_fence OR r.worker_id IS DISTINCT FROM x.principal_id OR r.revision IS DISTINCT FROM p_process_revision
 OR r.lease_expires_at<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR r.state NOT IN ('LEASED','REQUESTED','STARTING','RUNNING','STOP_REQUESTED') THEN RAISE EXCEPTION 'STALE_PROCESS_BINDING'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.tasks t JOIN company.attempts a ON a.tenant_id=t.tenant_id AND a.project_id=t.project_id AND a.task_id=t.id AND a.id=t.active_attempt_id WHERE t.tenant_id=x.tenant_id AND t.project_id=x.project_id AND t.id=r.task_id AND a.id=r.attempt_id AND a.fencing_epoch=r.attempt_fencing_epoch AND a.worker_id=r.worker_id AND a.lease_expires_at=r.lease_expires_at AND EXISTS(SELECT 1 FROM company.projects pp WHERE pp.tenant_id=r.tenant_id AND pp.id=r.project_id AND pp.workspace_id=r.workspace_id))
 THEN RAISE EXCEPTION 'PROCESS_ATTEMPT_TUPLE_MISMATCH'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.budget_reservations b WHERE b.tenant_id=r.tenant_id AND b.project_id=r.project_id AND b.id=r.reservation_id AND b.task_id=r.task_id AND b.attempt_id=r.attempt_id AND b.attempt_fencing_epoch=r.attempt_fencing_epoch AND b.state='RESERVED') THEN RAISE EXCEPTION 'BUDGET_BINDING_NOT_CURRENT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.host_registrations h JOIN company.projects p ON p.tenant_id=h.tenant_id AND p.id=h.project_id WHERE h.tenant_id=r.tenant_id AND h.project_id=r.project_id AND h.id=r.host_registration_id AND h.revision=r.host_registration_revision AND h.state='BOUND_NOT_LEASED' AND h.bound_generation=r.host_generation AND p.instance_generation=r.host_generation AND p.host_registration_id=r.host_registration_id AND p.host_registration_revision=r.host_registration_revision) THEN RAISE EXCEPTION 'HOST_GENERATION_STALE'; END IF;
 IF p_slot IS NOT NULL THEN
  IF p_claim_revision IS NULL OR NOT EXISTS(SELECT 1 FROM company.resource_claims c JOIN company.resource_slots s ON s.tenant_id=c.tenant_id AND s.id=c.slot_id WHERE c.tenant_id=r.tenant_id AND c.project_id=r.project_id AND c.process_run_id=r.id AND c.slot_id=p_slot AND c.revision=p_claim_revision AND c.state='HELD' AND c.units>0 AND s.reserved>=c.units AND s.reserved<=s.capacity) THEN RAISE EXCEPTION 'RESOURCE_CLAIM_NOT_CURRENT'; END IF;
 ELSIF p_claim_revision IS NOT NULL THEN RAISE EXCEPTION 'RESOURCE_SLOT_REQUIRED'; END IF;
 UPDATE company_private.request_contexts SET resource_kind=CASE WHEN p_slot IS NULL THEN 'PROCESS' ELSE 'RESOURCE' END,resource_id=COALESCE(p_slot,p_process) WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND request_nonce=n;
 RETURN n;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'PROCESS_RESOURCE_UNRESOLVED'; END $$;

CREATE OR REPLACE FUNCTION company_private.r54_e0_setup_mandate_consume(p_installation uuid,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; b company_private.bootstrap_receipts%ROWTYPE; e company.evaluation_runs%ROWTYPE;
 v_command uuid; v_id uuid; v_digest text; v_key text;
BEGIN
 x=company_private.r54_b_context('e0.setup_mandate_consume',true);
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=p_installation AND tenant_id=x.tenant_id AND project_id=x.project_id FOR UPDATE;
 IF b.accepted_human_id IS DISTINCT FROM x.principal_id OR b.e0_mandate IS NULL OR b.e0_valid_until IS NULL OR b.e0_valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)
 THEN RAISE EXCEPTION 'BLOCKED_SETUP_MANDATE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.installation_bootstrap_control z WHERE z.installation_id=b.installation_id AND z.state='CONSUMED' AND z.generation=b.generation AND z.consumed_command_id=b.command_id AND z.setup_manifest_digest=b.setup_manifest_digest) THEN RAISE EXCEPTION 'BLOCKED_SETUP_PROVENANCE'; END IF;
 v_digest=encode(sha256(convert_to(b.e0_mandate::text,'UTF8')),'hex');v_key='e0:'||p_installation::text;
 SELECT * INTO e FROM company.evaluation_runs WHERE e0_installation_id=p_installation;
 IF FOUND THEN RETURN jsonb_build_object('evaluation_run_id',e.id,'command_id',e.authorization_id,'outcome','REPLAY_NO_NEW_ATTEMPT'); END IF;
 v_command=gen_random_uuid();v_id=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,v_command,x.principal_id,x.operation_id,v_key,v_digest,p_correlation,'RUNNING',NULL);
 INSERT INTO company.evaluation_runs(tenant_id,project_id,id,authorization_id,role_id,fixture_digest,model_digest,source_kind,state,subject_principal_id,e0_installation_id)
 VALUES(x.tenant_id,x.project_id,v_id,v_command,b.e0_mandate->>'role_id',b.e0_mandate->>'fixture_digest',b.e0_mandate->>'model_digest','DISPOSABLE_TEST','AUTHORIZED',(b.e0_mandate->>'subject_principal_id')::uuid,p_installation);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,p_correlation,x.principal_id,'E0MandateConsumed');
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,v_id,0,'E0MandateConsumed',jsonb_build_object('evaluation_run_id',v_id,'command_id',v_command));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=v_id WHERE tenant_id=x.tenant_id AND id=v_command;
 PERFORM company_private.r54_b_context(x.operation_id,true);
 RETURN jsonb_build_object('evaluation_run_id',v_id,'command_id',v_command,'outcome','EVALUATION_AUTHORIZED_NOT_STARTED');
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_e0_evaluation_attempt_create(p_evaluation uuid,p_lease_until timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE;b company_private.bootstrap_receipts%ROWTYPE;t uuid;a uuid;v_plan uuid;
BEGIN
 x=company_private.r54_b_context('e0.evaluation_attempt_create',true);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=e.e0_installation_id;
 IF b.accepted_human_id IS DISTINCT FROM x.principal_id OR b.e0_valid_until IS NULL OR b.e0_valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR p_lease_until IS NULL OR p_lease_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR p_lease_until>b.e0_valid_until THEN RAISE EXCEPTION 'BLOCKED_SETUP_MANDATE'; END IF;
 IF e.evaluation_attempt_id IS NOT NULL THEN RETURN jsonb_build_object('task_id',e.evaluation_task_id,'attempt_id',e.evaluation_attempt_id,'outcome','REPLAY_NO_NEW_ATTEMPT'); END IF;
 IF e.state<>'AUTHORIZED' THEN RAISE EXCEPTION 'CONFLICT_EVALUATION_STATE'; END IF;
 v_plan=(b.e0_mandate->>'plan_id')::uuid;
 PERFORM 1 FROM company.plans WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=v_plan FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'BLOCKED_EVALUATION_PLAN'; END IF;
 t=gen_random_uuid();a=gen_random_uuid();
 INSERT INTO company.tasks(tenant_id,project_id,id,plan_id,title,role_id,state,revision,fencing_epoch,acceptance_criteria,execution_kind)
 VALUES(x.tenant_id,x.project_id,t,v_plan,'E0 disposable evaluation',e.role_id,'READY',0,1,jsonb_build_array('negative suite and independent evidence required'),'EVALUATION');
 INSERT INTO company.attempts(tenant_id,project_id,task_id,id,attempt_no,fencing_epoch,worker_id,state,lease_expires_at,e0_evaluation_run_id)
 VALUES(x.tenant_id,x.project_id,t,a,1,1,e.subject_principal_id,'CLAIMED',p_lease_until,e.id);
 UPDATE company.tasks SET active_attempt_id=a WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=t;
 UPDATE company.evaluation_runs SET evaluation_task_id=t,evaluation_attempt_id=a WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.id;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) SELECT x.tenant_id,c.correlation_id,x.principal_id,'E0AttemptCreated' FROM company.commands c WHERE c.tenant_id=x.tenant_id AND c.id=e.authorization_id;
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,t,0,'E0AttemptCreated',jsonb_build_object('task_id',t,'attempt_id',a,'evaluation_run_id',e.id,'ordinary_admission',false));
 PERFORM company_private.r54_b_context(x.operation_id,true);
 RETURN jsonb_build_object('task_id',t,'attempt_id',a,'outcome','EVALUATION_CLAIMED_PROCESS_NOT_STARTED');
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_qualification_current(p_qualification uuid,p_subject uuid,p_binding_digest text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;q company.agent_qualifications%ROWTYPE;h company.governance_decision_heads%ROWTYPE;
BEGIN
 x=company_private.r54_b_context('qualification.admission',false,false);
 SELECT * INTO STRICT q FROM company.agent_qualifications WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_qualification;
 IF p_subject IS NULL OR p_binding_digest IS NULL OR q.subject_principal_id IS DISTINCT FROM p_subject OR q.execution_binding_digest IS DISTINCT FROM p_binding_digest OR q.valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) THEN RAISE EXCEPTION 'DENIED_QUALIFICATION_BINDING'; END IF;
 SELECT * INTO STRICT h FROM company.governance_decision_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND decision_kind='QUALIFICATION' AND operation='qualification.activate' AND logical_target_digest=encode(sha256(convert_to(q.id::text,'UTF8')),'hex');
 IF h.decision_state<>'APPROVED' THEN RAISE EXCEPTION 'DENIED_QUALIFICATION_CURRENT_HEAD'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.artifacts a JOIN company.principals p ON p.tenant_id=a.tenant_id AND p.id=(a.r54_human_decision->>'human_id')::uuid
 WHERE a.tenant_id=x.tenant_id AND a.project_id=h.decision_project_id AND a.task_id=h.decision_task_id AND a.attempt_id=h.decision_attempt_id AND a.id=h.decision_artifact_id AND a.state='AVAILABLE' AND p.kind='HUMAN'
 AND a.r54_human_decision->>'kind'='QUALIFICATION_ACTIVATE' AND a.r54_human_decision->>'qualification_id'=q.id::text AND a.r54_human_decision->>'binding_digest'=p_binding_digest
 AND (a.r54_human_decision->>'valid_until')::timestamptz>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)) THEN RAISE EXCEPTION 'DENIED_QUALIFICATION_HUMAN_PROVENANCE'; END IF;
 RETURN jsonb_build_object('qualification_id',q.id,'subject_principal_id',q.subject_principal_id,'execution_binding_digest',q.execution_binding_digest,'head_revision',h.revision,'eligible',true,'grant_created',false,'command_receipt',NULL);
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_qualification_decide(p_qualification uuid,p_expected_revision bigint,p_decision_task uuid,p_decision_attempt uuid,p_decision_artifact uuid,p_revoke boolean,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;q company.agent_qualifications%ROWTYPE;a company.artifacts%ROWTYPE;h company.governance_decision_heads%ROWTYPE;c company.commands%ROWTYPE;
 v_op text;v_target text;v_digest text;v_cmd uuid;v_revision bigint;v_kind text;
BEGIN
 IF p_revoke IS NULL THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 v_op=CASE WHEN p_revoke THEN 'qualification.revoke' ELSE 'qualification.activate' END;
 v_kind=CASE WHEN p_revoke THEN 'QUALIFICATION_REVOKE' ELSE 'QUALIFICATION_ACTIVATE' END;
 x=company_private.r54_b_context(v_op,true);
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 OR p_expected_revision IS NULL OR p_expected_revision<0 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 SELECT * INTO STRICT q FROM company.agent_qualifications WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_qualification;
 IF q.execution_binding_digest IS NULL OR q.subject_principal_id IS NULL THEN RAISE EXCEPTION 'BLOCKED_LEGACY_QUALIFICATION'; END IF;
 SELECT * INTO STRICT a FROM company.artifacts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_decision_task AND attempt_id=p_decision_attempt AND id=p_decision_artifact AND state='AVAILABLE';
 IF NOT ((a.r54_human_decision->>'kind'=v_kind AND a.r54_human_decision->>'human_id'=x.principal_id::text
 AND a.r54_human_decision->>'qualification_id'=q.id::text AND a.r54_human_decision->>'binding_digest'=q.execution_binding_digest
 AND (a.r54_human_decision->>'valid_until')::timestamptz>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)) IS TRUE)
 OR NOT EXISTS(SELECT 1 FROM company.commands z WHERE z.tenant_id=x.tenant_id AND z.id=(a.r54_human_decision->>'command_id')::uuid AND z.principal_id=x.principal_id AND z.operation='qualification.human_decision' AND z.state='SUCCEEDED' AND z.result_ref=a.id)
 THEN RAISE EXCEPTION 'BLOCKED_EXACT_HUMAN_DECISION'; END IF;
 IF NOT p_revoke AND (q.valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR NOT EXISTS(SELECT 1 FROM company.evaluation_runs e JOIN company.evidence ev ON ev.tenant_id=e.tenant_id AND ev.project_id=e.project_id AND ev.task_id=e.evaluation_task_id AND ev.attempt_id=e.evaluation_attempt_id AND ev.id=e.sealed_evidence_id JOIN company.verification_runs vr ON vr.tenant_id=ev.tenant_id AND vr.project_id=ev.project_id AND vr.task_id=ev.task_id AND vr.attempt_id=ev.attempt_id AND vr.id=ev.verification_run_id
 WHERE e.tenant_id=q.tenant_id AND e.project_id=q.project_id AND e.id=q.evaluation_run_id AND e.execution_binding_digest=q.execution_binding_digest AND e.state='REVIEWED' AND vr.result='PASS' AND vr.exit_code=0 AND vr.producer_id<>vr.verifier_id)) THEN RAISE EXCEPTION 'BLOCKED_INDEPENDENT_EVALUATION'; END IF;
 v_target=encode(sha256(convert_to(q.id::text,'UTF8')),'hex');
 v_digest=encode(sha256(convert_to(jsonb_build_array(q.id,p_expected_revision,p_decision_task,p_decision_attempt,p_decision_artifact,p_revoke)::text,'UTF8')),'hex');
 -- Project authority lock is already held by protected context; serialize absent and present head.
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=v_op AND idempotency_key=p_key;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM v_digest THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'qualification_id',q.id,'outcome','REPLAY_NO_NEW_HEAD');
 END IF;
 SELECT * INTO h FROM company.governance_decision_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND decision_kind='QUALIFICATION' AND operation='qualification.activate' AND logical_target_digest=v_target FOR UPDATE;
 IF COALESCE(h.revision,0)<>p_expected_revision OR (p_revoke AND h.revision IS NULL) THEN RAISE EXCEPTION 'STALE_QUALIFICATION_HEAD'; END IF;
 v_revision=p_expected_revision+1;v_cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,v_cmd,x.principal_id,v_op,p_key,v_digest,p_correlation,'RUNNING',NULL);
 INSERT INTO company.governance_decision_heads(tenant_id,scope_kind,scope_ref,target_project_id,decision_kind,operation,logical_target_digest,revision,decision_state,decision_project_id,decision_task_id,decision_attempt_id,decision_artifact_id,command_id,decision_digest)
 VALUES(x.tenant_id,'PROJECT',x.project_id,x.project_id,'QUALIFICATION','qualification.activate',v_target,v_revision,CASE WHEN p_revoke THEN 'REVOKED' ELSE 'APPROVED' END,x.project_id,p_decision_task,p_decision_attempt,p_decision_artifact,v_cmd,a.sha256)
 ON CONFLICT(tenant_id,scope_kind,scope_ref,decision_kind,operation,logical_target_digest) DO UPDATE SET revision=EXCLUDED.revision,decision_state=EXCLUDED.decision_state,decision_project_id=EXCLUDED.decision_project_id,decision_task_id=EXCLUDED.decision_task_id,decision_attempt_id=EXCLUDED.decision_attempt_id,decision_artifact_id=EXCLUDED.decision_artifact_id,command_id=EXCLUDED.command_id,decision_digest=EXCLUDED.decision_digest WHERE company.governance_decision_heads.revision=p_expected_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_QUALIFICATION_HEAD'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,p_correlation,x.principal_id,v_kind);
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,q.id,v_revision,v_kind,jsonb_build_object('qualification_id',q.id,'head_revision',v_revision,'command_id',v_cmd));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=q.id WHERE tenant_id=x.tenant_id AND id=v_cmd;
 PERFORM company_private.r54_b_context(v_op,true);
 RETURN jsonb_build_object('qualification_id',q.id,'command_id',v_cmd,'head_revision',v_revision,'outcome',CASE WHEN p_revoke THEN 'REVOKED' ELSE 'ACTIVATED_NO_GRANT' END);
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_evaluation_verification_seal(p_evaluation uuid,p_binding jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE;v company.verification_runs%ROWTYPE;ev company.evidence%ROWTYPE;a company.artifacts%ROWTYPE;d text; r company.verifier_receipts%ROWTYPE; env company.internal_receipt_envelopes%ROWTYPE; rep jsonb;
BEGIN
 x=company_private.r54_b_context('e0.evaluation_verification_seal',false);
 PERFORM company_private.r54_schema_check(p_binding,'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"schema_version":{"const":"r53.execution-binding.v1"},"subject_principal_id":{"type":"string","format":"uuid"},"role_definition":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"agent_profile":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"model":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"engine":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"tools":{"type":"array","items":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"minItems":1,"uniqueItems":true},"suite":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"policy":{"type":"object","properties":{"identity":{"type":"string","minLength":1},"revision":{"type":"integer","minimum":1},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["identity","revision","sha256"],"additionalProperties":false},"resource_scope":{"type":"object","properties":{"tenant_id":{"type":"string","format":"uuid"},"project_id":{"type":"string","format":"uuid"},"workspace_id":{"type":"string","format":"uuid"}},"required":["tenant_id","project_id","workspace_id"],"additionalProperties":false},"independent_evidence":{"type":"object","properties":{"task_id":{"type":"string","format":"uuid"},"attempt_id":{"type":"string","format":"uuid"},"evidence_id":{"type":"string","format":"uuid"},"verification_run_id":{"type":"string","format":"uuid"},"producer_id":{"type":"string","format":"uuid"},"verifier_id":{"type":"string","format":"uuid"},"artifact_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["task_id","attempt_id","evidence_id","verification_run_id","producer_id","verifier_id","artifact_sha256"],"additionalProperties":false},"source_revision":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["schema_version","subject_principal_id","role_definition","agent_profile","model","engine","tools","suite","policy","resource_scope","independent_evidence","source_revision"],"additionalProperties":false}'::jsonb);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 IF p_binding IS NULL OR jsonb_typeof(p_binding)<>'object' OR NOT(p_binding ?& ARRAY['schema_version','subject_principal_id','role_definition','agent_profile','model','engine','tools','suite','policy','resource_scope','independent_evidence','source_revision']) THEN RAISE EXCEPTION 'INVALID_SEALED_BINDING'; END IF;
 IF NOT((p_binding->>'schema_version'='r53.execution-binding.v1' AND p_binding->>'subject_principal_id'=e.subject_principal_id::text AND p_binding#>>'{role_definition,identity}'=e.role_id AND p_binding#>>'{model,sha256}'=e.model_digest AND p_binding#>>'{suite,sha256}'=e.fixture_digest AND p_binding#>>'{resource_scope,tenant_id}'=x.tenant_id::text AND p_binding#>>'{resource_scope,project_id}'=x.project_id::text AND p_binding#>>'{resource_scope,workspace_id}'=(SELECT br.e0_mandate->>'workspace_id' FROM company_private.bootstrap_receipts br WHERE br.installation_id=e.e0_installation_id) AND p_binding#>>'{agent_profile,sha256}'=(SELECT br.e0_mandate->>'profile_digest' FROM company_private.bootstrap_receipts br WHERE br.installation_id=e.e0_installation_id)) IS TRUE) THEN RAISE EXCEPTION 'INVALID_SEALED_BINDING'; END IF;
 SELECT * INTO STRICT ev FROM company.evidence WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=e.evaluation_task_id AND attempt_id=e.evaluation_attempt_id AND id=(p_binding#>>'{independent_evidence,evidence_id}')::uuid;
 SELECT * INTO STRICT v FROM company.verification_runs WHERE tenant_id=ev.tenant_id AND project_id=ev.project_id AND task_id=ev.task_id AND attempt_id=ev.attempt_id AND id=ev.verification_run_id;
 SELECT * INTO STRICT a FROM company.artifacts WHERE tenant_id=ev.tenant_id AND project_id=ev.project_id AND task_id=ev.task_id AND attempt_id=ev.attempt_id AND id=ev.artifact_id;
 IF NOT((v.result='PASS' AND v.exit_code=0 AND v.producer_id<>v.verifier_id AND v.verifier_id=x.principal_id AND v.producer_id=e.subject_principal_id
 AND a.state='AVAILABLE' AND a.sha256=p_binding#>>'{independent_evidence,artifact_sha256}'
 AND v.id::text=p_binding#>>'{independent_evidence,verification_run_id}' AND v.producer_id::text=p_binding#>>'{independent_evidence,producer_id}' AND v.verifier_id::text=p_binding#>>'{independent_evidence,verifier_id}'
 AND ev.task_id::text=p_binding#>>'{independent_evidence,task_id}' AND ev.attempt_id::text=p_binding#>>'{independent_evidence,attempt_id}') IS TRUE) THEN RAISE EXCEPTION 'DENIED_INDEPENDENT_EVIDENCE'; END IF;
 rep=a.r54_evaluation_report;
 PERFORM company_private.r54_schema_check(rep,'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"profile":{"const":"r54.evaluation-report.pg-jsonb.v1"},"receipt_id":{"type":"string","format":"uuid"},"subject_principal_id":{"type":"string","format":"uuid"},"model_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"fixture_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"negative_suite_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"positive_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}},"negative_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}}},"required":["profile","receipt_id","subject_principal_id","model_digest","fixture_digest","negative_suite_digest","positive_cases","negative_cases"],"additionalProperties":false}'::jsonb);
 IF NOT((jsonb_typeof(rep)='object' AND rep->>'profile'='r54.evaluation-report.pg-jsonb.v1'
 AND rep->>'model_digest'=e.model_digest AND rep->>'fixture_digest'=e.fixture_digest
 AND rep->>'subject_principal_id'=e.subject_principal_id::text
 AND rep->>'negative_suite_digest'=(SELECT b.e0_mandate->>'negative_suite_digest' FROM company_private.bootstrap_receipts b WHERE b.installation_id=e.e0_installation_id)
 AND jsonb_typeof(rep->'positive_cases')='array' AND jsonb_array_length(rep->'positive_cases')>0
 AND jsonb_typeof(rep->'negative_cases')='array' AND jsonb_array_length(rep->'negative_cases')>0
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements((rep->'positive_cases')||(rep->'negative_cases')) c WHERE NOT((jsonb_typeof(c)='object' AND c->>'oracle_id'<>'' AND c->>'result'='PASS' AND c->>'observed_digest' ~ '^[a-f0-9]{64}$') IS TRUE))
 AND (SELECT jsonb_agg(z->>'oracle_id' ORDER BY z->>'oracle_id') FROM jsonb_array_elements(rep->'positive_cases') z)=(SELECT jsonb_agg(z ORDER BY z) FROM company_private.bootstrap_receipts br,jsonb_array_elements(br.e0_mandate->'required_positive_oracle_ids') z WHERE br.installation_id=e.e0_installation_id)
 AND (SELECT jsonb_agg(z->>'oracle_id' ORDER BY z->>'oracle_id') FROM jsonb_array_elements(rep->'negative_cases') z)=(SELECT jsonb_agg(z ORDER BY z) FROM company_private.bootstrap_receipts br,jsonb_array_elements(br.e0_mandate->'required_negative_oracle_ids') z WHERE br.installation_id=e.e0_installation_id)
 AND (SELECT count(*)=count(DISTINCT z->>'oracle_id') FROM jsonb_array_elements((rep->'positive_cases')||(rep->'negative_cases')) z)
 AND encode(sha256(convert_to(rep::text,'UTF8')),'hex')=a.sha256) IS TRUE) THEN RAISE EXCEPTION 'DENIED_EVALUATION_SUITE_REPORT'; END IF;
 SELECT * INTO STRICT r FROM company.verifier_receipts WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND task_id=e.evaluation_task_id AND attempt_id=e.evaluation_attempt_id AND id=(rep->>'receipt_id')::uuid AND purpose='EVALUATION' AND signer_id=v.verifier_id;
 SELECT * INTO STRICT env FROM company.internal_receipt_envelopes WHERE tenant_id=r.tenant_id AND receipt_id=r.id AND purpose='EVALUATION' AND issuer_id=r.signer_id AND key_id=r.key_id;
 d=encode(sha256(convert_to(p_binding::text,'UTF8')),'hex');
 IF env.expected_binding_digest IS DISTINCT FROM d OR env.canonical_artifact_digest IS DISTINCT FROM a.sha256 OR env.profile_id<>'r54.evaluation-report.pg-jsonb.v1'
 OR env.auth_tag IS DISTINCT FROM r.signature OR env.envelope_digest IS DISTINCT FROM r.receipt_digest
 OR NOT EXISTS(SELECT 1 FROM company.signer_enrollments en JOIN company.principals hp ON hp.tenant_id=en.tenant_id AND hp.id=en.approved_by AND hp.kind='HUMAN'
 WHERE en.tenant_id=env.tenant_id AND en.issuer_id=env.issuer_id AND en.key_id=env.key_id AND en.purpose='EVALUATION' AND en.profile_id=env.profile_id AND en.enrollment_revision=env.enrollment_revision
 AND en.valid_from<=env.verified_at AND en.valid_until>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) AND company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,en.valid_from,en.valid_until) IS TRUE AND en.revoked_at IS NULL AND en.compromised_since IS NULL AND en.secret_ref<>'' AND en.key_fingerprint ~ '^[a-f0-9]{64}$') THEN RAISE EXCEPTION 'DENIED_EVALUATION_SIGNER_PROVENANCE'; END IF;
 IF e.execution_binding_digest IS NOT NULL THEN
  IF e.execution_binding_digest IS DISTINCT FROM d THEN RAISE EXCEPTION 'CONFLICT_IMMUTABLE_EVALUATION_SEAL'; END IF;
  RETURN jsonb_build_object('evaluation_run_id',e.id,'outcome','REPLAY_SEAL_NO_QUALIFICATION');
 END IF;
 IF e.state NOT IN ('AUTHORIZED','RUNNING','MEASURED') THEN RAISE EXCEPTION 'CONFLICT_EVALUATION_STATE'; END IF;
 UPDATE company.evaluation_runs SET execution_binding=p_binding,execution_binding_digest=d,sealed_evidence_id=ev.id,sealed_verification_id=v.id,sealed_artifact_id=a.id,state='REVIEWED' WHERE tenant_id=e.tenant_id AND project_id=e.project_id AND id=e.id AND execution_binding_digest IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_IMMUTABLE_EVALUATION_SEAL'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) SELECT x.tenant_id,c.correlation_id,x.principal_id,'E0EvaluationSealed' FROM company.commands c WHERE c.tenant_id=e.tenant_id AND c.id=e.authorization_id;
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,e.id,1,'E0EvaluationSealed',jsonb_build_object('evaluation_run_id',e.id,'binding_digest',d,'evidence_id',ev.id,'qualification_created',false));
 PERFORM company_private.r54_b_context(x.operation_id,false);
 RETURN jsonb_build_object('evaluation_run_id',e.id,'binding_digest',d,'outcome','SEALED_NOT_QUALIFIED');
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_qualification_candidate_issue(p_evaluation uuid,p_valid_until timestamptz,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE;c company.commands%ROWTYPE;v uuid;cmd uuid;d text;
BEGIN
 x=company_private.r54_b_context('e0.qualification_candidate_issue',true);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 IF e.state<>'REVIEWED' OR e.execution_binding IS NULL OR e.execution_binding_digest IS NULL OR e.sealed_evidence_id IS NULL OR p_valid_until IS NULL OR p_valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) THEN RAISE EXCEPTION 'BLOCKED_REVIEWED_EVALUATION'; END IF;
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.bootstrap_receipts b WHERE b.installation_id=e.e0_installation_id AND b.e0_valid_until>=p_valid_until AND b.accepted_human_id=x.principal_id) THEN RAISE EXCEPTION 'BLOCKED_QUALIFICATION_VALIDITY_CEILING'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(e.id,e.execution_binding_digest,p_valid_until)::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key;
 IF FOUND THEN
  IF c.payload_digest IS DISTINCT FROM d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('qualification_id',c.result_ref,'command_id',c.id,'outcome','REPLAY_NO_ACTIVATION');
 END IF;
 v=gen_random_uuid();cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL);
 INSERT INTO company.agent_qualifications(tenant_id,project_id,id,evaluation_run_id,role_id,version_binding,approved_by,valid_until,subject_principal_id,execution_binding_digest,evaluation_task_id,evaluation_attempt_id,evaluation_evidence_id)
 VALUES(x.tenant_id,x.project_id,v,e.id,e.role_id,e.execution_binding,x.principal_id,p_valid_until,e.subject_principal_id,e.execution_binding_digest,e.evaluation_task_id,e.evaluation_attempt_id,e.sealed_evidence_id);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,p_correlation,x.principal_id,'QualificationCandidateIssued');
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,v,0,'QualificationCandidateIssued',jsonb_build_object('qualification_id',v,'command_id',cmd,'active',false));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=v WHERE tenant_id=x.tenant_id AND id=cmd;
 PERFORM company_private.r54_b_context(x.operation_id,true);
 RETURN jsonb_build_object('qualification_id',v,'command_id',cmd,'outcome','CANDIDATE_NOT_ACTIVE','grant_created',false);
END $$;

CREATE OR REPLACE FUNCTION company_private.r54_e0_evaluation_artifact_record(p_evaluation uuid,p_report jsonb,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE; c company.commands%ROWTYPE; a uuid; cmd uuid;d text;n bigint;
BEGIN
 x=company_private.r54_b_context('e0.evaluation_artifact_record',false);
 PERFORM company_private.r54_schema_check(p_report,'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"profile":{"const":"r54.evaluation-report.pg-jsonb.v1"},"receipt_id":{"type":"string","format":"uuid"},"subject_principal_id":{"type":"string","format":"uuid"},"model_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"fixture_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"negative_suite_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"positive_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}},"negative_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}}},"required":["profile","receipt_id","subject_principal_id","model_digest","fixture_digest","negative_suite_digest","positive_cases","negative_cases"],"additionalProperties":false}'::jsonb);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 IF e.subject_principal_id IS DISTINCT FROM x.principal_id OR e.state NOT IN ('AUTHORIZED','RUNNING','MEASURED') OR NOT EXISTS(SELECT 1 FROM company.attempts at JOIN company.tasks t ON t.tenant_id=at.tenant_id AND t.project_id=at.project_id AND t.id=at.task_id WHERE at.tenant_id=e.tenant_id AND at.project_id=e.project_id AND at.task_id=e.evaluation_task_id AND at.id=e.evaluation_attempt_id AND at.worker_id=x.principal_id AND at.lease_expires_at>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) AND at.ended_at IS NULL AND t.execution_kind='EVALUATION' AND t.active_attempt_id=at.id AND t.fencing_epoch=at.fencing_epoch) THEN RAISE EXCEPTION 'DENIED_EVALUATION_ATTEMPT'; END IF;
 IF p_report IS NULL OR jsonb_typeof(p_report)<>'object' OR p_report->>'profile' IS DISTINCT FROM 'r54.evaluation-report.pg-jsonb.v1' OR p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 n=octet_length(convert_to(p_report::text,'UTF8'));IF n>65536 THEN RAISE EXCEPTION 'EVALUATION_REPORT_TOO_LARGE'; END IF;
 d=encode(sha256(convert_to(p_report::text,'UTF8')),'hex');
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key;
 IF FOUND THEN IF c.payload_digest IS DISTINCT FROM d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;RETURN jsonb_build_object('artifact_id',c.result_ref,'command_id',c.id,'outcome','REPLAY_STORED_REPORT');END IF;
 a=gen_random_uuid();cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cmd,x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL);
 -- JSONB is the persisted payload; this bounded report is not an external blob-store availability assertion.
 INSERT INTO company.artifacts(tenant_id,project_id,task_id,attempt_id,id,storage_key,sha256,size_bytes,state,r54_evaluation_report) VALUES(x.tenant_id,x.project_id,e.evaluation_task_id,e.evaluation_attempt_id,a,gen_random_uuid(),d,n,'AVAILABLE',p_report);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,p_correlation,x.principal_id,'E0ReportRecorded');
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,a,0,'E0ReportRecorded',jsonb_build_object('artifact_id',a,'sha256',d,'command_id',cmd));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=a WHERE tenant_id=x.tenant_id AND id=cmd;
 PERFORM company_private.r54_b_context(x.operation_id,false);
 RETURN jsonb_build_object('artifact_id',a,'sha256',d,'command_id',cmd,'outcome','REPORT_RECORDED_NOT_VERIFIED');
END $$;

ROLLBACK;
