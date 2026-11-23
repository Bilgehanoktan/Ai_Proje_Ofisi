-- Source candidate only. Apply after r58 under the existing migration owner.
-- No grants, enrollment, approval or runtime activation are introduced here.
BEGIN;
CREATE OR REPLACE FUNCTION company_private.r58_finish(p_command uuid,p_target uuid,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;receipt jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id;
 IF c.state='SUCCEEDED' THEN
  receipt=company_private.r57_replay_command(c.id);
 ELSE
  INSERT INTO company_private.r58_execution_receipts(tenant_id,project_id,command_id,operation,target_id,payload) VALUES(x.tenant_id,x.project_id,c.id,x.operation_id,p_target,p_result);
  receipt=company_private.r55_cp_finalize_command(c.id,p_target,0,company_private.r55_cp_event_kind(x.operation_id),p_result);
 END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id;
 IF c.state IS DISTINCT FROM 'SUCCEEDED' OR jsonb_typeof(c.r55_result_payload) IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'R59_FINALIZED_RESULT_REQUIRED';
 END IF;
 -- launch_consume retains its dedicated replay branch returning no spawn permission.
 -- Domain state is nested and cannot overwrite the canonical command state.
 RETURN receipt || jsonb_build_object('result_payload',c.r55_result_payload);
END $$;
-- CREATE OR REPLACE preserves the existing r58 owner and transport ACL boundary.
ROLLBACK;
