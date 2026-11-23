BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
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
 WHERE a.tenant_id=x.tenant_id AND a.project_id=x.project_id AND a.task_id=x.task_id AND a.id=x.attempt_id AND company_private.r60_attempt_actor_allowed(x.tenant_id,x.project_id,x.task_id,x.attempt_id,x.principal_id,x.operation_id) IS TRUE AND a.fencing_epoch=x.fencing_epoch AND t.fencing_epoch=x.fencing_epoch AND a.lease_expires_at>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) AND a.ended_at IS NULL AND (a.state IN ('CLAIMED','RUNNING') OR (a.state='PRODUCED' AND x.operation_id IN ('patch.receipt','verification.final_seal','evidence.provenance','verification.accept','candidate.r58.artifacts.read','evidence.attestation_ingest')))) THEN RETURN false; END IF;
 RETURN true;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS OR RAISE_EXCEPTION THEN RETURN false;
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
      OR a.fencing_epoch<>p_fence OR company_private.r60_attempt_actor_allowed(s.tenant_id,p_project,p_task,p_attempt,s.principal_id,p_operation) IS NOT TRUE OR a.lease_expires_at<=((company_private.r55_cp_clock_current_bounds(s.tenant_id,p_project)->>'utc_upper_bound')::timestamptz)
      OR (a.state NOT IN ('CLAIMED','RUNNING') AND NOT (a.state='PRODUCED' AND p_operation IN ('patch.receipt','verification.final_seal','evidence.provenance','verification.accept','candidate.r58.artifacts.read','evidence.attestation_ingest'))) OR a.ended_at IS NOT NULL THEN RAISE EXCEPTION 'STALE_ATTEMPT'; END IF;
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
ALTER FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) OWNER TO company_context_owner;
ALTER FUNCTION company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean),company_private.r54_context_enter(text,text,uuid,text,uuid,uuid,uuid,bigint,uuid) FROM PUBLIC;

ROLLBACK;
