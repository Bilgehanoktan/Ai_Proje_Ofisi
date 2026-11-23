BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

DO $$ BEGIN IF (SELECT count(*) FROM company_private.operation_permissions WHERE operation_id IN ('CAP-017.revoke','e0.setup_mandate_consume','e0.qualification_candidate_issue','e0.evaluation_artifact_record','qualification.activate','qualification.revoke') AND scope_kind='PROJECT' AND execution_class IN ('COMMAND','SPECIAL'))<>6 THEN RAISE EXCEPTION 'R64_EXISTING_OPERATION_REGISTRY_REQUIRED'; END IF; END $$;
CREATE OR REPLACE FUNCTION company_private.r55_cp_event_kind(p_operation text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT CASE p_operation
 WHEN 'CAP-017.revoke' THEN 'GrantRevoked'
 WHEN 'e0.setup_mandate_consume' THEN 'E0MandateConsumed'
 WHEN 'e0.qualification_candidate_issue' THEN 'QualificationCandidateIssued'
 WHEN 'e0.evaluation_artifact_record' THEN 'E0ReportRecorded'
 WHEN 'qualification.activate' THEN 'QUALIFICATION_ACTIVATE'
 WHEN 'qualification.revoke' THEN 'QUALIFICATION_REVOKE'

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
GRANT EXECUTE ON FUNCTION company_private.r55_cp_event_kind(text) TO company_atomic_functions_r55, company_execution_functions_r58;
ROLLBACK;
