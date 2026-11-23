BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- FRESH/QUIESCED MIGRATION CANDIDATE ONLY. Legacy rows are not assigned fabricated cursors.
CREATE ROLE company_event_functions_r54 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_event_functions_r54;
CREATE TABLE company.project_event_heads (
 tenant_id uuid NOT NULL, project_id uuid NOT NULL, writer_generation bigint NOT NULL CHECK(writer_generation>0),
 committed_sequence bigint NOT NULL CHECK(committed_sequence>=0), migration_manifest_digest text NOT NULL CHECK(migration_manifest_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(tenant_id,project_id), FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id)
);
ALTER TABLE company.outbox ADD COLUMN project_sequence bigint;
ALTER TABLE company.outbox ADD COLUMN event_writer_generation bigint;
ALTER TABLE company.outbox ADD COLUMN event_instance_id uuid;
ALTER TABLE company.outbox ADD COLUMN event_digest text;
ALTER TABLE company.outbox ADD CONSTRAINT r54_event_complete CHECK(
 (project_sequence IS NULL AND event_writer_generation IS NULL AND event_instance_id IS NULL AND event_digest IS NULL)
 OR (project_sequence IS NOT NULL AND event_writer_generation IS NOT NULL AND event_digest IS NOT NULL AND project_sequence>0 AND event_writer_generation>0 AND event_instance_id IS NOT NULL AND event_digest ~ '^[a-f0-9]{64}$'));
CREATE UNIQUE INDEX r54_project_sequence ON company.outbox(tenant_id,project_id,project_sequence);
CREATE UNIQUE INDEX r54_event_identity ON company.outbox(tenant_id,project_id,event_instance_id);
ALTER TABLE company.project_event_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.project_event_heads FORCE ROW LEVEL SECURITY;
GRANT SELECT,UPDATE ON company.project_event_heads TO company_event_functions_r54;
GRANT SELECT,INSERT ON company.outbox TO company_event_functions_r54;
GRANT USAGE ON SEQUENCE company.outbox_event_id_seq TO company_event_functions_r54;
GRANT SELECT ON company_private.request_contexts,company_private.operation_permissions TO company_event_functions_r54;
CREATE POLICY r54_event_registry ON company_private.operation_permissions FOR SELECT TO company_event_functions_r54 USING(true);
CREATE POLICY r54_event_context ON company_private.request_contexts FOR SELECT TO company_event_functions_r54 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user);
-- Policies only expose the transaction-bound scope, never arbitrary supplied tenant/project.
CREATE POLICY r54_head_access ON company.project_event_heads TO company_event_functions_r54
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=project_event_heads.tenant_id AND x.project_id=project_event_heads.project_id))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=project_event_heads.tenant_id AND x.project_id=project_event_heads.project_id));
CREATE POLICY r54_event_access ON company.outbox TO company_event_functions_r54
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=outbox.tenant_id AND x.project_id=outbox.project_id))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=outbox.tenant_id AND x.project_id=outbox.project_id));
CREATE FUNCTION company_private.r54_emit_event(p_tenant uuid,p_project uuid,p_event uuid,p_aggregate uuid,p_revision bigint,p_kind text,p_payload jsonb)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; h company.project_event_heads%ROWTYPE; e company.outbox%ROWTYPE; d text; n bigint; perm text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 IF x.tenant_id<>p_tenant OR x.project_id IS DISTINCT FROM p_project OR p_event IS NULL OR p_aggregate IS NULL OR p_revision IS NULL OR p_revision<0 OR p_kind IS NULL OR p_kind='' OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'INVALID_EVENT_BINDING'; END IF;
 SELECT permission INTO STRICT perm FROM company_private.operation_permissions WHERE operation_id=x.operation_id;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,perm,x.task_id,true) THEN RAISE EXCEPTION 'DENIED_EVENT_COMMIT'; END IF;
 IF NOT ((x.operation_id='objectives.create' AND p_kind='ObjectiveCreated')
 OR (x.operation_id='CAP-017.revoke' AND p_kind='GrantRevoked')
 OR (x.operation_id='plans.create' AND p_kind='PlanCreated')
 OR (x.operation_id='tasks.create' AND p_kind='TaskCreated')
 OR (x.operation_id='e0.setup_mandate_consume' AND p_kind='E0MandateConsumed')
 OR (x.operation_id='e0.evaluation_attempt_create' AND p_kind='E0AttemptCreated')
 OR (x.operation_id='e0.evaluation_artifact_record' AND p_kind='E0ReportRecorded')
 OR (x.operation_id='e0.evaluation_worker_admit' AND p_kind='E0WorkerAdmitted')
 OR (x.operation_id='e0.evaluation_verification_seal' AND p_kind='E0EvaluationSealed')
 OR (x.operation_id='e0.qualification_candidate_issue' AND p_kind='QualificationCandidateIssued')
 OR (x.operation_id='qualification.activate' AND p_kind='QUALIFICATION_ACTIVATE')
 OR (x.operation_id='qualification.revoke' AND p_kind='QUALIFICATION_REVOKE')) THEN RAISE EXCEPTION 'EVENT_PRODUCER_KIND_MISMATCH'; END IF;
 -- PROJECT authority locks precede this row lock. No pg sequence defines the project prefix.
 SELECT * INTO STRICT h FROM company.project_event_heads WHERE tenant_id=p_tenant AND project_id=p_project FOR UPDATE;
 IF h.writer_generation<>54 THEN RAISE EXCEPTION 'OLD_EVENT_WRITER_FENCED'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(p_aggregate,p_revision,p_kind,p_payload)::text,'UTF8')),'hex');
 SELECT * INTO e FROM company.outbox WHERE tenant_id=p_tenant AND project_id=p_project AND event_instance_id=p_event;
 IF FOUND THEN
  IF e.event_digest IS DISTINCT FROM d THEN RAISE EXCEPTION 'CONFLICT_EVENT_DIGEST'; END IF;
  RETURN e.project_sequence;
 END IF;
 n=h.committed_sequence+1;
 INSERT INTO company.outbox(tenant_id,project_id,aggregate_id,aggregate_revision,kind,payload,project_sequence,event_writer_generation,event_instance_id,event_digest)
 VALUES(p_tenant,p_project,p_aggregate,p_revision,p_kind,p_payload,n,54,p_event,d);
 UPDATE company.project_event_heads SET committed_sequence=n WHERE tenant_id=p_tenant AND project_id=p_project AND committed_sequence=h.committed_sequence AND writer_generation=54;
 IF NOT FOUND THEN RAISE EXCEPTION 'CONFLICT_EVENT_HEAD'; END IF;
 RETURN n;
EXCEPTION WHEN NO_DATA_FOUND THEN RAISE EXCEPTION 'EVENT_HEAD_OR_CONTEXT_NOT_MIGRATED';
END $$;
ALTER FUNCTION company_private.r54_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb) OWNER TO company_event_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb) FROM PUBLIC;
CREATE FUNCTION company_private.r54_emit_event(p_tenant uuid,p_project uuid,p_aggregate uuid,p_revision bigint,p_kind text,p_payload jsonb)
RETURNS bigint LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT company_private.r54_emit_event(p_tenant,p_project,
 (substr(encode(sha256(convert_to(jsonb_build_array(p_tenant,p_project,p_aggregate,p_revision,p_kind)::text,'UTF8')),'hex'),1,32))::uuid,
 p_aggregate,p_revision,p_kind,p_payload);
$$;
REVOKE ALL ON FUNCTION company_private.r54_emit_event(uuid,uuid,uuid,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) TO company_event_functions_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_emit_event(uuid,uuid,uuid,uuid,bigint,text,jsonb),company_private.r54_emit_event(uuid,uuid,uuid,bigint,text,jsonb) TO company_first_run_functions_r53,company_revoke_functions_r53;
-- Transport/runtime receive no direct EXECUTE or outbox/head DML. A writer fence removes old direct grants.
ROLLBACK;
