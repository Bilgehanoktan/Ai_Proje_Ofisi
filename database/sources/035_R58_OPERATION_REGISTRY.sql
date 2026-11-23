BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r55_cp_event_kind(p_operation text) RETURNS text
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
 WHEN 'worker.claim' THEN 'WorkerClaimed'
 WHEN 'worker.heartbeat' THEN 'WorkerHeartbeat'
 WHEN 'workspace.current_head' THEN 'WorkspaceHeadUpdated'
 WHEN 'process.launch_reserve' THEN 'LaunchReserved'
 WHEN 'process.launch_consume' THEN 'LaunchConsumed'
 WHEN 'process.launch_callback' THEN 'LaunchCallbackRecorded'
 WHEN 'tool.authorize_final' THEN 'ToolAuthorized'
 WHEN 'patch.receipt' THEN 'PatchReceiptPersisted'
 WHEN 'verification.final_seal' THEN 'VerificationSealed'
 WHEN 'evidence.provenance' THEN 'EvidenceProvenanceRecorded'
 WHEN 'verification.accept' THEN 'TaskAccepted'
 WHEN 'evidence.attestation_ingest' THEN 'ExecutionAttestationIngested'
 WHEN 'process.stop_release' THEN 'ProcessStoppedAndReleased'
 END;
$$;
REVOKE ALL ON FUNCTION company_private.r55_cp_event_kind(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_event_kind(text) TO company_atomic_functions_r55,company_first_run_functions_r53;

INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('worker.claim','worker.claim','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('worker.heartbeat','worker.heartbeat','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('workspace.current_head','workspace.current_head','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.launch_reserve','process.launch_reserve','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.launch_consume','process.launch_consume','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.launch_callback','process.launch_callback','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('tool.authorize_final','tool.authorize_final','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('patch.receipt','patch.receipt','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('verification.final_seal','verification.final_seal','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('evidence.provenance','evidence.provenance','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('verification.accept','verification.accept','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('evidence.attestation_ingest','evidence.attestation_ingest','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.stop_release','process.stop_release','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM company_private.operation_permissions WHERE operation_id=ANY(ARRAY['worker.claim','worker.heartbeat','workspace.current_head','process.launch_reserve','process.launch_consume','process.launch_callback','tool.authorize_final','patch.receipt','verification.final_seal','evidence.provenance','verification.accept','evidence.attestation_ingest','process.stop_release']) AND (permission IS DISTINCT FROM operation_id OR scope_kind IS DISTINCT FROM 'PROJECT' OR execution_class IS DISTINCT FROM 'COMMAND')) THEN RAISE EXCEPTION 'R58_OPERATION_REGISTRY_CONFLICT'; END IF; END $$;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('candidate.r58.artifacts.read','artifacts.read','PROJECT','QUERY',0,NULL) ON CONFLICT(operation_id) DO NOTHING;

-- New application bootstrap definitions. Inactive revision 0 / NULL policy.
-- Explicit permission-label choices, not historical approval or grant issuance.
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('CAP-017.revoke','cap-017.revoke','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('e0.setup_mandate_consume','e0.setup_mandate_consume','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('e0.qualification_candidate_issue','e0.qualification_candidate_issue','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('e0.evaluation_artifact_record','e0.evaluation_artifact_record','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('qualification.activate','qualification.activate','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('qualification.revoke','qualification.revoke','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('objectives.create','objectives.create','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('plans.create','plans.create','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('tasks.create','tasks.create','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM (VALUES ('CAP-017.revoke','cap-017.revoke'),('e0.setup_mandate_consume','e0.setup_mandate_consume'),('e0.qualification_candidate_issue','e0.qualification_candidate_issue'),('e0.evaluation_artifact_record','e0.evaluation_artifact_record'),('qualification.activate','qualification.activate'),('qualification.revoke','qualification.revoke'),('objectives.create','objectives.create'),('plans.create','plans.create'),('tasks.create','tasks.create')) AS expected(operation_id,permission) JOIN company_private.operation_permissions actual USING(operation_id) WHERE actual.permission IS DISTINCT FROM expected.permission OR actual.scope_kind IS DISTINCT FROM 'PROJECT' OR actual.execution_class IS DISTINCT FROM 'COMMAND') THEN RAISE EXCEPTION 'APPLICATION_BOOTSTRAP_REGISTRY_CONFLICT'; END IF; END $$;

-- Explicit bootstrap-only definitions; inactive, not a grant.
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('projects.read','projects.read','PROJECT','QUERY',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM company_private.operation_permissions WHERE operation_id='projects.read' AND (permission IS DISTINCT FROM 'projects.read' OR scope_kind IS DISTINCT FROM 'PROJECT' OR execution_class IS DISTINCT FROM 'QUERY')) THEN RAISE EXCEPTION 'BOOTSTRAP_DEFINITION_CONFLICT'; END IF; END $$;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('projects.create','projects.create','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM company_private.operation_permissions WHERE operation_id='projects.create' AND (permission IS DISTINCT FROM 'projects.create' OR scope_kind IS DISTINCT FROM 'PROJECT' OR execution_class IS DISTINCT FROM 'COMMAND')) THEN RAISE EXCEPTION 'BOOTSTRAP_DEFINITION_CONFLICT'; END IF; END $$;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('e0.evaluation_attempt_create','e0.evaluation_attempt_create','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM company_private.operation_permissions WHERE operation_id='e0.evaluation_attempt_create' AND (permission IS DISTINCT FROM 'e0.evaluation_attempt_create' OR scope_kind IS DISTINCT FROM 'PROJECT' OR execution_class IS DISTINCT FROM 'COMMAND')) THEN RAISE EXCEPTION 'BOOTSTRAP_DEFINITION_CONFLICT'; END IF; END $$;
ROLLBACK;
