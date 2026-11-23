BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Six bounded detail adapters. No canonical OpenAPI path is asserted.
CREATE ROLE company_readback_functions_r54 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_readback_functions_r54;
GRANT SELECT ON company_private.request_contexts,company.project_event_heads TO company_readback_functions_r54;
GRANT INSERT ON company.audit_events TO company_readback_functions_r54;
GRANT USAGE ON SEQUENCE company.audit_events_id_seq TO company_readback_functions_r54;
GRANT EXECUTE ON FUNCTION company_private.r54_allowed(uuid,uuid,text,uuid,boolean) TO company_readback_functions_r54;
CREATE POLICY r54_readback_context ON company_private.request_contexts FOR SELECT TO company_readback_functions_r54 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user);
CREATE POLICY r54_readback_head ON company.project_event_heads FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=project_event_heads.tenant_id AND x.project_id=project_event_heads.project_id));
CREATE POLICY r54_readback_audit ON company.audit_events FOR INSERT TO company_readback_functions_r54 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id));
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.attempts.read','attempts.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.attempts TO company_readback_functions_r54;
CREATE POLICY r54_attempts_read_read ON company.attempts FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.attempts.read' AND company_private.r54_allowed(attempts.tenant_id,attempts.project_id,'attempts.read',attempts.task_id,false)));
CREATE FUNCTION company_private.r54_attempts_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.attempts.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'attempts.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'task_id',s.task_id,'id',s.id,'attempt_no',s.attempt_no,'fencing_epoch',s.fencing_epoch,'worker_id',s.worker_id,'state',s.state,'lease_expires_at',s.lease_expires_at,'ended_at',s.ended_at),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.attempts s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.task_id=p_task AND s.id=p_id AND (p_attempt IS NULL OR s.id=p_attempt);
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'attempts.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:Attempt');
 RETURN jsonb_build_object('kind','Attempt','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_attempts_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_attempts_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_attempts_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.qualifications.read','qualifications.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.agent_qualifications TO company_readback_functions_r54;
CREATE POLICY r54_qualifications_read_read ON company.agent_qualifications FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.qualifications.read' AND company_private.r54_allowed(agent_qualifications.tenant_id,agent_qualifications.project_id,'qualifications.read',x.task_id,false)));
CREATE FUNCTION company_private.r54_qualifications_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.qualifications.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'qualifications.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'id',s.id,'evaluation_run_id',s.evaluation_run_id,'role_id',s.role_id,'version_binding',s.version_binding,'approved_by',s.approved_by,'valid_until',s.valid_until,'subject_principal_id',s.subject_principal_id),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.agent_qualifications s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.id=p_id AND (p_task IS NULL OR EXISTS(SELECT 1 FROM company.attempts a WHERE a.tenant_id=s.tenant_id AND a.project_id=s.project_id AND a.task_id=p_task AND a.admission_qualification_id=s.id AND a.worker_id=s.subject_principal_id)) AND s.subject_principal_id IS NOT NULL;
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'qualifications.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:Qualification');
 RETURN jsonb_build_object('kind','Qualification','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_qualifications_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_qualifications_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_qualifications_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.agent_runs.read','agent_runs.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.process_runs TO company_readback_functions_r54;
CREATE POLICY r54_agent_runs_read_read ON company.process_runs FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.agent_runs.read' AND company_private.r54_allowed(process_runs.tenant_id,process_runs.project_id,'agent_runs.read',process_runs.task_id,false)));
CREATE FUNCTION company_private.r54_agent_runs_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.agent_runs.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'agent_runs.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'task_id',s.task_id,'attempt_id',s.attempt_id,'id',s.id,'worker_id',s.worker_id,'qualification_id',s.qualification_id,'state',s.state,'revision',s.revision,'attempt_fencing_epoch',s.attempt_fencing_epoch,'semantic_run_digest',s.semantic_run_digest,'controller_generation',s.controller_generation,'verification_run_id',s.verification_run_id),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.process_runs s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.task_id=p_task AND s.id=p_id AND (p_attempt IS NULL OR s.attempt_id=p_attempt);
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'agent_runs.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:AgentRun');
 RETURN jsonb_build_object('kind','AgentRun','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_agent_runs_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_agent_runs_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_agent_runs_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.tool_requests.read','tool_requests.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.tool_requests TO company_readback_functions_r54;
CREATE POLICY r54_tool_requests_read_read ON company.tool_requests FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.tool_requests.read' AND company_private.r54_allowed(tool_requests.tenant_id,tool_requests.project_id,'tool_requests.read',tool_requests.task_id,false)));
CREATE FUNCTION company_private.r54_tool_requests_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.tool_requests.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'tool_requests.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'task_id',s.task_id,'attempt_id',s.attempt_id,'request_id',s.request_id,'payload_digest',s.payload_digest,'receipt_id',s.receipt_id),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.tool_requests s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.task_id=p_task AND s.request_id=p_id AND s.attempt_id=p_attempt;
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'tool_requests.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:ToolRequest');
 RETURN jsonb_build_object('kind','ToolRequest','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_tool_requests_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_tool_requests_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_tool_requests_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.evidence.read','evidence.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.evidence TO company_readback_functions_r54;
CREATE POLICY r54_evidence_read_read ON company.evidence FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.evidence.read' AND company_private.r54_allowed(evidence.tenant_id,evidence.project_id,'evidence.read',evidence.task_id,false)));
CREATE FUNCTION company_private.r54_evidence_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.evidence.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'evidence.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'task_id',s.task_id,'attempt_id',s.attempt_id,'id',s.id,'verification_run_id',s.verification_run_id,'artifact_id',s.artifact_id,'command_receipt',s.command_receipt),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.evidence s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.task_id=p_task AND s.id=p_id AND s.attempt_id=p_attempt;
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'evidence.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:Evidence');
 RETURN jsonb_build_object('kind','Evidence','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_evidence_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_evidence_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_evidence_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r54.acceptance_decisions.read','acceptance_decisions.read','PROJECT','QUERY',0,NULL);
GRANT SELECT ON company.acceptance_records TO company_readback_functions_r54;
CREATE POLICY r54_acceptance_decisions_read_read ON company.acceptance_records FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.acceptance_decisions.read' AND company_private.r54_allowed(acceptance_records.tenant_id,acceptance_records.project_id,'acceptance_decisions.read',acceptance_records.task_id,false)));
CREATE FUNCTION company_private.r54_acceptance_decisions_read(p_task uuid,p_id uuid,p_attempt uuid DEFAULT NULL,p_expected_digest text DEFAULT NULL,p_ui_generation bigint DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; data jsonb; prefix bigint; gen bigint; d text; correlation uuid;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='candidate.r54.acceptance_decisions.read';
 IF p_id IS NULL OR p_ui_generation IS NULL OR p_ui_generation<0 OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'acceptance_decisions.read',p_task,false) THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED'; END IF;
 -- Record and event prefix are selected in ONE MVCC statement. This is not a persisted temporal snapshot.
 SELECT jsonb_build_object('tenant_id',s.tenant_id,'project_id',s.project_id,'task_id',s.task_id,'attempt_id',s.attempt_id,'id',s.id,'verification_run_id',s.verification_run_id,'evidence_id',s.evidence_id,'accepted_by',s.accepted_by,'build_digest',s.build_digest,'dirty_digest',s.dirty_digest,'created_at',s.created_at),h.committed_sequence,h.writer_generation INTO STRICT data,prefix,gen
 FROM company.acceptance_records s JOIN company.project_event_heads h ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.task_id=p_task AND s.id=p_id AND s.attempt_id=p_attempt;
 IF gen<>54 THEN RAISE EXCEPTION 'SNAPSHOT_GENERATION_UNSUPPORTED'; END IF;
 d=encode(sha256(convert_to(data::text,'UTF8')),'hex');
 IF p_expected_digest IS NOT NULL AND p_expected_digest<>d THEN RAISE EXCEPTION 'STALE_SOURCE_DIGEST'; END IF;
 IF NOT company_private.r54_allowed(x.tenant_id,x.project_id,'acceptance_decisions.read',p_task,false) THEN RAISE EXCEPTION 'DENIED_READ_RETURN_CUT'; END IF;
 correlation=gen_random_uuid();
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'Readback:AcceptanceDecision');
 RETURN jsonb_build_object('kind','AcceptanceDecision','record',data,'source_digest',d,'project_sequence',prefix,'event_writer_generation',gen,'authority_epoch',x.project_epoch,'ui_generation',p_ui_generation,'pagination',NULL,'command_receipt_ref',NULL,'access_audit_correlation',correlation);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'NOT_FOUND_OR_DENIED';
END $$;
ALTER FUNCTION company_private.r54_acceptance_decisions_read(uuid,uuid,uuid,text,bigint) OWNER TO company_readback_functions_r54;
REVOKE ALL ON FUNCTION company_private.r54_acceptance_decisions_read(uuid,uuid,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r54_acceptance_decisions_read(uuid,uuid,uuid,text,bigint) TO company_transport_r54;
CREATE POLICY r54_qualification_attempt_binding ON company.attempts FOR SELECT TO company_readback_functions_r54 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.operation_id='candidate.r54.qualifications.read' AND company_private.r54_allowed(attempts.tenant_id,attempts.project_id,'qualifications.read',attempts.task_id,false)));
ROLLBACK;
