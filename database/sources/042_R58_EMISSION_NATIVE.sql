BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r58_emission_snapshot() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;h text;perm text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=x.operation_id;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,false) IS NOT TRUE THEN RAISE EXCEPTION 'R58_EMISSION_CURRENT_AUTHORITY'; END IF;
 SELECT head_digest INTO h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id;
 RETURN jsonb_build_object('tenant_id',x.tenant_id,'project_id',x.project_id,'principal_id',x.principal_id,'session_id',x.session_id,'operation',x.operation_id,'tenant_epoch',x.tenant_epoch,'project_epoch',x.project_epoch,'session_epoch',x.session_epoch,'policy_revision',x.policy_revision,'head_digest',h);
END $$;
CREATE FUNCTION company_private.r58_emission_check(p_snapshot jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 -- Native context_enter reacquires the same rank-ordered scope locks used by
 -- revoke. The socket host holds this transaction during bounded synchronous
 -- sendall; every chunk refreshes trusted time/current grant before emission.
 RETURN p_snapshot IS NOT NULL AND p_snapshot=company_private.r58_emission_snapshot();
END $$;
ROLLBACK;
