BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r63_constructor_result(p_command uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;receipt jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 IF x.operation_id NOT IN ('objectives.create','plans.create','tasks.create') THEN RAISE EXCEPTION 'R63_CONSTRUCTOR_CONTEXT_ONLY'; END IF;
 x=company_private.r58_context(x.operation_id);
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id AND r55_project_id=x.project_id AND state='SUCCEEDED';
 -- Rechecks the immutable command digest and its actual audit/outbox witnesses.
 receipt=company_private.r57_replay_command(c.id);
 IF jsonb_typeof(c.r55_result_payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'R63_CANONICAL_RESULT_REQUIRED'; END IF;
 RETURN receipt||jsonb_build_object('result_payload',c.r55_result_payload);
END $$;
ROLLBACK;
