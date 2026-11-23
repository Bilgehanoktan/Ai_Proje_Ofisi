BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_patch_receipt(p_task uuid,p_attempt uuid,p_fence bigint,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;h company_private.r58_workspace_heads%ROWTYPE;tr company.tool_requests%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;c company.commands%ROWTYPE;j jsonb;rid uuid;
BEGIN
 x=company_private.r58_context('patch.receipt');m=company_private.r58_attestation(p_attestation,'r58.patch.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['task_id','attempt_id','fencing_epoch','base_head','result_head','patch_digest','tool_request_id','process_id','request_digest','receipt_artifact_id']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 IF NOT EXISTS(SELECT 1 FROM company_private.r60_tool_consumptions u JOIN company_private.r58_attestations effect_proof ON effect_proof.tenant_id=u.tenant_id AND effect_proof.project_id=u.project_id AND effect_proof.id=u.effect_attestation_id WHERE u.tenant_id=x.tenant_id AND u.project_id=x.project_id AND u.kernel_request_id=(j->>'tool_request_id')::uuid AND u.process_id=(j->>'process_id')::uuid AND u.frame_digest=j->>'request_digest' AND u.state='SUCCEEDED' AND effect_proof.profile='r60.tool-effect.v1' AND effect_proof.payload->>'base_head'=j->>'base_head' AND effect_proof.payload->>'result_head'=j->>'result_head' AND effect_proof.payload->>'effect_digest'=j->>'patch_digest') THEN RAISE EXCEPTION 'R60_COMPLETED_PATCH_EFFECT_REQUIRED'; END IF;
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR UPDATE;
 SELECT * INTO STRICT tr FROM company.tool_requests WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt AND request_id=(j->>'tool_request_id')::uuid FOR UPDATE;
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=(j->>'process_id')::uuid AND state='RUNNING';
 PERFORM company_private.r58_process_current(cap.process_id);
 IF j->>'task_id' IS DISTINCT FROM p_task::text OR j->>'attempt_id' IS DISTINCT FROM p_attempt::text OR j->>'fencing_epoch' IS DISTINCT FROM p_fence::text
 OR j->>'base_head' IS DISTINCT FROM h.head_digest OR j->>'base_head' IS DISTINCT FROM cap.tuple->>'head_digest' OR j->>'result_head' !~ '^[a-f0-9]{64}$' OR j->>'patch_digest' !~ '^[a-f0-9]{64}$'
 OR tr.receipt_id IS NOT NULL OR tr.payload_digest IS DISTINCT FROM j->>'request_digest' OR tr.request_fencing_epoch IS DISTINCT FROM p_fence
 OR j->>'receipt_artifact_id' IS DISTINCT FROM m.id::text OR NOT EXISTS(SELECT 1 FROM company.artifacts ar WHERE ar.tenant_id=x.tenant_id AND ar.project_id=x.project_id AND ar.task_id=p_task AND ar.attempt_id=p_attempt AND ar.id=m.id AND ar.state='AVAILABLE' AND ar.sha256=m.raw_digest)
 OR m.issuer_id::text IS DISTINCT FROM cap.tuple->>'controller_id' OR m.issuer_id=a.worker_id
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_execution_receipts rr WHERE rr.tenant_id=x.tenant_id AND rr.project_id=x.project_id AND rr.operation='tool.authorize_final' AND rr.target_id=tr.request_id AND rr.payload->>'tool'='patch.apply' AND rr.payload->>'head_digest'=h.head_digest AND rr.payload->>'process_id'=j->>'process_id') THEN RAISE EXCEPTION 'R58_PATCH_PROVENANCE'; END IF;
 rid=m.id;
 INSERT INTO company_private.r58_patch_receipts VALUES(x.tenant_id,x.project_id,p_task,p_attempt,rid,p_fence,h.head_digest,j->>'result_head',j->>'patch_digest',tr.request_id,m.id,c.id);
 UPDATE company_private.r58_workspace_heads SET revision=revision+1,head_digest=j->>'result_head',attestation_id=m.id WHERE tenant_id=h.tenant_id AND project_id=h.project_id AND revision=h.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PATCH_HEAD_CAS'; END IF;
 UPDATE company.tool_requests SET receipt_id=rid WHERE tenant_id=tr.tenant_id AND attempt_id=tr.attempt_id AND request_id=tr.request_id AND receipt_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PATCH_TOOL_RECEIPT_CAS'; END IF;
 UPDATE company.attempts SET state='PRODUCED' WHERE tenant_id=a.tenant_id AND project_id=a.project_id AND task_id=a.task_id AND id=a.id;
 UPDATE company.tasks SET state='VERIFYING',revision=revision+1 WHERE tenant_id=a.tenant_id AND project_id=a.project_id AND id=a.task_id AND active_attempt_id=a.id AND fencing_epoch=p_fence AND state='RUNNING';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PATCH_TASK_CAS'; END IF;
 RETURN company_private.r58_finish(c.id,rid,jsonb_build_object('patch_id',rid,'result_head',j->>'result_head','patch_digest',j->>'patch_digest','attestation',m.id));
END $$;
ROLLBACK;
