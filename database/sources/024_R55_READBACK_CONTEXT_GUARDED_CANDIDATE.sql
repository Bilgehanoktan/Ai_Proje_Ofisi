BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Read-only authority projection; no direct context/registry SELECT for transport.
CREATE FUNCTION company_private.r55_cp_read_authority(p_operation text,p_task uuid,p_nonce uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; op company_private.operation_permissions%ROWTYPE; allowed boolean;
BEGIN
 IF p_nonce IS NULL OR p_operation IS NULL OR p_operation NOT IN ('candidate.r54.attempts.read','candidate.r54.qualifications.read','candidate.r54.agent_runs.read','candidate.r54.tool_requests.read','candidate.r54.evidence.read','candidate.r54.acceptance_decisions.read') THEN RAISE EXCEPTION 'UNSUPPORTED_READ_AUTHORITY'; END IF;
 IF NOT pg_has_role(session_user,'company_transport_r54','MEMBER') THEN RAISE EXCEPTION 'TRANSPORT_REQUIRED'; END IF;
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND request_nonce=p_nonce AND operation_id=p_operation AND writer_generation=54;
 IF x.task_id IS DISTINCT FROM p_task THEN RAISE EXCEPTION 'READ_CONTEXT_TASK_MISMATCH'; END IF;
 SELECT * INTO STRICT op FROM company_private.operation_permissions WHERE operation_id=p_operation AND execution_class='QUERY' AND scope_kind='PROJECT';
 allowed=company_private.r54_allowed(x.tenant_id,x.project_id,op.permission,p_task,false);
 IF allowed IS DISTINCT FROM true THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 RETURN jsonb_build_object('tenant_id',x.tenant_id,'project_id',x.project_id,'principal_id',x.principal_id,'session_id',x.session_id,
 'tenant_epoch',x.tenant_epoch,'project_epoch',x.project_epoch,'session_epoch',x.session_epoch,'policy_revision',x.policy_revision,
 'writer_generation',x.writer_generation,'allowed',true);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r55_cp_read_authority(text,uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_read_authority(text,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_read_authority(text,uuid,uuid) TO company_transport_r54;
ROLLBACK;
