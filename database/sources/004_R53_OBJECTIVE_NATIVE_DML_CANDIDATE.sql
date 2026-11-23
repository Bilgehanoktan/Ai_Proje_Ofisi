BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Önkoşul: r53 context overlay. Bu SQL ürün kurulumu değildir.
CREATE POLICY r53_objective_insert ON company.objectives FOR INSERT TO company_first_run_functions_r53
 WITH CHECK(company_private.r53_allowed(tenant_id,project_id,'objectives.create',NULL,true)
 AND created_by=(SELECT principal_id FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user));
CREATE POLICY r53_command_read ON company.commands FOR SELECT TO company_first_run_functions_r53 USING(
 EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND company_private.r53_allowed(x.tenant_id,x.project_id,x.operation_id,x.task_id,true)));
CREATE POLICY r53_command_insert ON company.commands FOR INSERT TO company_first_run_functions_r53 WITH CHECK(
 EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND company_private.r53_allowed(x.tenant_id,x.project_id,x.operation_id,x.task_id,true)));
CREATE POLICY r53_command_update ON company.commands FOR UPDATE TO company_first_run_functions_r53
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND company_private.r53_allowed(x.tenant_id,x.project_id,x.operation_id,x.task_id,true)))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND x.operation_id=commands.operation AND company_private.r53_allowed(x.tenant_id,x.project_id,x.operation_id,x.task_id,true)));
CREATE POLICY r53_project_objective_read ON company.projects FOR SELECT TO company_first_run_functions_r53 USING(company_private.r53_allowed(tenant_id,id,'objectives.create',NULL,true));
CREATE POLICY r53_project_objective_update ON company.projects FOR UPDATE TO company_first_run_functions_r53 USING(company_private.r53_allowed(tenant_id,id,'objectives.create',NULL,true)) WITH CHECK(company_private.r53_allowed(tenant_id,id,'objectives.create',NULL,true));
CREATE POLICY r53_objective_audit ON company.audit_events FOR INSERT TO company_first_run_functions_r53 WITH CHECK(
 EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id AND x.operation_id='objectives.create' AND company_private.r53_allowed(x.tenant_id,x.project_id,'objectives.create',NULL,true)));
CREATE POLICY r53_objective_outbox ON company.outbox FOR INSERT TO company_first_run_functions_r53 WITH CHECK(company_private.r53_allowed(tenant_id,project_id,'objectives.create',NULL,true) AND kind='ObjectiveCreated');
GRANT INSERT ON company.objectives,company.audit_events,company.outbox TO company_first_run_functions_r53;
GRANT SELECT,INSERT,UPDATE ON company.commands TO company_first_run_functions_r53;
GRANT SELECT ON company.projects TO company_first_run_functions_r53;
GRANT UPDATE(revision) ON company.projects TO company_first_run_functions_r53;
GRANT USAGE ON SEQUENCE company.audit_events_id_seq,company.outbox_event_id_seq TO company_first_run_functions_r53;

CREATE FUNCTION company_private.r53_objectives_create(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; v_project uuid; v_correlation uuid;
 v_key text; v_digest text; v_id uuid; v_command uuid; v_revision bigint; element jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='objectives.create';
 IF p_request IS NULL OR jsonb_typeof(p_request)<>'object' OR NOT (p_request ?& ARRAY['idempotency_key','correlation_id','project_id','goal','constraints','expected_outputs'])
 OR (SELECT count(*) FROM jsonb_object_keys(p_request))<>6 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF jsonb_typeof(p_request->'idempotency_key')<>'string' OR jsonb_typeof(p_request->'correlation_id')<>'string' OR jsonb_typeof(p_request->'project_id')<>'string'
 OR jsonb_typeof(p_request->'goal')<>'string' OR jsonb_typeof(p_request->'constraints')<>'array' OR jsonb_typeof(p_request->'expected_outputs')<>'array' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 v_project=(p_request->>'project_id')::uuid; v_correlation=(p_request->>'correlation_id')::uuid; v_key=p_request->>'idempotency_key';
 IF v_project IS DISTINCT FROM x.project_id OR x.resource_kind<>'PROJECT' OR NOT company_private.r53_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF length(v_key) NOT BETWEEN 16 AND 128 OR v_key !~ '^[A-Za-z0-9_.:-]+$' OR length(p_request->>'goal') NOT BETWEEN 10 AND 4000
 OR jsonb_array_length(p_request->'constraints') NOT BETWEEN 1 AND 20 OR jsonb_array_length(p_request->'expected_outputs') NOT BETWEEN 1 AND 10 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 FOR element IN SELECT value FROM jsonb_array_elements((p_request->'constraints')||(p_request->'expected_outputs')) LOOP
  IF jsonb_typeof(element)<>'string' OR length(element#>>'{}') NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 END LOOP;
 -- Server-owned profile PG_JSONB_TEXT_UTF8_R53; JCS veya caller digest iddiası yok.
 -- correlation_id semantik payload dışıdır: replay ilk correlation id'yi döndürür.
 v_digest=encode(sha256(convert_to((p_request-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 -- Project authority advisory lock context enter'da alınmıştır; row lock bundan sonra.
 SELECT revision INTO STRICT v_revision FROM company.projects WHERE tenant_id=x.tenant_id AND id=v_project FOR UPDATE;
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='objectives.create' AND idempotency_key=v_key;
 IF FOUND THEN
  IF c.payload_digest<>v_digest THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 v_id=gen_random_uuid(); v_command=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,v_command,x.principal_id,'objectives.create',v_key,v_digest,v_correlation,'RUNNING',NULL);
 INSERT INTO company.objectives(tenant_id,project_id,id,goal,constraints,expected_outputs,created_by)
 VALUES(x.tenant_id,v_project,v_id,p_request->>'goal',p_request->'constraints',p_request->'expected_outputs',x.principal_id);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=v_project AND revision=v_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,v_correlation,x.principal_id,'ObjectiveCreated');
 INSERT INTO company.outbox(tenant_id,project_id,aggregate_id,aggregate_revision,kind,payload)
 VALUES(x.tenant_id,v_project,v_id,v_revision+1,'ObjectiveCreated',jsonb_build_object('objective_id',v_id,'command_id',v_command,'project_revision',v_revision+1));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=v_id WHERE tenant_id=x.tenant_id AND id=v_command;
 IF NOT company_private.r53_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',v_command,'correlation_id',v_correlation,'state','SUCCEEDED','result_ref',v_id);
EXCEPTION WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
WHEN INVALID_TEXT_REPRESENTATION THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
END $$;
ALTER FUNCTION company_private.r53_objectives_create(jsonb) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r53_objectives_create(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r53_objectives_create(jsonb) TO company_transport_r53;
ROLLBACK;
