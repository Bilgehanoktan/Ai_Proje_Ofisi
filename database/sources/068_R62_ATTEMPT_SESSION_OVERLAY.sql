BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_attempt(p_task uuid,p_attempt uuid,p_fence bigint) RETURNS company.attempts
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;t company.tasks%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task FOR UPDATE;
 SELECT * INTO STRICT a FROM company.attempts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND id=p_attempt FOR UPDATE;
 IF t.execution_kind IS DISTINCT FROM 'ORDINARY' OR a.e0_evaluation_run_id IS NOT NULL OR t.active_attempt_id IS DISTINCT FROM a.id OR t.fencing_epoch IS DISTINCT FROM p_fence OR a.fencing_epoch IS DISTINCT FROM p_fence
 OR x.task_id IS DISTINCT FROM p_task OR x.attempt_id IS DISTINCT FROM p_attempt OR x.fencing_epoch IS DISTINCT FROM p_fence
 OR a.state NOT IN ('CLAIMED','RUNNING','PRODUCED') THEN RAISE EXCEPTION 'R58_STALE_ORDINARY_ATTEMPT'; END IF;
 PERFORM 1 FROM company_private.r58_lease_policies lp WHERE lp.tenant_id=x.tenant_id AND lp.project_id=x.project_id AND lp.revision=a.r58_policy_revision AND lp.enabled AND lp.verification_profile_digest=a.r58_verification_profile_digest AND company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,'-infinity'::timestamptz,lp.valid_until) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ATTEMPT_LEASE_POLICY_REVOKED'; END IF;
 PERFORM 1 FROM company_private.r58_verification_profiles vp WHERE vp.tenant_id=x.tenant_id AND vp.project_id=x.project_id AND vp.profile_digest=a.r58_verification_profile_digest AND vp.enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ATTEMPT_VERIFICATION_PROFILE_REVOKED'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,a.lease_expires_at);
 PERFORM company_private.r58_qualification(a.admission_qualification_id,a.worker_id,a.r58_binding_digest);
 PERFORM company_private.r61_worker_deadline(p_task,p_attempt);
 RETURN a;
END $$;
ROLLBACK;
