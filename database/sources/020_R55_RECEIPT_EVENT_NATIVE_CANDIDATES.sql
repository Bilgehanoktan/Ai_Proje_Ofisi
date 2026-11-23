BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Overlay after r54 assembly. Existing canonical commands/audit_events/outbox;
-- no second ledger, dispatcher, or fabricated cryptographic receipt.
CREATE ROLE company_atomic_functions_r55 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_atomic_functions_r55;
ALTER TABLE company.commands ADD COLUMN r55_project_id uuid;
ALTER TABLE company.commands ADD COLUMN r55_result_payload jsonb;
ALTER TABLE company.commands ADD COLUMN r55_result_digest text;
ALTER TABLE company.commands ADD COLUMN r55_event_sequence bigint;
ALTER TABLE company.commands ADD COLUMN r55_audit_id bigint;
ALTER TABLE company.commands ADD COLUMN r55_source_revision text;
ALTER TABLE company.commands ADD CONSTRAINT r55_command_project_fk FOREIGN KEY(tenant_id,r55_project_id) REFERENCES company.projects(tenant_id,id);
ALTER TABLE company.commands ADD CONSTRAINT r55_command_finality_shape CHECK((
 (r55_project_id IS NULL AND r55_result_payload IS NULL AND r55_result_digest IS NULL AND r55_event_sequence IS NULL AND r55_audit_id IS NULL AND r55_source_revision IS NULL)
 OR (state='SUCCEEDED' AND r55_project_id IS NOT NULL AND r55_result_payload IS NOT NULL AND jsonb_typeof(r55_result_payload)='object'
 AND r55_result_digest IS NOT NULL AND r55_result_digest ~ '^[a-f0-9]{64}$' AND r55_event_sequence>0
 AND r55_event_sequence IS NOT NULL AND r55_audit_id IS NOT NULL AND r55_audit_id>0 AND r55_source_revision IS NOT NULL AND r55_source_revision='r55-cp1')) IS TRUE);
GRANT SELECT,UPDATE(r55_project_id,r55_result_payload,r55_result_digest,r55_event_sequence,r55_audit_id,r55_source_revision) ON company.commands TO company_atomic_functions_r55;
GRANT SELECT,INSERT ON company.outbox TO company_atomic_functions_r55;
GRANT SELECT,UPDATE ON company.project_event_heads TO company_atomic_functions_r55;
GRANT SELECT,INSERT ON company.audit_events TO company_atomic_functions_r55;
GRANT SELECT ON company_private.request_contexts,company_private.operation_permissions TO company_atomic_functions_r55;
GRANT USAGE ON SEQUENCE company.outbox_event_id_seq,company.audit_events_id_seq TO company_atomic_functions_r55;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) TO company_atomic_functions_r55;
CREATE POLICY r55_atomic_context ON company_private.request_contexts FOR SELECT TO company_atomic_functions_r55
 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r55_atomic_registry ON company_private.operation_permissions FOR SELECT TO company_atomic_functions_r55 USING(true);
CREATE POLICY r55_atomic_commands ON company.commands TO company_atomic_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.project_id=commands.r55_project_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND x.writer_generation=54));
CREATE POLICY r55_atomic_outbox ON company.outbox TO company_atomic_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=outbox.tenant_id AND x.project_id=outbox.project_id AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=outbox.tenant_id AND x.project_id=outbox.project_id AND x.writer_generation=54));
CREATE POLICY r55_atomic_head ON company.project_event_heads TO company_atomic_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=project_event_heads.tenant_id AND x.project_id=project_event_heads.project_id AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=project_event_heads.tenant_id AND x.project_id=project_event_heads.project_id AND x.writer_generation=54));
CREATE POLICY r55_atomic_audit ON company.audit_events TO company_atomic_functions_r55
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id AND x.writer_generation=54))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id AND x.writer_generation=54));

CREATE FUNCTION company_private.r55_cp_event_kind(p_operation text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT CASE p_operation
 WHEN 'e0.process_admit' THEN 'E0ProcessAdmitted'
 WHEN 'e0.process_stop_confirm' THEN 'E0ProcessStopConfirmed'
 WHEN 'e0.process_release' THEN 'E0ProcessReleased'
 WHEN 'e0.process_reconcile' THEN 'E0ProcessReconciled'
 WHEN 'e0.evaluation_envelope_persist' THEN 'E0EnvelopePersisted'
 WHEN 'e0.process_proof_persist' THEN 'E0ProcessProofPersisted'
 WHEN 'plans.create' THEN 'PlanCreated'
 WHEN 'tasks.create' THEN 'TaskCreated'
 WHEN 'objectives.create' THEN 'ObjectiveCreated'
 END;
$$;
REVOKE ALL ON FUNCTION company_private.r55_cp_event_kind(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_event_kind(text) TO company_atomic_functions_r55,company_first_run_functions_r53;

CREATE FUNCTION company_private.r55_cp_emit_event(p_tenant uuid,p_project uuid,p_event uuid,p_aggregate uuid,p_revision bigint,p_kind text,p_payload jsonb)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; h company.project_event_heads%ROWTYPE; e company.outbox%ROWTYPE; d text; n bigint; perm text; expected_kind text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 IF x.tenant_id IS DISTINCT FROM p_tenant OR x.project_id IS DISTINCT FROM p_project OR p_event IS NULL OR p_aggregate IS NULL OR p_revision IS NULL OR p_revision<0 OR p_payload IS NULL OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_EVENT_BINDING'; END IF;
 expected_kind=company_private.r55_cp_event_kind(x.operation_id);
 IF expected_kind IS NULL OR p_kind IS DISTINCT FROM expected_kind THEN RAISE EXCEPTION 'EVENT_PRODUCER_KIND_MISMATCH'; END IF;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=x.operation_id AND execution_class NOT IN ('QUERY','STREAM');
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_EVENT_COMMIT'; END IF;
 SELECT * INTO STRICT h FROM company.project_event_heads WHERE tenant_id=p_tenant AND project_id=p_project FOR UPDATE;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_EVENT_AFTER_LOCK_WAIT'; END IF;
 IF h.writer_generation IS DISTINCT FROM 54 THEN RAISE EXCEPTION 'OLD_EVENT_WRITER_FENCED'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(p_aggregate,p_revision,p_kind,p_payload)::text,'UTF8')),'hex');
 SELECT * INTO e FROM company.outbox WHERE tenant_id=p_tenant AND project_id=p_project AND event_instance_id=p_event;
 IF FOUND THEN
  IF e.event_digest IS DISTINCT FROM d OR e.event_writer_generation IS DISTINCT FROM 54 OR e.project_sequence IS NULL OR e.project_sequence>h.committed_sequence THEN RAISE EXCEPTION 'CONFLICT_EVENT_DIGEST'; END IF;
  RETURN e.project_sequence;
 END IF;
 n=h.committed_sequence+1;
 INSERT INTO company.outbox(tenant_id,project_id,aggregate_id,aggregate_revision,kind,payload,project_sequence,event_writer_generation,event_instance_id,event_digest)
 VALUES(p_tenant,p_project,p_aggregate,p_revision,p_kind,p_payload,n,54,p_event,d);
 UPDATE company.project_event_heads SET committed_sequence=n WHERE tenant_id=p_tenant AND project_id=p_project AND committed_sequence=h.committed_sequence AND writer_generation=54;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_EVENT_HEAD'; END IF;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_EVENT_RETURN_CUT'; END IF;
 RETURN n;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'EVENT_HEAD_OR_CONTEXT_NOT_MIGRATED';
END $$;
ALTER FUNCTION company_private.r55_cp_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb) OWNER TO company_atomic_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb) FROM PUBLIC;
-- Only canonical domain owner may call. No transport/client direct EXECUTE.
GRANT EXECUTE ON FUNCTION company_private.r55_cp_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb) TO company_first_run_functions_r53;

CREATE FUNCTION company_private.r55_cp_finalize_command(p_command uuid,p_aggregate uuid,p_revision bigint,p_event_kind text,p_result_payload jsonb)
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
 IF c.state IS DISTINCT FROM 'SUCCEEDED' OR c.result_ref IS DISTINCT FROM p_aggregate OR c.payload_digest IS NULL OR c.correlation_id IS NULL THEN RAISE EXCEPTION 'COMMAND_NOT_CANONICAL_SUCCESS'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,c.result_ref,p_revision,p_event_kind,p_result_payload,'r55-cp1')::text,'UTF8')),'hex');
 IF c.r55_result_digest IS NOT NULL THEN
  IF c.r55_result_digest IS DISTINCT FROM d OR c.r55_project_id IS DISTINCT FROM x.project_id OR c.r55_event_sequence IS NULL OR c.r55_audit_id IS NULL THEN RAISE EXCEPTION 'CONFLICT_RESULT_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,c.correlation_id,x.principal_id,p_event_kind) RETURNING id INTO aid;
 event_payload=jsonb_build_object('command_id',c.id,'request_digest',c.payload_digest,'result_digest',d,'result_ref',c.result_ref,'source_revision','r55-cp1');
 seq=company_private.r55_cp_emit_event(x.tenant_id,x.project_id,c.id,p_aggregate,p_revision,p_event_kind,event_payload);
 UPDATE company.commands SET r55_project_id=x.project_id,r55_result_payload=p_result_payload,r55_result_digest=d,r55_event_sequence=seq,r55_audit_id=aid,r55_source_revision='r55-cp1' WHERE tenant_id=c.tenant_id AND id=c.id AND r55_result_digest IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_RESULT_FINALIZATION'; END IF;
 IF company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) IS DISTINCT FROM true THEN RAISE EXCEPTION 'DENIED_COMMAND_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'COMMAND_OR_CONTEXT_UNRESOLVED';
END $$;
ALTER FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) OWNER TO company_atomic_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_finalize_command(uuid,uuid,bigint,text,jsonb) TO company_first_run_functions_r53;

CREATE FUNCTION company_private.r55_cp_result_immutable() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.r55_result_digest IS NOT NULL THEN RAISE EXCEPTION 'IMMUTABLE_CANONICAL_COMMAND_RESULT'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION company_private.r55_cp_result_immutable() FROM PUBLIC;
CREATE TRIGGER r55_cp_result_immutable BEFORE UPDATE OR DELETE ON company.commands FOR EACH ROW EXECUTE FUNCTION company_private.r55_cp_result_immutable();

CREATE FUNCTION company_private.r55_cp_require_finalized_command() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE c company.commands%ROWTYPE;
BEGIN
 IF company_private.r55_cp_event_kind(NEW.operation) IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=NEW.tenant_id AND id=NEW.id;
 IF c.state IS DISTINCT FROM 'SUCCEEDED' OR c.r55_result_digest IS NULL OR c.r55_event_sequence IS NULL OR c.r55_audit_id IS NULL
 OR NOT EXISTS(SELECT 1 FROM company.audit_events a WHERE a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id AND a.kind=company_private.r55_cp_event_kind(c.operation))
 OR NOT EXISTS(SELECT 1 FROM company.outbox e WHERE e.tenant_id=c.tenant_id AND e.project_id=c.r55_project_id AND e.project_sequence=c.r55_event_sequence AND e.event_instance_id=c.id AND e.event_writer_generation=54 AND e.payload->>'result_digest'=c.r55_result_digest AND e.payload->>'request_digest'=c.payload_digest)
 THEN RAISE EXCEPTION 'MANDATORY_COMMAND_RECEIPT_AUDIT_EVENT_MISSING'; END IF;
 RETURN NULL;
END $$;
ALTER FUNCTION company_private.r55_cp_require_finalized_command() OWNER TO company_atomic_functions_r55;
REVOKE ALL ON FUNCTION company_private.r55_cp_require_finalized_command() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER r55_cp_require_finalized_command AFTER INSERT OR UPDATE ON company.commands DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION company_private.r55_cp_require_finalized_command();
CREATE FUNCTION company_private.r55_cp_context_exit(p_nonce uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 -- Evaluate deferred result linkage while transaction-bound context still exists.
 -- Constraints remain IMMEDIATE; no protected write is allowed after this cut.
 SET CONSTRAINTS company.r55_cp_require_finalized_command IMMEDIATE;
 PERFORM company_private.r54_context_exit(p_nonce);
END $$;
ALTER FUNCTION company_private.r55_cp_context_exit(uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_context_exit(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_context_exit(uuid) TO company_transport_r54;
-- HMAC envelope verification is NOT provided by these digests. E0-04 remains
-- blocked until enrolled-key verifier -> immutable envelope INSERT is accepted.
ROLLBACK;
