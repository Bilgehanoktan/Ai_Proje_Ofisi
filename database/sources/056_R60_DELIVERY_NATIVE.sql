BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r60_delivery_guard(p_capability uuid,p_command uuid,p_snapshot jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;r company.process_runs%ROWTYPE;current_snapshot jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='process.launch_delivery';
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'process.launch_delivery',x.task_id,true) IS NOT TRUE THEN RAISE EXCEPTION 'R60_DELIVERY_DENIED'; END IF;
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation='process.launch_consume' AND r55_project_id=x.project_id AND state='SUCCEEDED' FOR SHARE;
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_capability AND consume_command_id=c.id AND state='CONSUMED' FOR SHARE;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=cap.process_id FOR SHARE;
 PERFORM company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);
 PERFORM company_private.r58_process_current(r.id);
 current_snapshot=company_private.r58_emission_snapshot();
 IF r.controller_id IS DISTINCT FROM x.principal_id OR r.state IS DISTINCT FROM 'STARTING' OR x.task_id IS DISTINCT FROM r.task_id OR x.attempt_id IS DISTINCT FROM r.attempt_id
 OR (current_snapshot-'operation') IS DISTINCT FROM (p_snapshot-'operation') OR p_snapshot->>'operation' IS DISTINCT FROM 'process.launch_consume'
 OR c.r55_result_payload->>'capability_id' IS DISTINCT FROM cap.id::text OR c.r55_result_payload->>'tuple_digest' IS DISTINCT FROM cap.tuple_digest OR c.r55_result_payload->>'spawn_permitted' IS DISTINCT FROM 'true'
 OR c.r55_result_payload->>'tuple_raw' IS DISTINCT FROM cap.tuple::text
 OR NOT EXISTS(SELECT 1 FROM company.audit_events WHERE tenant_id=x.tenant_id AND id=c.r55_audit_id AND actor_id=c.principal_id AND correlation_id=c.correlation_id AND kind='LaunchConsumed')
 OR NOT EXISTS(SELECT 1 FROM company.outbox WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND event_instance_id=c.id AND project_sequence=c.r55_event_sequence AND kind='LaunchConsumed' AND payload->>'result_digest'=c.r55_result_digest)
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND head_digest=cap.tuple->>'head_digest')
 THEN RAISE EXCEPTION 'R60_COMMITTED_CAPABILITY_NOT_CURRENT'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
 RETURN jsonb_build_object('command_receipt',jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref),'result',c.r55_result_payload,'snapshot',p_snapshot);
 -- Caller holds this transaction and original scope revoke locks across spawn.
END $$;
ROLLBACK;
