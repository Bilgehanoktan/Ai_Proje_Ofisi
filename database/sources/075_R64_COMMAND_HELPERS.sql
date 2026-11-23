BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_context(p_operation text) RETURNS company_private.request_contexts
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;perm text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id=p_operation;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=p_operation AND (execution_class='COMMAND' OR (execution_class='SPECIAL' AND p_operation IN ('CAP-017.revoke','e0.setup_mandate_consume','e0.qualification_candidate_issue','e0.evaluation_artifact_record','qualification.activate','qualification.revoke'))) AND approved_policy_digest IS NOT NULL AND policy_revision=x.policy_revision;
 IF x.project_id IS NULL OR company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS NOT TRUE THEN RAISE EXCEPTION 'R58_CURRENT_AUTHORITY_REQUIRED'; END IF;
 IF p_operation IN ('CAP-017.revoke','e0.setup_mandate_consume','e0.qualification_candidate_issue','e0.evaluation_artifact_record','qualification.activate','qualification.revoke') AND p_operation<>'e0.evaluation_artifact_record' AND x.principal_kind IS DISTINCT FROM 'HUMAN' THEN RAISE EXCEPTION 'R64_ACTUAL_HUMAN_REQUIRED'; END IF;
 RETURN x;
END $$;
CREATE FUNCTION company_private.r64_begin_digest(p_key text,p_correlation uuid,p_digest text) RETURNS company.commands
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 IF p_key IS NULL OR p_key !~ '^[A-Za-z0-9_.:-]{16,128}$' OR p_correlation IS NULL OR p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'R64_COMMAND_BINDING'; END IF;
 c=company_private.r60_find_command(p_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest IS DISTINCT FROM p_digest OR c.state IS DISTINCT FROM 'SUCCEEDED' OR c.r55_result_digest IS NULL THEN RAISE EXCEPTION 'R64_IDEMPOTENCY_CONFLICT_OR_INCOMPLETE'; END IF;
  RETURN c;
 END IF;
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,gen_random_uuid(),x.principal_id,x.operation_id,p_key,p_digest,p_correlation,'RUNNING',NULL) RETURNING * INTO c;
 RETURN c;
END $$;
ALTER FUNCTION company_private.r58_context(text) OWNER TO company_execution_functions_r58;
ALTER FUNCTION company_private.r64_begin_digest(text,uuid,text) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r58_context(text),company_private.r64_begin_digest(text,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r64_begin_digest(text,uuid,text),company_private.r58_finish(uuid,uuid,jsonb),company_private.r60_finish_revision(uuid,uuid,bigint,jsonb) TO company_first_run_functions_r53,company_revoke_functions_r53;

ROLLBACK;
