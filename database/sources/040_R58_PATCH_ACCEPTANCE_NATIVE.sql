BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r58_tool_authorize_final(p_task uuid,p_attempt uuid,p_fence bigint,p_process uuid,p_tool text,p_request_digest text,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;r company.process_runs%ROWTYPE;lp company_private.r58_lease_policies%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;h company_private.r58_workspace_heads%ROWTYPE;c company.commands%ROWTYPE;rid uuid;
BEGIN
 x=company_private.r58_context('tool.authorize_final');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'process_id',p_process,'tool',p_tool,'request_digest',p_request_digest));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 SELECT * INTO STRICT lp FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=a.r58_policy_revision AND enabled FOR SHARE;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR SHARE;
 PERFORM company_private.r58_process_current(r.id);
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state='RUNNING';
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 IF p_tool IS NULL OR NOT ((p_tool=ANY(lp.allowed_tools)) IS TRUE) OR p_request_digest IS NULL OR p_request_digest !~ '^[a-f0-9]{64}$'
 OR a.worker_id IS DISTINCT FROM x.principal_id OR r.state IS DISTINCT FROM 'RUNNING' OR r.attempt_id IS DISTINCT FROM a.id OR r.task_id IS DISTINCT FROM a.task_id OR r.attempt_fencing_epoch IS DISTINCT FROM p_fence OR r.qualification_id IS DISTINCT FROM a.admission_qualification_id
 OR cap.tuple->>'head_digest' IS DISTINCT FROM h.head_digest OR cap.callback_attestation_id IS NULL THEN RAISE EXCEPTION 'R58_TOOL_EXACT_CURRENT_AUTHORITY'; END IF;
 PERFORM company_private.r58_attestation(cap.callback_attestation_id,'r58.launch-callback.v1');
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
 rid=gen_random_uuid();
 INSERT INTO company.tool_requests(tenant_id,project_id,task_id,attempt_id,request_id,payload_digest,request_fencing_epoch) VALUES(x.tenant_id,x.project_id,p_task,p_attempt,rid,p_request_digest,p_fence);
 RETURN company_private.r58_finish(c.id,rid,jsonb_build_object('request_id',rid,'process_id',r.id,'head_digest',h.head_digest,'tool',p_tool,'request_digest',p_request_digest,'os_effect_performed',false));
END $$;

CREATE FUNCTION company_private.r58_patch_receipt(p_task uuid,p_attempt uuid,p_fence bigint,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;h company_private.r58_workspace_heads%ROWTYPE;tr company.tool_requests%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;c company.commands%ROWTYPE;j jsonb;rid uuid;
BEGIN
 x=company_private.r58_context('patch.receipt');m=company_private.r58_attestation(p_attestation,'r58.patch.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['task_id','attempt_id','fencing_epoch','base_head','result_head','patch_digest','tool_request_id','process_id','request_digest','receipt_artifact_id']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
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

CREATE FUNCTION company_private.r58_verification_final_seal(p_task uuid,p_attempt uuid,p_fence bigint,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;pm company_private.r58_attestations%ROWTYPE;patch company_private.r58_patch_receipts%ROWTYPE;profile company_private.r58_verification_profiles%ROWTYPE;h company_private.r58_workspace_heads%ROWTYPE;c company.commands%ROWTYPE;j jsonb;vid uuid;sd text;
BEGIN
 x=company_private.r58_context('verification.final_seal');m=company_private.r58_attestation(p_attestation,'r58.verification.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['patch_id','head_digest','profile_digest','build_digest','results','report_artifact_id','kind','acceptance_criteria_digest']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 SELECT * INTO STRICT patch FROM company_private.r58_patch_receipts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=(j->>'patch_id')::uuid;
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 SELECT * INTO STRICT profile FROM company_private.r58_verification_profiles WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND profile_digest=a.r58_verification_profile_digest AND enabled FOR SHARE;
 pm=company_private.r58_attestation(patch.attestation_id,'r58.patch.v1');
 IF j->>'kind' IS DISTINCT FROM 'ORDINARY' OR j->>'profile_digest' IS DISTINCT FROM profile.profile_digest OR j->>'head_digest' IS DISTINCT FROM h.head_digest OR patch.result_head IS DISTINCT FROM h.head_digest OR patch.task_id IS DISTINCT FROM p_task OR patch.attempt_id IS DISTINCT FROM p_attempt OR patch.fence IS DISTINCT FROM p_fence
 OR m.issuer_id=a.worker_id OR m.issuer_id=pm.issuer_id OR m.issuer_id IS DISTINCT FROM x.principal_id OR j->>'build_digest' !~ '^[a-f0-9]{64}$' OR jsonb_typeof(j->'results') IS DISTINCT FROM 'array'
 OR NOT EXISTS(SELECT 1 FROM company.tasks t WHERE t.tenant_id=x.tenant_id AND t.project_id=x.project_id AND t.id=p_task AND j->>'acceptance_criteria_digest'=encode(sha256(convert_to(t.acceptance_criteria::text,'UTF8')),'hex'))
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=profile.approved_by AND kind='HUMAN') THEN RAISE EXCEPTION 'R58_ORDINARY_SEAL_CURRENT_BINDING'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(j->'results') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'object' OR NOT ((z ?& ARRAY['oracle_id','outcome','artifact_digest']) IS TRUE) OR (SELECT count(*) FROM jsonb_object_keys(z))<>3 OR z->>'outcome' IS DISTINCT FROM 'PASS' OR jsonb_typeof(z->'oracle_id') IS DISTINCT FROM 'string' OR jsonb_typeof(z->'artifact_digest') IS DISTINCT FROM 'string' OR z->>'artifact_digest' !~ '^[a-f0-9]{64}$')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(profile.oracle_ids) z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string' OR length(z#>>'{}')=0)
 OR (SELECT count(*)<>count(DISTINCT value) FROM jsonb_array_elements_text(profile.oracle_ids))
 OR (SELECT count(*)<>count(DISTINCT value->>'oracle_id') FROM jsonb_array_elements(j->'results'))
 OR EXISTS((SELECT value FROM jsonb_array_elements_text(profile.oracle_ids)) EXCEPT (SELECT value->>'oracle_id' FROM jsonb_array_elements(j->'results')))
 OR EXISTS((SELECT value->>'oracle_id' FROM jsonb_array_elements(j->'results')) EXCEPT (SELECT value FROM jsonb_array_elements_text(profile.oracle_ids)))
 OR NOT EXISTS(SELECT 1 FROM company.artifacts art WHERE art.tenant_id=x.tenant_id AND art.project_id=x.project_id AND art.task_id=p_task AND art.attempt_id=p_attempt AND art.id=(j->>'report_artifact_id')::uuid AND art.state='AVAILABLE' AND art.sha256=m.raw_digest) THEN RAISE EXCEPTION 'R58_EXACT_REQUIRED_ORACLE_MANIFEST'; END IF;
 vid=gen_random_uuid();sd=encode(sha256(convert_to(jsonb_build_array(patch.id,h.head_digest,profile.profile_digest,m.raw_digest,j->'results')::text,'UTF8')),'hex');
 INSERT INTO company.verification_runs(tenant_id,project_id,task_id,attempt_id,id,producer_id,verifier_id,profile_version,build_digest,dirty_digest,result,exit_code,source_report_artifact_id)
 VALUES(x.tenant_id,x.project_id,p_task,p_attempt,vid,a.worker_id,m.issuer_id,profile.profile_digest,j->>'build_digest',patch.patch_digest,'PASS',0,(j->>'report_artifact_id')::uuid);
 INSERT INTO company_private.r58_verification_seals VALUES(x.tenant_id,x.project_id,p_task,p_attempt,vid,patch.id,h.head_digest,m.id,sd,c.id);
 RETURN company_private.r58_finish(c.id,vid,jsonb_build_object('verification_id',vid,'seal_digest',sd,'head_digest',h.head_digest,'patch_id',patch.id));
END $$;

CREATE FUNCTION company_private.r58_evidence_provenance(p_task uuid,p_attempt uuid,p_fence bigint,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;s company_private.r58_verification_seals%ROWTYPE;v company.verification_runs%ROWTYPE;c company.commands%ROWTYPE;j jsonb;eid uuid;
BEGIN
 x=company_private.r58_context('evidence.provenance');m=company_private.r58_attestation(p_attestation,'r58.evidence.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['verification_id','seal_digest','artifact_id','artifact_digest','head_digest']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 SELECT * INTO STRICT s FROM company_private.r58_verification_seals WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt AND verification_id=(j->>'verification_id')::uuid;
 SELECT * INTO STRICT v FROM company.verification_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt AND id=s.verification_id AND result='PASS';
 IF m.issuer_id=a.worker_id OR m.issuer_id=v.verifier_id OR m.issuer_id IS DISTINCT FROM x.principal_id OR j->>'seal_digest' IS DISTINCT FROM s.seal_digest OR j->>'head_digest' IS DISTINCT FROM s.head_digest
 OR EXISTS(SELECT 1 FROM company_private.r58_patch_receipts p JOIN company_private.r58_attestations pm ON pm.tenant_id=p.tenant_id AND pm.project_id=p.project_id AND pm.id=p.attestation_id WHERE p.tenant_id=x.tenant_id AND p.project_id=x.project_id AND p.id=s.patch_id AND pm.issuer_id=m.issuer_id)
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND head_digest=s.head_digest)
 OR NOT EXISTS(SELECT 1 FROM company.artifacts art WHERE art.tenant_id=x.tenant_id AND art.project_id=x.project_id AND art.task_id=p_task AND art.attempt_id=p_attempt AND art.id=(j->>'artifact_id')::uuid AND art.state='AVAILABLE' AND art.sha256=j->>'artifact_digest') THEN RAISE EXCEPTION 'R58_EVIDENCE_EXACT_PROVENANCE'; END IF;
 PERFORM company_private.r58_attestation(s.attestation_id,'r58.verification.v1');eid=gen_random_uuid();
 INSERT INTO company.evidence(tenant_id,project_id,task_id,attempt_id,id,verification_run_id,artifact_id,command_receipt) VALUES(x.tenant_id,x.project_id,p_task,p_attempt,eid,s.verification_id,(j->>'artifact_id')::uuid,c.id);
 INSERT INTO company_private.r58_evidence_provenance VALUES(x.tenant_id,x.project_id,p_task,p_attempt,eid,m.id,s.head_digest,s.seal_digest,c.id);
 RETURN company_private.r58_finish(c.id,eid,jsonb_build_object('evidence_id',eid,'verification_id',s.verification_id,'seal_digest',s.seal_digest,'head_digest',s.head_digest));
END $$;

CREATE FUNCTION company_private.r58_verification_accept(p_task uuid,p_attempt uuid,p_fence bigint,p_revision bigint,p_evidence uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;t company.tasks%ROWTYPE;e company.evidence%ROWTYPE;ep company_private.r58_evidence_provenance%ROWTYPE;s company_private.r58_verification_seals%ROWTYPE;v company.verification_runs%ROWTYPE;m company_private.r58_attestations%ROWTYPE;patch company_private.r58_patch_receipts%ROWTYPE;pm company_private.r58_attestations%ROWTYPE;h company_private.r58_workspace_heads%ROWTYPE;c company.commands%ROWTYPE;acceptance_id uuid;
BEGIN
 x=company_private.r58_context('verification.accept');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'expected_revision',p_revision,'evidence_id',p_evidence));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task FOR UPDATE;
 SELECT * INTO STRICT e FROM company.evidence WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt AND id=p_evidence;
 SELECT * INTO STRICT ep FROM company_private.r58_evidence_provenance WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND evidence_id=e.id;
 SELECT * INTO STRICT s FROM company_private.r58_verification_seals WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND verification_id=e.verification_run_id;
 SELECT * INTO STRICT v FROM company.verification_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt AND id=s.verification_id;
 SELECT * INTO STRICT patch FROM company_private.r58_patch_receipts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=s.patch_id;
 m=company_private.r58_attestation(ep.attestation_id,'r58.evidence.v1');pm=company_private.r58_attestation(patch.attestation_id,'r58.patch.v1');
 PERFORM company_private.r58_attestation(s.attestation_id,'r58.verification.v1');
 IF t.state IS DISTINCT FROM 'VERIFYING' OR t.revision IS DISTINCT FROM p_revision OR v.result IS DISTINCT FROM 'PASS' OR v.exit_code IS DISTINCT FROM 0
 OR x.principal_id IN (a.worker_id,v.verifier_id,m.issuer_id,pm.issuer_id)
 OR ep.head_digest IS DISTINCT FROM h.head_digest OR s.head_digest IS DISTINCT FROM h.head_digest OR patch.result_head IS DISTINCT FROM h.head_digest OR ep.seal_digest IS DISTINCT FROM s.seal_digest
 OR NOT EXISTS(SELECT 1 FROM company.artifacts art WHERE art.tenant_id=e.tenant_id AND art.project_id=e.project_id AND art.task_id=e.task_id AND art.attempt_id=e.attempt_id AND art.id=e.artifact_id AND art.state='AVAILABLE' AND art.sha256=m.payload->>'artifact_digest') THEN RAISE EXCEPTION 'R58_INDEPENDENT_ACCEPTANCE_CURRENT_EVIDENCE'; END IF;
 acceptance_id=gen_random_uuid();
 INSERT INTO company.acceptance_records(tenant_id,project_id,task_id,attempt_id,id,verification_run_id,evidence_id,accepted_by,build_digest,dirty_digest) VALUES(x.tenant_id,x.project_id,p_task,p_attempt,acceptance_id,v.id,e.id,x.principal_id,v.build_digest,v.dirty_digest);
 UPDATE company.tasks SET state='ACCEPTED',revision=revision+1 WHERE tenant_id=t.tenant_id AND project_id=t.project_id AND id=t.id AND revision=p_revision AND active_attempt_id=a.id AND fencing_epoch=p_fence AND state='VERIFYING';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ACCEPTANCE_CAS'; END IF;
 RETURN company_private.r58_finish(c.id,t.id,jsonb_build_object('task_id',t.id,'attempt_id',a.id,'acceptance_id',acceptance_id,'state','ACCEPTED','task_revision',p_revision+1,'head_digest',h.head_digest,'evidence_id',e.id,'seal_digest',s.seal_digest,'acceptor_id',x.principal_id));
END $$;
ROLLBACK;
