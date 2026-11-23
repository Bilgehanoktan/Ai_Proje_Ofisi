BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- PlanCreate: exact canonical OpenAPI fields; no endpoint invented.
GRANT SELECT ON company.objectives,company.projects TO company_first_run_functions_r53;
GRANT UPDATE(revision) ON company.projects TO company_first_run_functions_r53;
GRANT INSERT ON company.plans TO company_first_run_functions_r53;
CREATE POLICY r54_plans_create_parent ON company.objectives FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,project_id,'plans.create',NULL,true));
CREATE POLICY r54_plans_create_project_select ON company.projects FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,id,'plans.create',NULL,true));
CREATE POLICY r54_plans_create_project_update ON company.projects FOR UPDATE TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,id,'plans.create',NULL,true)) WITH CHECK(company_private.r54_allowed(tenant_id,id,'plans.create',NULL,true));
CREATE POLICY r54_plans_create_insert ON company.plans FOR INSERT TO company_first_run_functions_r53 WITH CHECK(company_private.r54_allowed(tenant_id,project_id,'plans.create',NULL,true));
CREATE FUNCTION company_private.r54_plans_create(q jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; pid uuid; parent_id uuid; rid uuid; cid uuid; correlation uuid; k text; d text; rev bigint; dep uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='plans.create';
 IF q IS NULL OR jsonb_typeof(q)<>'object' OR NOT(q ?& ARRAY['idempotency_key','correlation_id','project_id','objective_id','expected_revision','assumptions','acceptance_criteria']) OR EXISTS(SELECT 1 FROM jsonb_object_keys(q) key WHERE key<>ALL(ARRAY['idempotency_key','correlation_id','project_id','objective_id','expected_revision','assumptions','acceptance_criteria'])) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 pid=(q->>'project_id')::uuid; parent_id=(q->>'objective_id')::uuid; correlation=(q->>'correlation_id')::uuid; k=q->>'idempotency_key';
 IF pid IS DISTINCT FROM x.project_id OR x.task_id IS NOT NULL OR k IS NULL OR k !~ '^[A-Za-z0-9_.:-]{16,128}$' OR NOT company_private.r54_allowed(x.tenant_id,pid,'plans.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF jsonb_typeof(q->'acceptance_criteria') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'acceptance_criteria') NOT BETWEEN 1 AND 20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'acceptance_criteria') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 d=encode(sha256(convert_to((q-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 SELECT revision INTO STRICT rev FROM company.projects WHERE tenant_id=x.tenant_id AND id=pid FOR UPDATE;
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='plans.create' AND idempotency_key=k;
 IF FOUND THEN
  IF c.payload_digest<>d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 PERFORM 1 FROM company.objectives WHERE tenant_id=x.tenant_id AND project_id=pid AND id=parent_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'PARENT_NOT_FOUND_OR_DENIED'; END IF;
 IF jsonb_typeof(q->'expected_revision') IS DISTINCT FROM 'number' OR (q->>'expected_revision') !~ '^[0-9]+$' OR (q->>'expected_revision')::bigint<>rev THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 IF jsonb_typeof(q->'assumptions') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'assumptions')>20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'assumptions') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 rid=gen_random_uuid(); cid=gen_random_uuid();
 INSERT INTO company.plans(tenant_id,project_id,id,objective_id,revision,assumptions,acceptance_criteria) VALUES(x.tenant_id,pid,rid,parent_id,0,q->'assumptions',q->'acceptance_criteria');
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cid,x.principal_id,'plans.create',k,d,correlation,'SUCCEEDED',rid);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=pid AND revision=rev;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'PlanCreated');
 PERFORM company_private.r54_emit_event(x.tenant_id,pid,rid,0,'PlanCreated',jsonb_build_object('resource_id',rid,'command_id',cid,'project_revision',rev+1));
 IF NOT company_private.r54_allowed(x.tenant_id,pid,'plans.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',cid,'correlation_id',correlation,'state','SUCCEEDED','result_ref',rid);
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;
ALTER FUNCTION company_private.r54_plans_create(jsonb) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_plans_create(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_plans_create(jsonb) TO company_transport_r54;
-- TaskCreate: exact canonical OpenAPI fields; no endpoint invented.
GRANT SELECT ON company.plans,company.projects TO company_first_run_functions_r53;
GRANT UPDATE(revision) ON company.projects TO company_first_run_functions_r53;
GRANT INSERT ON company.tasks TO company_first_run_functions_r53;
CREATE POLICY r54_tasks_create_parent ON company.plans FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,project_id,'tasks.create',NULL,true));
CREATE POLICY r54_tasks_create_project_select ON company.projects FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,id,'tasks.create',NULL,true));
CREATE POLICY r54_tasks_create_project_update ON company.projects FOR UPDATE TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,id,'tasks.create',NULL,true)) WITH CHECK(company_private.r54_allowed(tenant_id,id,'tasks.create',NULL,true));
CREATE POLICY r54_tasks_create_insert ON company.tasks FOR INSERT TO company_first_run_functions_r53 WITH CHECK(company_private.r54_allowed(tenant_id,project_id,'tasks.create',NULL,true));
CREATE FUNCTION company_private.r54_tasks_create(q jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; pid uuid; parent_id uuid; rid uuid; cid uuid; correlation uuid; k text; d text; rev bigint; dep uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='tasks.create';
 IF q IS NULL OR jsonb_typeof(q)<>'object' OR NOT(q ?& ARRAY['idempotency_key','correlation_id','project_id','plan_id','title','role_id','acceptance_criteria']) OR EXISTS(SELECT 1 FROM jsonb_object_keys(q) key WHERE key<>ALL(ARRAY['idempotency_key','correlation_id','project_id','plan_id','title','role_id','acceptance_criteria','depends_on'])) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 pid=(q->>'project_id')::uuid; parent_id=(q->>'plan_id')::uuid; correlation=(q->>'correlation_id')::uuid; k=q->>'idempotency_key';
 IF pid IS DISTINCT FROM x.project_id OR x.task_id IS NOT NULL OR k IS NULL OR k !~ '^[A-Za-z0-9_.:-]{16,128}$' OR NOT company_private.r54_allowed(x.tenant_id,pid,'tasks.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF jsonb_typeof(q->'acceptance_criteria') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF jsonb_array_length(q->'acceptance_criteria') NOT BETWEEN 1 AND 20 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'acceptance_criteria') e WHERE jsonb_typeof(e)<>'string' OR length(e#>>'{}') NOT BETWEEN 1 AND 2000) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 d=encode(sha256(convert_to((q-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 SELECT revision INTO STRICT rev FROM company.projects WHERE tenant_id=x.tenant_id AND id=pid FOR UPDATE;
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='tasks.create' AND idempotency_key=k;
 IF FOUND THEN
  IF c.payload_digest<>d THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 PERFORM 1 FROM company.plans WHERE tenant_id=x.tenant_id AND project_id=pid AND id=parent_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'PARENT_NOT_FOUND_OR_DENIED'; END IF;
 IF jsonb_typeof(q->'title') IS DISTINCT FROM 'string' OR length(q->>'title') NOT BETWEEN 3 AND 200 OR jsonb_typeof(q->'role_id') IS DISTINCT FROM 'string' OR (q->>'role_id') !~ '^(MGR|EXP)-[0-9]{2,3}$' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 IF q ? 'depends_on' THEN
  IF jsonb_typeof(q->'depends_on') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
  IF jsonb_array_length(q->'depends_on')>32 OR EXISTS(SELECT 1 FROM jsonb_array_elements(q->'depends_on') e WHERE jsonb_typeof(e)<>'string') OR (SELECT count(*)<>count(DISTINCT value) FROM jsonb_array_elements_text(q->'depends_on')) THEN RAISE EXCEPTION 'INVALID_TYPED_REQUEST'; END IF;
 END IF;
 rid=gen_random_uuid(); cid=gen_random_uuid();
 INSERT INTO company.tasks(tenant_id,project_id,id,plan_id,title,role_id,state,revision,fencing_epoch,acceptance_criteria) VALUES(x.tenant_id,pid,rid,parent_id,q->>'title',q->>'role_id','DRAFT',0,0,q->'acceptance_criteria');
 -- Existing dependency rows cannot point to a not-yet-created rid; only outgoing edges added => no cycle introduced.
 FOR dep IN SELECT value::uuid FROM jsonb_array_elements_text(COALESCE(q->'depends_on','[]'::jsonb)) ORDER BY value LOOP
  PERFORM 1 FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=pid AND id=dep;
  IF NOT FOUND THEN RAISE EXCEPTION 'DEPENDENCY_NOT_FOUND_OR_DENIED'; END IF;
  INSERT INTO company.task_dependencies(tenant_id,project_id,task_id,depends_on_task_id) VALUES(x.tenant_id,pid,rid,dep);
 END LOOP;
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cid,x.principal_id,'tasks.create',k,d,correlation,'SUCCEEDED',rid);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=pid AND revision=rev;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT_REVISION'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'TaskCreated');
 PERFORM company_private.r54_emit_event(x.tenant_id,pid,rid,0,'TaskCreated',jsonb_build_object('resource_id',rid,'command_id',cid,'project_revision',rev+1));
 IF NOT company_private.r54_allowed(x.tenant_id,pid,'tasks.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',cid,'correlation_id',correlation,'state','SUCCEEDED','result_ref',rid);
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;
ALTER FUNCTION company_private.r54_tasks_create(jsonb) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_tasks_create(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_tasks_create(jsonb) TO company_transport_r54;
GRANT SELECT ON company.tasks TO company_first_run_functions_r53;
GRANT INSERT ON company.task_dependencies TO company_first_run_functions_r53;
CREATE POLICY r54_task_create_dependency_read ON company.tasks FOR SELECT TO company_first_run_functions_r53 USING(company_private.r54_allowed(tenant_id,project_id,'tasks.create',NULL,true));
CREATE POLICY r54_task_create_dependency_write ON company.task_dependencies FOR INSERT TO company_first_run_functions_r53 WITH CHECK(company_private.r54_allowed(tenant_id,project_id,'tasks.create',NULL,true));
-- Reuse exact r53 command SELECT/INSERT policies (dynamic current operation), add audit policy specific to these two operations.
CREATE POLICY r54_plan_task_audit ON company.audit_events FOR INSERT TO company_first_run_functions_r53 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id AND x.operation_id IN ('plans.create','tasks.create') AND company_private.r54_allowed(x.tenant_id,x.project_id,x.operation_id,NULL,true)));
ROLLBACK;
