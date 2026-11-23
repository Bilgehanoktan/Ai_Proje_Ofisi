BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r54_e0_setup_mandate_consume(p_installation uuid,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; b company_private.bootstrap_receipts%ROWTYPE; e company.evaluation_runs%ROWTYPE;
 v_command uuid; v_id uuid; v_digest text; v_key text; c company.commands%ROWTYPE;
BEGIN
 x=company_private.r54_b_context('e0.setup_mandate_consume',true);
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=p_installation AND tenant_id=x.tenant_id AND project_id=x.project_id FOR UPDATE;
 IF b.accepted_human_id IS DISTINCT FROM x.principal_id OR b.e0_mandate IS NULL OR b.e0_valid_until IS NULL OR b.e0_valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)
 THEN RAISE EXCEPTION 'BLOCKED_SETUP_MANDATE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.installation_bootstrap_control z WHERE z.installation_id=b.installation_id AND z.state='CONSUMED' AND z.generation=b.generation AND z.consumed_command_id=b.command_id AND z.setup_manifest_digest=b.setup_manifest_digest) THEN RAISE EXCEPTION 'BLOCKED_SETUP_PROVENANCE'; END IF;
 v_digest=encode(sha256(convert_to(b.e0_mandate::text,'UTF8')),'hex');v_key='e0:'||p_installation::text;
 c=company_private.r64_begin_digest(v_key,p_correlation,v_digest);
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 v_command=c.id;v_id=gen_random_uuid();
 INSERT INTO company.evaluation_runs(tenant_id,project_id,id,authorization_id,role_id,fixture_digest,model_digest,source_kind,state,subject_principal_id,e0_installation_id)
 VALUES(x.tenant_id,x.project_id,v_id,v_command,b.e0_mandate->>'role_id',b.e0_mandate->>'fixture_digest',b.e0_mandate->>'model_digest','DISPOSABLE_TEST','AUTHORIZED',(b.e0_mandate->>'subject_principal_id')::uuid,p_installation);
 RETURN company_private.r60_finish_revision(v_command,v_id,0,jsonb_build_object('evaluation_run_id',v_id,'command_id',v_command,'outcome','EVALUATION_AUTHORIZED_NOT_STARTED'));
END $$;
ALTER FUNCTION company_private.r54_e0_setup_mandate_consume(uuid,uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_e0_setup_mandate_consume(uuid,uuid) FROM PUBLIC;

CREATE OR REPLACE FUNCTION company_private.r54_qualification_candidate_issue(p_evaluation uuid,p_valid_until timestamptz,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE;c company.commands%ROWTYPE;v uuid;cmd uuid;d text;
BEGIN
 x=company_private.r54_b_context('e0.qualification_candidate_issue',true);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 IF e.state<>'REVIEWED' OR e.execution_binding IS NULL OR e.execution_binding_digest IS NULL OR e.sealed_evidence_id IS NULL OR p_valid_until IS NULL OR p_valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) THEN RAISE EXCEPTION 'BLOCKED_REVIEWED_EVALUATION'; END IF;
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.bootstrap_receipts b WHERE b.installation_id=e.e0_installation_id AND b.e0_valid_until>=p_valid_until AND b.accepted_human_id=x.principal_id) THEN RAISE EXCEPTION 'BLOCKED_QUALIFICATION_VALIDITY_CEILING'; END IF;
 d=encode(sha256(convert_to(jsonb_build_array(e.id,e.execution_binding_digest,p_valid_until)::text,'UTF8')),'hex');
 c=company_private.r64_begin_digest(p_key,p_correlation,d);
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 v=gen_random_uuid();cmd=c.id;
 INSERT INTO company.agent_qualifications(tenant_id,project_id,id,evaluation_run_id,role_id,version_binding,approved_by,valid_until,subject_principal_id,execution_binding_digest,evaluation_task_id,evaluation_attempt_id,evaluation_evidence_id)
 VALUES(x.tenant_id,x.project_id,v,e.id,e.role_id,e.execution_binding,x.principal_id,p_valid_until,e.subject_principal_id,e.execution_binding_digest,e.evaluation_task_id,e.evaluation_attempt_id,e.sealed_evidence_id);
 RETURN company_private.r60_finish_revision(cmd,v,0,jsonb_build_object('qualification_id',v,'command_id',cmd,'outcome','CANDIDATE_NOT_ACTIVE','grant_created',false));
END $$;
ALTER FUNCTION company_private.r54_qualification_candidate_issue(uuid,timestamptz,text,uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_qualification_candidate_issue(uuid,timestamptz,text,uuid) FROM PUBLIC;

CREATE OR REPLACE FUNCTION company_private.r54_qualification_decide(p_qualification uuid,p_expected_revision bigint,p_decision_task uuid,p_decision_attempt uuid,p_decision_artifact uuid,p_revoke boolean,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;q company.agent_qualifications%ROWTYPE;a company.artifacts%ROWTYPE;h company.governance_decision_heads%ROWTYPE;c company.commands%ROWTYPE;
 v_op text;v_target text;v_digest text;v_cmd uuid;v_revision bigint;v_kind text;
BEGIN
 IF p_revoke IS NULL THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 v_op=CASE WHEN p_revoke THEN 'qualification.revoke' ELSE 'qualification.activate' END;
 v_kind=CASE WHEN p_revoke THEN 'QUALIFICATION_REVOKE' ELSE 'QUALIFICATION_ACTIVATE' END;
 x=company_private.r54_b_context(v_op,true);
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 OR p_expected_revision IS NULL OR p_expected_revision<0 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 SELECT * INTO STRICT q FROM company.agent_qualifications WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_qualification;
 IF q.execution_binding_digest IS NULL OR q.subject_principal_id IS NULL THEN RAISE EXCEPTION 'BLOCKED_LEGACY_QUALIFICATION'; END IF;
 SELECT * INTO STRICT a FROM company.artifacts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_decision_task AND attempt_id=p_decision_attempt AND id=p_decision_artifact AND state='AVAILABLE';
 IF NOT ((a.r54_human_decision->>'kind'=v_kind AND a.r54_human_decision->>'human_id'=x.principal_id::text
 AND a.r54_human_decision->>'qualification_id'=q.id::text AND a.r54_human_decision->>'binding_digest'=q.execution_binding_digest
 AND (a.r54_human_decision->>'valid_until')::timestamptz>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz)) IS TRUE)
 OR NOT EXISTS(SELECT 1 FROM company.commands z WHERE z.tenant_id=x.tenant_id AND z.id=(a.r54_human_decision->>'command_id')::uuid AND z.principal_id=x.principal_id AND z.operation='qualification.human_decision' AND z.state='SUCCEEDED' AND z.result_ref=a.id)
 THEN RAISE EXCEPTION 'BLOCKED_EXACT_HUMAN_DECISION'; END IF;
 IF NOT p_revoke AND (q.valid_until<=((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) OR NOT EXISTS(SELECT 1 FROM company.evaluation_runs e JOIN company.evidence ev ON ev.tenant_id=e.tenant_id AND ev.project_id=e.project_id AND ev.task_id=e.evaluation_task_id AND ev.attempt_id=e.evaluation_attempt_id AND ev.id=e.sealed_evidence_id JOIN company.verification_runs vr ON vr.tenant_id=ev.tenant_id AND vr.project_id=ev.project_id AND vr.task_id=ev.task_id AND vr.attempt_id=ev.attempt_id AND vr.id=ev.verification_run_id
 WHERE e.tenant_id=q.tenant_id AND e.project_id=q.project_id AND e.id=q.evaluation_run_id AND e.execution_binding_digest=q.execution_binding_digest AND e.state='REVIEWED' AND vr.result='PASS' AND vr.exit_code=0 AND vr.producer_id<>vr.verifier_id)) THEN RAISE EXCEPTION 'BLOCKED_INDEPENDENT_EVALUATION'; END IF;
 v_target=encode(sha256(convert_to(q.id::text,'UTF8')),'hex');
 v_digest=encode(sha256(convert_to(jsonb_build_array(q.id,p_expected_revision,p_decision_task,p_decision_attempt,p_decision_artifact,p_revoke)::text,'UTF8')),'hex');
 -- Project authority lock is already held by protected context; serialize absent and present head.
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 c=company_private.r64_begin_digest(p_key,p_correlation,v_digest);
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO h FROM company.governance_decision_heads WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND decision_kind='QUALIFICATION' AND operation='qualification.activate' AND logical_target_digest=v_target FOR UPDATE;
 IF COALESCE(h.revision,0)<>p_expected_revision OR (p_revoke AND h.revision IS NULL) THEN RAISE EXCEPTION 'STALE_QUALIFICATION_HEAD'; END IF;
 v_revision=p_expected_revision+1;v_cmd=c.id;
 INSERT INTO company.governance_decision_heads(tenant_id,scope_kind,scope_ref,target_project_id,decision_kind,operation,logical_target_digest,revision,decision_state,decision_project_id,decision_task_id,decision_attempt_id,decision_artifact_id,command_id,decision_digest)
 VALUES(x.tenant_id,'PROJECT',x.project_id,x.project_id,'QUALIFICATION','qualification.activate',v_target,v_revision,CASE WHEN p_revoke THEN 'REVOKED' ELSE 'APPROVED' END,x.project_id,p_decision_task,p_decision_attempt,p_decision_artifact,v_cmd,a.sha256)
 ON CONFLICT(tenant_id,scope_kind,scope_ref,decision_kind,operation,logical_target_digest) DO UPDATE SET revision=EXCLUDED.revision,decision_state=EXCLUDED.decision_state,decision_project_id=EXCLUDED.decision_project_id,decision_task_id=EXCLUDED.decision_task_id,decision_attempt_id=EXCLUDED.decision_attempt_id,decision_artifact_id=EXCLUDED.decision_artifact_id,command_id=EXCLUDED.command_id,decision_digest=EXCLUDED.decision_digest WHERE company.governance_decision_heads.revision=p_expected_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_QUALIFICATION_HEAD'; END IF;
 RETURN company_private.r60_finish_revision(v_cmd,q.id,v_revision,jsonb_build_object('qualification_id',q.id,'command_id',v_cmd,'head_revision',v_revision,'outcome',CASE WHEN p_revoke THEN 'REVOKED' ELSE 'ACTIVATED_NO_GRANT' END));
END $$;
ALTER FUNCTION company_private.r54_qualification_decide(uuid,bigint,uuid,uuid,uuid,boolean,text,uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_qualification_decide(uuid,bigint,uuid,uuid,uuid,boolean,text,uuid) FROM PUBLIC;

CREATE OR REPLACE FUNCTION company_private.r54_e0_evaluation_artifact_record(p_evaluation uuid,p_report jsonb,p_key text,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.evaluation_runs%ROWTYPE; c company.commands%ROWTYPE; a uuid; cmd uuid;d text;n bigint;
BEGIN
 x=company_private.r54_b_context('e0.evaluation_artifact_record',false);
 PERFORM company_private.r54_schema_check(p_report,'{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","properties":{"profile":{"const":"r54.evaluation-report.pg-jsonb.v1"},"receipt_id":{"type":"string","format":"uuid"},"subject_principal_id":{"type":"string","format":"uuid"},"model_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"fixture_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"negative_suite_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"},"positive_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}},"negative_cases":{"type":"array","minItems":1,"items":{"type":"object","properties":{"oracle_id":{"type":"string","minLength":1},"result":{"const":"PASS"},"observed_digest":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["oracle_id","result","observed_digest"],"additionalProperties":false}}},"required":["profile","receipt_id","subject_principal_id","model_digest","fixture_digest","negative_suite_digest","positive_cases","negative_cases"],"additionalProperties":false}'::jsonb);
 SELECT * INTO STRICT e FROM company.evaluation_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_evaluation FOR UPDATE;
 IF e.subject_principal_id IS DISTINCT FROM x.principal_id OR e.state NOT IN ('AUTHORIZED','RUNNING','MEASURED') OR NOT EXISTS(SELECT 1 FROM company.attempts at JOIN company.tasks t ON t.tenant_id=at.tenant_id AND t.project_id=at.project_id AND t.id=at.task_id WHERE at.tenant_id=e.tenant_id AND at.project_id=e.project_id AND at.task_id=e.evaluation_task_id AND at.id=e.evaluation_attempt_id AND at.worker_id=x.principal_id AND at.lease_expires_at>((company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id)->>'utc_upper_bound')::timestamptz) AND at.ended_at IS NULL AND t.execution_kind='EVALUATION' AND t.active_attempt_id=at.id AND t.fencing_epoch=at.fencing_epoch) THEN RAISE EXCEPTION 'DENIED_EVALUATION_ATTEMPT'; END IF;
 IF p_report IS NULL OR jsonb_typeof(p_report)<>'object' OR p_report->>'profile' IS DISTINCT FROM 'r54.evaluation-report.pg-jsonb.v1' OR p_key IS NULL OR length(p_key) NOT BETWEEN 16 AND 128 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 n=octet_length(convert_to(p_report::text,'UTF8'));IF n>65536 THEN RAISE EXCEPTION 'EVALUATION_REPORT_TOO_LARGE'; END IF;
 d=encode(sha256(convert_to(p_report::text,'UTF8')),'hex');
 c=company_private.r64_begin_digest(p_key,p_correlation,d);
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=gen_random_uuid();cmd=c.id;
 -- JSONB is the persisted payload; this bounded report is not an external blob-store availability assertion.
 INSERT INTO company.artifacts(tenant_id,project_id,task_id,attempt_id,id,storage_key,sha256,size_bytes,state,r54_evaluation_report) VALUES(x.tenant_id,x.project_id,e.evaluation_task_id,e.evaluation_attempt_id,a,gen_random_uuid(),d,n,'AVAILABLE',p_report);
 RETURN company_private.r60_finish_revision(cmd,a,0,jsonb_build_object('artifact_id',a,'sha256',d,'command_id',cmd,'outcome','REPORT_RECORDED_NOT_VERIFIED'));
END $$;
ALTER FUNCTION company_private.r54_e0_evaluation_artifact_record(uuid,jsonb,text,uuid) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r54_e0_evaluation_artifact_record(uuid,jsonb,text,uuid) FROM PUBLIC;

ROLLBACK;
