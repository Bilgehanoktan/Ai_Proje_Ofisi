BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE ROLE company_transport_r54 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company_private TO company_transport_r54;

CREATE FUNCTION company_private.r54_grant_chain(p_tenant uuid,p_project uuid,p_principal uuid,p_permission text,p_task uuid,p_leaf uuid)
RETURNS uuid[] LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE g company.project_grants%ROWTYPE; child company.project_grants%ROWTYPE;
 ids uuid[]='{}'; next_id uuid=p_leaf; first_row boolean=true;
BEGIN
 IF p_leaf IS NULL OR p_permission IS NULL OR p_permission='' OR position('*' IN p_permission)>0 THEN RAISE EXCEPTION 'GRANT_ID_REQUIRED'; END IF;
 LOOP
  IF next_id=ANY(ids) THEN RAISE EXCEPTION 'DELEGATION_CYCLE'; END IF;
  SELECT * INTO STRICT g FROM company.project_grants WHERE tenant_id=p_tenant AND project_id=p_project AND grant_id=next_id;
  IF NOT EXISTS(SELECT 1 FROM company.memberships WHERE tenant_id=p_tenant AND principal_id=g.principal_id) THEN RAISE EXCEPTION 'ANCESTOR_MEMBERSHIP_REVOKED'; END IF;
  IF g.revoked_at IS NOT NULL OR g.valid_from>clock_timestamp() OR g.valid_until<=clock_timestamp()
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
ALTER FUNCTION company_private.r54_grant_chain(uuid,uuid,uuid,text,uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_grant_chain(uuid,uuid,uuid,text,uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r54_context_enter(p_token text,p_operation text,p_project uuid,p_kind text,p_resource uuid,p_task uuid,p_attempt uuid,p_fence bigint,p_grant uuid)
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
 IF s.revoked_at IS NOT NULL OR s.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'AUTH_REVOKED'; END IF;
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
      OR a.fencing_epoch<>p_fence OR a.worker_id<>s.principal_id OR a.lease_expires_at<=clock_timestamp()
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
ALTER FUNCTION company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) TO company_transport_r54;

CREATE OR REPLACE FUNCTION company_private.r54_allowed(p_tenant uuid,p_project uuid,p_permission text,p_task uuid,p_write boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; op company_private.operation_permissions%ROWTYPE; ids uuid[];
BEGIN
 PERFORM company_private.r54_require_clock_health(p_tenant,p_project);
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user;
 SELECT * INTO STRICT op FROM company_private.operation_permissions WHERE operation_id=x.operation_id AND permission=p_permission AND scope_kind='PROJECT';
 IF x.writer_generation<>54 OR x.tenant_id<>p_tenant OR x.project_id IS DISTINCT FROM p_project
 OR x.policy_revision IS DISTINCT FROM op.policy_revision OR x.expires_at<=clock_timestamp() OR (p_write AND op.approved_policy_digest IS NULL)
 OR (x.task_id IS NOT NULL AND x.task_id IS DISTINCT FROM p_task) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.sessions s JOIN company.memberships m ON m.tenant_id=s.tenant_id AND m.principal_id=s.principal_id WHERE s.tenant_id=x.tenant_id AND s.id=x.session_id AND s.principal_id=x.principal_id AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='TENANT' AND scope_ref=x.tenant_id AND epoch=x.tenant_epoch)
 OR NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND epoch=x.project_epoch)
 OR NOT EXISTS(SELECT 1 FROM company.authority_scope_heads WHERE tenant_id=x.tenant_id AND scope_kind='SESSION' AND scope_ref=x.session_id AND epoch=x.session_epoch) THEN RETURN false; END IF;
 ids=company_private.r54_grant_chain(x.tenant_id,x.project_id,x.principal_id,p_permission,x.task_id,x.grant_id);
 IF ids IS DISTINCT FROM x.grant_chain_ids THEN RETURN false; END IF;
 IF x.attempt_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM company.attempts a JOIN company.tasks t ON t.tenant_id=a.tenant_id AND t.project_id=a.project_id AND t.id=a.task_id AND t.active_attempt_id=a.id
 WHERE a.tenant_id=x.tenant_id AND a.project_id=x.project_id AND a.task_id=x.task_id AND a.id=x.attempt_id AND a.worker_id=x.principal_id AND a.fencing_epoch=x.fencing_epoch AND t.fencing_epoch=x.fencing_epoch AND a.lease_expires_at>clock_timestamp() AND a.ended_at IS NULL AND a.state IN ('CLAIMED','RUNNING')) THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS OR RAISE_EXCEPTION THEN RETURN false;
END $$;
ALTER FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) TO company_first_run_functions_r53,company_revoke_functions_r53;

CREATE FUNCTION company_private.r54_context_exit(p_nonce uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 DELETE FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND request_nonce=p_nonce AND writer_generation=54;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONTEXT_NONCE_MISMATCH'; END IF;
END $$;
ALTER FUNCTION company_private.r54_context_exit(uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_context_exit(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_context_exit(uuid) TO company_transport_r54;

GRANT INSERT,DELETE,UPDATE ON company_private.request_contexts TO company_context_owner;
CREATE POLICY r54_context_insert ON company_private.request_contexts FOR INSERT TO company_context_owner WITH CHECK(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r54_context_delete ON company_private.request_contexts FOR DELETE TO company_context_owner USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r54_context_update ON company_private.request_contexts FOR UPDATE TO company_context_owner USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54) WITH CHECK(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
GRANT SELECT ON company_private.request_contexts TO company_first_run_functions_r53,company_revoke_functions_r53;
CREATE POLICY r54_bound_context_read ON company_private.request_contexts FOR SELECT TO company_first_run_functions_r53,company_revoke_functions_r53 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
GRANT SELECT ON company.process_runs,company.budget_reservations,company.host_registrations,company.resource_claims,company.resource_slots TO company_context_owner;
CREATE POLICY r54_context_process ON company.process_runs FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r54_context_budget ON company.budget_reservations FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r54_context_host ON company.host_registrations FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r54_context_claim ON company.resource_claims FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r54_context_slot ON company.resource_slots FOR SELECT TO company_context_owner USING(true);
GRANT EXECUTE ON FUNCTION company_private.r54_require_clock_health(uuid,uuid) TO company_first_run_functions_r53;
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
 OR r.lease_expires_at<=clock_timestamp() OR r.state NOT IN ('LEASED','REQUESTED','STARTING','RUNNING','STOP_REQUESTED') THEN RAISE EXCEPTION 'STALE_PROCESS_BINDING'; END IF;
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
ALTER FUNCTION company_private.r54_resource_process_context(text,text,uuid,uuid,uuid,bigint,uuid,uuid,uuid,bigint,bigint) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_resource_process_context(text,text,uuid,uuid,uuid,bigint,uuid,uuid,uuid,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_resource_process_context(text,text,uuid,uuid,uuid,bigint,uuid,uuid,uuid,bigint,bigint) TO company_transport_r54;

CREATE POLICY r54_tasks_read ON company.tasks FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,project_id,'tasks.read',id,false));
GRANT USAGE ON SCHEMA company,company_private TO company_first_run_functions_r53;
GRANT SELECT ON company.tasks TO company_first_run_functions_r53;
CREATE FUNCTION company_private.r54_tasks_read(p_task uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; t company.tasks%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='tasks.read';
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'tasks.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task;
 RETURN jsonb_build_object('id',t.id,'project_id',t.project_id,'title',t.title,'state',t.state,'revision',t.revision,'active_attempt_id',t.active_attempt_id);
EXCEPTION WHEN NO_DATA_FOUND THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_tasks_read(uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_tasks_read(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_tasks_read(uuid) TO company_transport_r54;
ROLLBACK;
