BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
ALTER TABLE company.commands DROP CONSTRAINT r56_command_finality_shape;
ALTER TABLE company.commands ADD CONSTRAINT r58_command_finality_shape CHECK((
 (r55_project_id IS NULL AND r55_result_payload IS NULL AND r55_result_digest IS NULL AND r55_event_sequence IS NULL AND r55_audit_id IS NULL AND r55_source_revision IS NULL)
 OR (state='SUCCEEDED' AND r55_project_id IS NOT NULL AND jsonb_typeof(r55_result_payload)='object'
 AND r55_result_digest ~ '^[a-f0-9]{64}$' AND r55_event_sequence>0 AND r55_audit_id>0 AND r55_source_revision IN ('r55-cp1','r56','r58'))) IS TRUE);
GRANT UPDATE(state,result_ref) ON company.commands TO company_atomic_functions_r55;
CREATE OR REPLACE FUNCTION company.r50_command_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.operation='trusted_setup.consume' AND OLD.state='RUNNING' AND OLD.r55_result_digest IS NULL
 AND NEW.state='SUCCEEDED' AND NEW.r55_source_revision='r56' THEN
  IF (to_jsonb(OLD)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
   IS DISTINCT FROM
   (to_jsonb(NEW)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
  OR NOT EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts x
   JOIN company_private.installation_bootstrap_control b ON b.installation_id=x.installation_id AND b.generation=x.generation
   WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user
   AND x.r56_command_id=OLD.id AND b.expected_tenant_id=OLD.tenant_id AND b.expected_human_id=OLD.principal_id
   AND b.expected_project_id=NEW.r55_project_id AND b.installation_id=NEW.result_ref
   AND b.state='ARMED' AND x.manifest_digest=OLD.payload_digest)
  THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 ELSIF OLD.operation IN ('objectives.create','plans.create','tasks.create','e0.process_proof_persist','e0.evaluation_envelope_persist','e0.process_admit','e0.process_stop_confirm','e0.process_reconcile','e0.process_release','worker.claim','worker.heartbeat','workspace.current_head','process.launch_reserve','process.launch_consume','process.launch_callback','tool.authorize_final','patch.receipt','verification.final_seal','evidence.provenance','verification.accept','evidence.attestation_ingest','process.stop_release')
 AND OLD.state='RUNNING' AND OLD.result_ref IS NULL AND OLD.r55_result_digest IS NULL
 AND NEW.state='SUCCEEDED' AND NEW.r55_source_revision IN ('r55-cp1','r58') THEN
  IF current_user<>'company_atomic_functions_r55'
  OR (to_jsonb(OLD)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
   IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
  OR NOT EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid()
   AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54
   AND x.tenant_id=OLD.tenant_id AND x.project_id=NEW.r55_project_id AND x.principal_id=OLD.principal_id AND x.operation_id=OLD.operation)
  THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 ELSE
  IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)
  OR (OLD.state IN ('SUCCEEDED','FAILED') AND ROW(OLD.state,OLD.result_ref) IS DISTINCT FROM ROW(NEW.state,NEW.result_ref))
  THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION company.r50_command_identity_immutable() FROM PUBLIC;

CREATE OR REPLACE FUNCTION company_private.r55_cp_finalize_command(p_command uuid,p_aggregate uuid,p_revision bigint,p_event_kind text,p_result_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; d text; seq bigint; aid bigint; perm text; event_payload jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 IF p_command IS NULL OR p_aggregate IS NULL OR p_revision IS NULL OR p_revision<0 OR p_result_payload IS NULL OR jsonb_typeof(p_result_payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_RESULT_BINDING'; END IF;
 IF p_event_kind IS DISTINCT FROM company_private.r55_cp_event_kind(x.operation_id) OR company_private.r55_cp_event_kind(x.operation_id) IS NULL THEN RAISE EXCEPTION 'UNREGISTERED_FINALIZER_OPERATION'; END IF;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=x.operation_id AND execution_class NOT IN ('QUERY','STREAM');
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_FINALIZE_COMMAND'; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id FOR UPDATE;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_FINALIZE_AFTER_LOCK_WAIT'; END IF;
 IF c.payload_digest IS NULL OR c.correlation_id IS NULL THEN RAISE EXCEPTION 'COMMAND_IDENTITY_INCOMPLETE'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,p_aggregate,p_revision,p_event_kind,p_result_payload,coalesce(c.r55_source_revision,'r58'))::text,'UTF8')),'hex');
 IF c.r55_result_digest IS NOT NULL THEN
  IF c.state IS DISTINCT FROM 'SUCCEEDED' OR c.result_ref IS DISTINCT FROM p_aggregate
   OR c.r55_result_digest IS DISTINCT FROM d OR c.r55_project_id IS DISTINCT FROM x.project_id
   OR c.r55_result_payload IS DISTINCT FROM p_result_payload OR c.r55_event_sequence IS NULL OR c.r55_audit_id IS NULL
   OR NOT EXISTS(SELECT 1 FROM company.audit_events a WHERE a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id AND a.kind=p_event_kind)
   OR NOT EXISTS(SELECT 1 FROM company.outbox e WHERE e.tenant_id=c.tenant_id AND e.project_id=c.r55_project_id AND e.project_sequence=c.r55_event_sequence AND e.event_instance_id=c.id AND e.event_writer_generation=54 AND e.kind=p_event_kind AND e.payload->>'result_digest'=d AND e.payload->>'request_digest'=c.payload_digest) THEN RAISE EXCEPTION 'CONFLICT_RESULT_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 IF c.state IS DISTINCT FROM 'RUNNING' OR c.result_ref IS NOT NULL THEN RAISE EXCEPTION 'UNSEALED_RUNNING_COMMAND_REQUIRED'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,c.correlation_id,x.principal_id,p_event_kind) RETURNING id INTO aid;
 event_payload=jsonb_build_object('command_id',c.id,'request_digest',c.payload_digest,'result_digest',d,'result_ref',p_aggregate,'source_revision','r58');
 seq=company_private.r55_cp_emit_event(x.tenant_id,x.project_id,c.id,p_aggregate,p_revision,p_event_kind,event_payload);
 UPDATE company.commands SET state='SUCCEEDED',result_ref=p_aggregate,r55_project_id=x.project_id,r55_result_payload=p_result_payload,r55_result_digest=d,r55_event_sequence=seq,r55_audit_id=aid,r55_source_revision='r58' WHERE tenant_id=c.tenant_id AND id=c.id AND state='RUNNING' AND result_ref IS NULL AND r55_result_digest IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_RESULT_FINALIZATION'; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_COMMAND_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'COMMAND_OR_CONTEXT_UNRESOLVED';
END $$;
ALTER FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) OWNER TO company_atomic_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) TO company_first_run_functions_r53;

CREATE FUNCTION company.r58_command_insert_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF NEW.state IS DISTINCT FROM 'RUNNING' OR NEW.result_ref IS NOT NULL OR NEW.r55_result_digest IS NOT NULL
 OR NEW.r55_project_id IS NOT NULL OR NEW.r55_result_payload IS NOT NULL OR NEW.r55_event_sequence IS NOT NULL OR NEW.r55_audit_id IS NOT NULL OR NEW.r55_source_revision IS NOT NULL THEN RAISE EXCEPTION 'R58_COMMAND_MUST_START_UNSEALED'; END IF;
 IF NEW.operation='trusted_setup.consume' THEN
  IF current_user<>'company_bootstrap_functions_r56' OR NOT EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts x JOIN company_private.installation_bootstrap_control b ON b.installation_id=x.installation_id AND b.generation=x.generation WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND b.expected_tenant_id=NEW.tenant_id AND b.expected_human_id=NEW.principal_id AND b.state='ARMED') THEN RAISE EXCEPTION 'R58_BOOTSTRAP_INSERT_CONTEXT'; END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM company_private.operation_permissions op WHERE op.operation_id=NEW.operation AND op.approved_policy_digest IS NOT NULL)
  OR NOT EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.tenant_id=NEW.tenant_id AND x.principal_id=NEW.principal_id AND x.operation_id=NEW.operation)
  OR NEW.operation NOT IN ('worker.claim','worker.heartbeat','workspace.current_head','process.launch_reserve','process.launch_consume','process.launch_callback','tool.authorize_final','patch.receipt','verification.final_seal','evidence.provenance','verification.accept','evidence.attestation_ingest','process.stop_release','objectives.create','plans.create','tasks.create','e0.process_proof_persist','e0.evaluation_envelope_persist','e0.process_admit','e0.process_stop_confirm','e0.process_reconcile','e0.process_release') THEN RAISE EXCEPTION 'R58_LEGACY_OR_UNKNOWN_COMMAND_INSERT_BLOCKED'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION company.r58_command_insert_guard() FROM PUBLIC;
CREATE TRIGGER r58_command_insert_guard BEFORE INSERT ON company.commands FOR EACH ROW EXECUTE FUNCTION company.r58_command_insert_guard();
ROLLBACK;
