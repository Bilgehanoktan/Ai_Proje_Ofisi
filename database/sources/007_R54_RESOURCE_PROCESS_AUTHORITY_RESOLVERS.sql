BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r54_require_clock_health(p_tenant uuid,p_project uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'BLOCKED_TIME_DEPENDENCY'; END $$;
ALTER FUNCTION company_private.r54_require_clock_health(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_require_clock_health(uuid,uuid) FROM PUBLIC;
CREATE FUNCTION company_private.r54_allowed(p_tenant uuid,p_project uuid,p_permission text,p_task uuid,p_write boolean)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM company_private.r54_require_clock_health(p_tenant,p_project);
 RETURN company_private.r53_allowed(p_tenant,p_project,p_permission,p_task,p_write);
END $$;
ALTER FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) TO company_first_run_functions_r53;
-- Native resolver: caller lease/ProcessRun hiçbir grant yaratmaz. Önce r53 exact delegated grant + ATTEMPT context.
CREATE FUNCTION company_private.r54_resource_process_context(p_token text,p_operation text,p_project uuid,p_task uuid,p_attempt uuid,p_fence bigint,p_grant uuid,p_process uuid,p_slot uuid,p_process_revision bigint,p_claim_revision bigint)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n uuid; x company_private.request_contexts%ROWTYPE; r company.process_runs%ROWTYPE;
BEGIN
 IF p_process IS NULL OR p_process_revision IS NULL OR p_process_revision<0 THEN RAISE EXCEPTION 'PROCESS_BINDING_REQUIRED'; END IF;
 n=company_private.r53_context_enter(p_token,p_operation,p_project,'ATTEMPT',p_attempt,p_task,p_attempt,p_fence,p_grant);
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
-- TENANT/SPECIAL mevcut operation scope enumlarıdır; bu tur açık finite UNSUPPORTED_SCOPE_BLOCKED. PROJECT yetkisini büyütmez.
-- Runtime EXECUTE ve context UPDATE/RLS grantları clock ve writer fence kabulünden önce verilmez.
ROLLBACK;
