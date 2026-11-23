BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r60_ready_binding(p_task uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;t company.tasks%ROWTYPE;p company.plans%ROWTYPE;h text;deps jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task;
 SELECT * INTO STRICT p FROM company.plans WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=t.plan_id FOR SHARE;
 SELECT head_digest INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 PERFORM 1 FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND (id=p_task OR id IN(SELECT depends_on_task_id FROM company.task_dependencies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task)) ORDER BY id FOR UPDATE;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task;
 IF jsonb_array_length(t.acceptance_criteria)=0 OR jsonb_array_length(p.acceptance_criteria)=0
 OR NOT EXISTS(SELECT 1 FROM company.objectives WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p.objective_id)
 OR EXISTS(SELECT 1 FROM company.task_dependencies d LEFT JOIN company.tasks parent ON parent.tenant_id=d.tenant_id AND parent.project_id=d.project_id AND parent.id=d.depends_on_task_id WHERE d.tenant_id=x.tenant_id AND d.project_id=x.project_id AND d.task_id=p_task AND (parent.id IS NULL OR parent.state<>'ACCEPTED')) THEN RAISE EXCEPTION 'R60_READINESS_DEPENDENCIES'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',parent.id,'revision',parent.revision,'state',parent.state) ORDER BY parent.id),'[]'::jsonb) INTO deps FROM company.task_dependencies d JOIN company.tasks parent ON parent.tenant_id=d.tenant_id AND parent.project_id=d.project_id AND parent.id=d.depends_on_task_id WHERE d.tenant_id=x.tenant_id AND d.project_id=x.project_id AND d.task_id=p_task;
 RETURN jsonb_build_object('task_id',t.id,'task_revision',t.revision,'plan_id',p.id,'plan_revision',p.revision,'role_id',t.role_id,'task_criteria',t.acceptance_criteria,'plan_criteria',p.acceptance_criteria,'dependencies',deps,'head_digest',h);
END $$;
CREATE FUNCTION company_private.r60_finish_revision(p_command uuid,p_target uuid,p_revision bigint,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;receipt jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND principal_id=x.principal_id AND operation=x.operation_id;
 INSERT INTO company_private.r58_execution_receipts VALUES(x.tenant_id,x.project_id,c.id,x.operation_id,p_target,p_result);
 receipt=company_private.r55_cp_finalize_command(c.id,p_target,p_revision,company_private.r55_cp_event_kind(x.operation_id),p_result);
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=x.tenant_id AND id=p_command AND r55_project_id=x.project_id AND state='SUCCEEDED';
 RETURN receipt||jsonb_build_object('result_payload',c.r55_result_payload);
END $$;
CREATE FUNCTION company_private.r60_tasks_ready(p_task uuid,p_plan_revision bigint,p_head text,q jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;t company.tasks%ROWTYPE;c company.commands%ROWTYPE;b jsonb;
BEGIN
 x=company_private.r58_context('tasks.ready');
 PERFORM company_private.r58_shape(q-'approval_ref',ARRAY['idempotency_key','correlation_id','expected_revision','action','reason']);
 IF x.task_id IS DISTINCT FROM p_task OR x.attempt_id IS NOT NULL OR q->>'action' IS DISTINCT FROM 'ready' OR length(q->>'reason') NOT BETWEEN 1 AND 2000 OR jsonb_typeof(q->'reason') IS DISTINCT FROM 'string'
 OR (q ? 'approval_ref' AND q->'approval_ref'<>'null'::jsonb) OR jsonb_typeof(q->'expected_revision') IS DISTINCT FROM 'number' OR (q->>'expected_revision') !~ '^[0-9]+$' THEN RAISE EXCEPTION 'R60_READY_TYPED_SCOPE'; END IF;
 c=company_private.r58_begin_command(q->>'idempotency_key',(q->>'correlation_id')::uuid,jsonb_build_object('task_id',p_task,'plan_revision',p_plan_revision,'head',p_head,'action',q-'idempotency_key'-'correlation_id'));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 b=company_private.r60_ready_binding(p_task);
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task;
 IF t.state IS DISTINCT FROM 'DRAFT' OR t.execution_kind IS DISTINCT FROM 'ORDINARY' OR t.active_attempt_id IS NOT NULL OR t.revision IS DISTINCT FROM (q->>'expected_revision')::bigint OR b->>'plan_revision' IS DISTINCT FROM p_plan_revision::text OR b->>'head_digest' IS DISTINCT FROM p_head THEN RAISE EXCEPTION 'R60_READY_CAS'; END IF;
 UPDATE company.tasks SET state='READY',revision=revision+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task AND state='DRAFT' AND revision=t.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_READY_UPDATE_CAS'; END IF;
 b=jsonb_set(b,'{task_revision}',to_jsonb(t.revision+1));
 INSERT INTO company_private.r60_ready_bindings VALUES(x.tenant_id,x.project_id,p_task,t.revision+1,p_plan_revision,p_head,b,encode(sha256(convert_to(b::text,'UTF8')),'hex'),c.id);
 RETURN company_private.r60_finish_revision(c.id,p_task,t.revision+1,jsonb_build_object('task_id',p_task,'state','READY','revision',t.revision+1,'binding_digest',encode(sha256(convert_to(b::text,'UTF8')),'hex')));
END $$;
CREATE FUNCTION company_private.r60_assert_ready(p_task uuid,p_revision bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;b jsonb;saved jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 b=company_private.r60_ready_binding(p_task);
 SELECT binding INTO STRICT saved FROM company_private.r60_ready_bindings WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND task_revision=p_revision;
 IF saved IS DISTINCT FROM b THEN RAISE EXCEPTION 'R60_READINESS_CHANGED_REISSUE_REQUIRED'; END IF;
END $$;
ROLLBACK;
