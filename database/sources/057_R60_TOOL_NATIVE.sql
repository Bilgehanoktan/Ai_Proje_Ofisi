BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r60_engine_bind(p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;c company.commands%ROWTYPE;j jsonb;
BEGIN
 x=company_private.r58_context('engine.bind');m=company_private.r58_attestation(p_attestation,'r60.engine-binding.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['engine_session_id','process_id','task_revision','tool_manifest_digest']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('attestation_id',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 r=company_private.r58_process_current((j->>'process_id')::uuid);a=company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);
 IF r.state IS DISTINCT FROM 'RUNNING' OR m.issuer_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id OR j->>'tool_manifest_digest' !~ '^[a-f0-9]{64}$'
 OR NOT EXISTS(SELECT 1 FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=r.task_id AND revision::text=j->>'task_revision')
 OR NOT EXISTS(SELECT 1 FROM company_private.r60_tool_manifests tm JOIN company.principals p ON p.tenant_id=tm.tenant_id AND p.id=tm.approved_by AND p.kind='HUMAN' WHERE tm.tenant_id=x.tenant_id AND tm.project_id=x.project_id AND tm.manifest_digest=j->>'tool_manifest_digest' AND tm.enabled) THEN RAISE EXCEPTION 'R60_ENGINE_BINDING_CURRENT'; END IF;
 INSERT INTO company_private.r60_engine_streams VALUES(x.tenant_id,x.project_id,(j->>'engine_session_id')::uuid,r.task_id,r.attempt_id,r.attempt_fencing_epoch,r.id,j->>'tool_manifest_digest',(j->>'task_revision')::bigint,1);
 RETURN company_private.r58_finish(c.id,r.id,jsonb_build_object('engine_session_id',j->>'engine_session_id','next_sequence',1));
END $$;
CREATE FUNCTION company_private.r60_tool_consume(p_kernel_request uuid,p_frame bytea,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;s company_private.r60_engine_streams%ROWTYPE;tr company.tool_requests%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;c company.commands%ROWTYPE;j jsonb;raw text;fd text;id uuid;auth jsonb;
BEGIN
 x=company_private.r58_context('tool.consume');
 IF p_frame IS NULL OR octet_length(p_frame) NOT BETWEEN 1 AND 65536 THEN RAISE EXCEPTION 'R60_FRAME_SIZE'; END IF;
 raw=convert_from(p_frame,'UTF8');
 IF right(raw,1)<>chr(10) OR position(chr(10) in left(raw,length(raw)-1))>0 THEN RAISE EXCEPTION 'R60_SINGLE_FRAME'; END IF;
 PERFORM company_private.r58_unique_json(raw::json);j=raw::jsonb;
 PERFORM company_private.r58_shape(j,ARRAY['protocol','request_id','engine_session_id','attempt_id','fencing_epoch','expected_revision','sequence','tool_manifest_digest','call']);
 IF jsonb_typeof(j->'fencing_epoch') IS DISTINCT FROM 'number' OR jsonb_typeof(j->'expected_revision') IS DISTINCT FROM 'number' OR jsonb_typeof(j->'sequence') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'R60_TYPED_FRAME_INTEGERS'; END IF;
 fd=encode(sha256(p_frame),'hex');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('kernel_request',p_kernel_request,'frame_digest',fd));
 IF c.state='SUCCEEDED' THEN RETURN jsonb_build_object('effect_permitted',false,'outcome','REPLAY_RECONCILE_ONLY'); END IF;
 SELECT * INTO STRICT s FROM company_private.r60_engine_streams WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=(j->>'engine_session_id')::uuid FOR UPDATE;
 a=company_private.r58_attempt(s.task_id,s.attempt_id,s.fence);r=company_private.r58_process_current(s.process_id);
 SELECT * INTO STRICT tr FROM company.tool_requests WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=s.task_id AND attempt_id=s.attempt_id AND request_id=p_kernel_request FOR UPDATE;
 SELECT payload INTO STRICT auth FROM company_private.r58_execution_receipts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND operation='tool.authorize_final' AND target_id=tr.request_id;
 IF j->>'protocol' IS DISTINCT FROM 'company-tool/1' OR j->>'attempt_id' IS DISTINCT FROM s.attempt_id::text OR j->>'fencing_epoch' IS DISTINCT FROM s.fence::text OR j->>'expected_revision' IS DISTINCT FROM s.task_revision::text OR j->>'sequence' IS DISTINCT FROM s.next_sequence::text OR j->>'tool_manifest_digest' IS DISTINCT FROM s.manifest_digest
 OR a.worker_id IS DISTINCT FROM x.principal_id OR r.state IS DISTINCT FROM 'RUNNING' OR tr.payload_digest IS DISTINCT FROM fd OR tr.request_fencing_epoch IS DISTINCT FROM s.fence OR tr.receipt_id IS NOT NULL
 OR auth->>'tool' IS DISTINCT FROM j->'call'->>'tool_id' OR auth->>'process_id' IS DISTINCT FROM r.id::text
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND head_digest=auth->>'head_digest')
 OR EXISTS(SELECT 1 FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=s.engine_session_id AND state IN ('CONSUMED','UNKNOWN'))
 OR NOT EXISTS(SELECT 1 FROM company_private.r60_tool_manifests WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND manifest_digest=s.manifest_digest AND enabled)
 OR EXISTS(SELECT 1 FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state IN ('PREPARED','COMMITTED')) THEN RAISE EXCEPTION 'R60_TOOL_BINDING_OR_PENDING'; END IF;
 IF j->'call'->>'tool_id'='workspace.read' THEN
  PERFORM company_private.r58_shape(j->'call',ARRAY['tool_id','arguments']);PERFORM company_private.r58_shape(j->'call'->'arguments',ARRAY['relative_path','max_bytes']);
  IF j->'call'->'arguments'->>'relative_path' IS DISTINCT FROM 'task_title.py' OR jsonb_typeof(j->'call'->'arguments'->'max_bytes') IS DISTINCT FROM 'number' OR (j->'call'->'arguments'->>'max_bytes') !~ '^[0-9]+$' OR (j->'call'->'arguments'->>'max_bytes')::bigint NOT BETWEEN 1 AND 16384 THEN RAISE EXCEPTION 'R60_PILOT_READ_SCOPE'; END IF;
 ELSIF j->'call'->>'tool_id'='patch.apply' THEN
  PERFORM company_private.r58_shape(j->'call',ARRAY['tool_id','patch_artifact_id','expected_source_digest']);
  PERFORM (j->'call'->>'patch_artifact_id')::uuid;
  IF j->'call'->>'expected_source_digest' IS DISTINCT FROM auth->>'head_digest' THEN RAISE EXCEPTION 'R60_PATCH_SOURCE_CAS'; END IF;
 ELSE RAISE EXCEPTION 'R60_INDEPENDENT_VERIFIER_OR_UNKNOWN_TOOL'; END IF;
 id=gen_random_uuid();
 INSERT INTO company_private.r60_tool_consumptions VALUES(x.tenant_id,x.project_id,id,s.engine_session_id,(j->>'request_id')::uuid,tr.request_id,s.next_sequence,r.id,fd,p_frame,'CONSUMED',NULL,c.id);
 RETURN company_private.r58_finish(c.id,id,jsonb_build_object('consume_id',id,'effect_permitted',true,'frame_digest',fd));
END $$;
CREATE FUNCTION company_private.r60_effect_guard(p_consume uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;u company_private.r60_tool_consumptions%ROWTYPE;s company_private.r60_engine_streams%ROWTYPE;r company.process_runs%ROWTYPE;auth jsonb;
BEGIN
 x=company_private.r58_context('tool.effect');
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 SELECT * INTO STRICT u FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume FOR UPDATE;
 SELECT * INTO STRICT s FROM company_private.r60_engine_streams WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=u.engine_session_id FOR UPDATE;
 r=company_private.r58_process_current(u.process_id);PERFORM company_private.r58_attempt(s.task_id,s.attempt_id,s.fence);
 SELECT payload INTO STRICT auth FROM company_private.r58_execution_receipts WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND operation='tool.authorize_final' AND target_id=u.kernel_request_id;
 IF u.state IS DISTINCT FROM 'CONSUMED' OR x.principal_id IS DISTINCT FROM r.controller_id OR r.state IS DISTINCT FROM 'RUNNING' OR x.task_id IS DISTINCT FROM s.task_id OR x.attempt_id IS DISTINCT FROM s.attempt_id OR s.next_sequence IS DISTINCT FROM u.sequence
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND head_digest=auth->>'head_digest')
 OR EXISTS(SELECT 1 FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state IN ('PREPARED','COMMITTED')) THEN RAISE EXCEPTION 'R60_EFFECT_NOT_CURRENT'; END IF;
 RETURN jsonb_build_object('consume_id',u.id,'frame_digest',u.frame_digest,'frame_base64',encode(u.frame_bytes,'base64'),'process_id',r.id,'base_head',auth->>'head_digest');
END $$;
CREATE FUNCTION company_private.r60_effect_complete(p_consume uuid,p_proof uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;u company_private.r60_tool_consumptions%ROWTYPE;m company_private.r58_attestations%ROWTYPE;c company.commands%ROWTYPE;g jsonb;j jsonb;
BEGIN
 x=company_private.r58_context('tool.effect');g=company_private.r60_effect_guard(p_consume);
 m=company_private.r58_attestation(p_proof,'r60.tool-effect.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['consume_id','frame_digest','process_id','base_head','result_head','effect_digest','outcome','effect']);
 IF m.issuer_id IS DISTINCT FROM x.principal_id OR j->>'consume_id' IS DISTINCT FROM p_consume::text OR j->>'frame_digest' IS DISTINCT FROM g->>'frame_digest' OR j->>'process_id' IS DISTINCT FROM g->>'process_id' OR j->>'base_head' IS DISTINCT FROM g->>'base_head' OR j->>'result_head' !~ '^[a-f0-9]{64}$' OR j->>'effect_digest' !~ '^[a-f0-9]{64}$' OR j->>'outcome' IS DISTINCT FROM 'SUCCEEDED' THEN RAISE EXCEPTION 'R60_EFFECT_PROOF_BINDING'; END IF;
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('consume_id',p_consume,'proof_id',p_proof));
 SELECT * INTO STRICT u FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume;
 UPDATE company_private.r60_tool_consumptions SET state='SUCCEEDED',effect_attestation_id=m.id WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume AND state='CONSUMED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_EFFECT_CAS'; END IF;
 UPDATE company_private.r60_engine_streams SET next_sequence=next_sequence+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=u.engine_session_id AND next_sequence=u.sequence;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_SEQUENCE_CAS'; END IF;
 RETURN company_private.r58_finish(c.id,m.id,jsonb_build_object('consume_id',u.id,'frame_digest',u.frame_digest,'receipt_id',m.id,'status','SUCCEEDED','artifact_ids',jsonb_build_array(m.id)));
END $$;
CREATE FUNCTION company_private.r60_effect_finish(p_consume uuid,p_proof uuid,p_key_id uuid,p_key_revision bigint,p_raw bytea,p_tag bytea,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;
BEGIN
 x=company_private.r58_context('tool.effect');
 PERFORM company_private.r60_effect_guard(p_consume);
 PERFORM company_private.r60_store_effect_proof(p_proof,x.principal_id,p_key_id,p_key_revision,'r60.tool-effect.v1',p_raw,p_tag);
 RETURN company_private.r60_effect_complete(p_consume,p_proof,p_key,p_correlation);
END $$;
ROLLBACK;
