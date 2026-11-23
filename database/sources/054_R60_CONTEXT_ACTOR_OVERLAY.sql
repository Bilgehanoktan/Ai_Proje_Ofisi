BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r60_attempt_actor_allowed(p_tenant uuid,p_project uuid,p_task uuid,p_attempt uuid,p_actor uuid,p_operation text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM company.attempts a WHERE a.tenant_id=p_tenant AND a.project_id=p_project AND a.task_id=p_task AND a.id=p_attempt AND
 (a.worker_id=p_actor OR
 (p_operation IN ('process.launch_consume','process.launch_callback','process.launch_delivery','engine.bind','tool.effect','process.lease_prepare','process.lease_commit','process.lease_activate','process.lease_read','evidence.attestation_ingest','candidate.r58.artifacts.read')
 AND EXISTS(SELECT 1 FROM company.process_runs r JOIN company_private.r58_controller_heads ch ON ch.tenant_id=r.tenant_id AND ch.project_id=r.project_id AND ch.controller_id=r.controller_id AND ch.generation=r.controller_generation AND ch.host_boot_id=r.r55_host_boot_id AND ch.enabled WHERE r.tenant_id=a.tenant_id AND r.project_id=a.project_id AND r.task_id=a.task_id AND r.attempt_id=a.id AND r.attempt_fencing_epoch=a.fencing_epoch AND r.controller_id=p_actor)) OR
 (p_operation IN ('verification.final_seal','evidence.provenance','verification.accept','candidate.r58.artifacts.read','evidence.attestation_ingest') AND p_actor<>a.worker_id
 AND EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=p_tenant AND id=p_actor AND kind='VERIFIER')
 AND NOT EXISTS(SELECT 1 FROM company.process_runs WHERE tenant_id=a.tenant_id AND project_id=a.project_id AND task_id=a.task_id AND attempt_id=a.id AND controller_id=p_actor))))
$$;
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
      OR (a.state NOT IN ('CLAIMED','RUNNING') AND NOT (a.state='PRODUCED' AND p_operation IN ('verification.final_seal','evidence.provenance','verification.accept','candidate.r58.artifacts.read','evidence.attestation_ingest'))) OR a.ended_at IS NOT NULL THEN RAISE EXCEPTION 'STALE_ATTEMPT'; END IF;
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
ROLLBACK;
