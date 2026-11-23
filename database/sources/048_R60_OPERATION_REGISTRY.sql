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
 WHEN 'tasks.ready' THEN 'TaskReadied'
 WHEN 'engine.bind' THEN 'EngineBound'
 WHEN 'tool.consume' THEN 'ToolConsumed'
 WHEN 'tool.effect' THEN 'ToolEffectCommitted'
 WHEN 'process.lease_prepare' THEN 'LeasePrepared'
 WHEN 'process.lease_commit' THEN 'LeaseCommitted'
 WHEN 'process.lease_activate' THEN 'LeaseActivated'
 WHEN 'process.reconcile' THEN 'ProcessReconciled'
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
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('tasks.ready','tasks.ready','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('engine.bind','engine.bind','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('tool.consume','tool.consume','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('tool.effect','tool.effect','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.lease_prepare','process.lease_prepare','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.lease_commit','process.lease_commit','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.lease_activate','process.lease_activate','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.reconcile','process.reconcile','PROJECT','COMMAND',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.launch_delivery','process.launch_delivery','PROJECT','QUERY',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
INSERT INTO company_private.operation_permissions(operation_id,permission,scope_kind,execution_class,policy_revision,approved_policy_digest) VALUES('process.lease_read','process.lease_read','PROJECT','QUERY',0,NULL) ON CONFLICT(operation_id) DO NOTHING;
ROLLBACK;
