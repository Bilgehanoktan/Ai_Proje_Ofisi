BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
GRANT SELECT ON company.audit_events,company.outbox TO company_execution_functions_r58;
CREATE POLICY r65_reply_audit_read ON company.audit_events FOR SELECT TO company_execution_functions_r58
USING(EXISTS(SELECT 1 FROM company_private.request_contexts x JOIN company.commands c ON c.tenant_id=x.tenant_id AND c.r55_project_id=x.project_id AND c.principal_id=x.principal_id AND c.operation='tool.effect' AND c.r55_audit_id=audit_events.id
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id='candidate.r58.artifacts.read' AND audit_events.tenant_id=x.tenant_id));
CREATE POLICY r65_reply_outbox_read ON company.outbox FOR SELECT TO company_execution_functions_r58
USING(EXISTS(SELECT 1 FROM company_private.request_contexts x JOIN company.commands c ON c.tenant_id=x.tenant_id AND c.r55_project_id=x.project_id AND c.principal_id=x.principal_id AND c.operation='tool.effect' AND c.id=outbox.event_instance_id AND c.r55_event_sequence=outbox.project_sequence
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id='candidate.r58.artifacts.read' AND outbox.tenant_id=x.tenant_id AND outbox.project_id=x.project_id));
CREATE POLICY r60_delivery_audit_read ON company.audit_events FOR SELECT TO company_execution_functions_r58
USING(audit_events.kind='LaunchConsumed' AND EXISTS(
 SELECT 1 FROM company_private.request_contexts x
 JOIN company.commands c ON c.tenant_id=x.tenant_id AND c.r55_project_id=x.project_id
  AND c.principal_id=x.principal_id AND c.operation='process.launch_consume' AND c.state='SUCCEEDED'
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id()
  AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id='process.launch_delivery'
  AND audit_events.tenant_id=x.tenant_id AND audit_events.actor_id=x.principal_id
  AND audit_events.id=c.r55_audit_id AND audit_events.correlation_id=c.correlation_id));
CREATE POLICY r60_delivery_outbox_read ON company.outbox FOR SELECT TO company_execution_functions_r58
USING(outbox.kind='LaunchConsumed' AND EXISTS(
 SELECT 1 FROM company_private.request_contexts x
 JOIN company.commands c ON c.tenant_id=x.tenant_id AND c.r55_project_id=x.project_id
  AND c.principal_id=x.principal_id AND c.operation='process.launch_consume' AND c.state='SUCCEEDED'
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id()
  AND x.db_login=session_user AND x.writer_generation=54 AND x.operation_id='process.launch_delivery'
  AND outbox.tenant_id=x.tenant_id AND outbox.project_id=x.project_id
  AND outbox.event_instance_id=c.id AND outbox.project_sequence=c.r55_event_sequence
  AND outbox.payload->>'result_digest'=c.r55_result_digest));
CREATE FUNCTION company_private.r65_engine_reply_guard(p_receipt uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;u company_private.r60_tool_consumptions%ROWTYPE;s company_private.r60_engine_streams%ROWTYPE;r company.process_runs%ROWTYPE;snapshot jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='candidate.r58.artifacts.read';
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'artifacts.read',x.task_id,false) IS NOT TRUE THEN RAISE EXCEPTION 'R65_REPLY_CURRENT_AUTHORITY_REQUIRED'; END IF;
 m=company_private.r58_attestation(p_receipt,'r60.tool-effect.v1');
 SELECT * INTO STRICT u FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND effect_attestation_id=m.id AND state='SUCCEEDED';
 SELECT * INTO STRICT s FROM company_private.r60_engine_streams WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=u.engine_session_id;
 r=company_private.r58_process_current(u.process_id);
 IF m.issuer_id IS DISTINCT FROM x.principal_id OR r.controller_id IS DISTINCT FROM x.principal_id
 OR s.task_id IS DISTINCT FROM x.task_id OR s.attempt_id IS DISTINCT FROM x.attempt_id OR s.fence IS DISTINCT FROM x.fencing_epoch
 OR s.next_sequence IS DISTINCT FROM u.sequence+1 OR r.state IS DISTINCT FROM 'RUNNING'
 OR m.payload->>'consume_id' IS DISTINCT FROM u.id::text OR m.payload->>'frame_digest' IS DISTINCT FROM u.frame_digest
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_execution_receipts e JOIN company.commands c ON c.tenant_id=e.tenant_id AND c.id=e.command_id
 JOIN company.audit_events a ON a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id AND a.kind=company_private.r55_cp_event_kind(c.operation)
 JOIN company.outbox ev ON ev.tenant_id=c.tenant_id AND ev.project_id=c.r55_project_id AND ev.event_instance_id=c.id AND ev.project_sequence=c.r55_event_sequence AND ev.event_writer_generation=54 AND ev.aggregate_revision=0 AND ev.aggregate_id=m.id AND ev.kind=a.kind
 WHERE e.tenant_id=x.tenant_id AND e.project_id=x.project_id AND e.operation='tool.effect' AND e.target_id=m.id AND e.payload=c.r55_result_payload AND c.principal_id=x.principal_id AND c.operation=e.operation AND c.state='SUCCEEDED' AND c.r55_project_id=x.project_id AND c.result_ref=m.id AND c.r55_source_revision='r58'
 AND c.r55_result_digest=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,c.result_ref,ev.aggregate_revision,ev.kind,c.r55_result_payload,c.r55_source_revision)::text,'UTF8')),'hex') AND ev.payload->>'result_digest'=c.r55_result_digest AND ev.payload->>'request_digest'=c.payload_digest)
 THEN RAISE EXCEPTION 'R65_REPLY_EXACT_COMMITTED_EFFECT_REQUIRED'; END IF;
 snapshot=company_private.r58_emission_snapshot();
 IF company_private.r58_emission_check(snapshot) IS NOT TRUE THEN RAISE EXCEPTION 'R65_REPLY_EMISSION_REVOKED'; END IF;
 RETURN jsonb_build_object('receipt_id',m.id,'engine_session_id',s.engine_session_id,'request_id',u.engine_request_id,'snapshot',snapshot);
END $$;
ALTER FUNCTION company_private.r65_engine_reply_guard(uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r65_engine_reply_guard(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r65_engine_reply_guard(uuid) TO company_transport_r54,company_execution_functions_r58;
ROLLBACK;
