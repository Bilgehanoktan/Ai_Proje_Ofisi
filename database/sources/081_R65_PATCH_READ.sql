-- Inert source candidate; no migration or enrollment is authorized here.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r65_effect_guard(p_consume uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;u company_private.r60_tool_consumptions%ROWTYPE;s company_private.r60_engine_streams%ROWTYPE;g jsonb;
BEGIN
 g=company_private.r60_effect_guard(p_consume);
 x=company_private.r58_context('tool.effect');
 SELECT * INTO STRICT u FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume;
 SELECT * INTO STRICT s FROM company_private.r60_engine_streams WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=u.engine_session_id;
 RETURN g||jsonb_build_object('task_id',s.task_id,'attempt_id',s.attempt_id,'fencing_epoch',s.fence,'engine_session_id',s.engine_session_id,'tool_manifest_digest',s.manifest_digest,'sequence',u.sequence,'request_id',u.engine_request_id,'kernel_request_id',u.kernel_request_id);
END $$;
ALTER FUNCTION company_private.r65_effect_guard(uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r65_effect_guard(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r65_effect_guard(uuid) TO company_transport_r54,company_execution_functions_r58;

CREATE FUNCTION company_private.r65_patch_artifact_read(p_consume uuid,p_artifact uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;g jsonb;j jsonb;frame jsonb;p jsonb;raw bytea;replacement bytea;
BEGIN
 -- Re-enters the SAME tool.effect context and holds its revocation/attempt/
 -- process/sequence/head locks. No detached artifact-read transaction.
 g=company_private.r65_effect_guard(p_consume);x=company_private.r58_context('tool.effect');
 frame=convert_from(decode(g->>'frame_base64','base64'),'UTF8')::jsonb;
 IF frame->'call'->>'tool_id' IS DISTINCT FROM 'patch.apply' OR frame->'call'->>'patch_artifact_id' IS DISTINCT FROM p_artifact::text THEN RAISE EXCEPTION 'R65_EXACT_CONSUMED_PATCH_REQUIRED'; END IF;
 m=company_private.r58_attestation(p_artifact,'r60.patch-proposal.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['task_id','attempt_id','fencing_epoch','process_id','engine_session_id','tool_manifest_digest','sequence','request_id','expected_source_digest','artifact_digest','artifact_base64']);
 IF m.issuer_id IS DISTINCT FROM x.principal_id
 OR j->>'task_id' IS DISTINCT FROM g->>'task_id' OR j->>'attempt_id' IS DISTINCT FROM g->>'attempt_id'
 OR j->>'fencing_epoch' IS DISTINCT FROM g->>'fencing_epoch' OR j->>'process_id' IS DISTINCT FROM g->>'process_id'
 OR j->>'engine_session_id' IS DISTINCT FROM g->>'engine_session_id' OR j->>'tool_manifest_digest' IS DISTINCT FROM g->>'tool_manifest_digest'
 OR j->>'sequence' IS DISTINCT FROM g->>'sequence' OR j->>'request_id' IS DISTINCT FROM g->>'request_id'
 OR j->>'expected_source_digest' IS DISTINCT FROM g->>'base_head'
 OR frame->'call'->>'expected_source_digest' IS DISTINCT FROM g->>'base_head'
 OR jsonb_typeof(j->'artifact_base64') IS DISTINCT FROM 'string' OR length(j->>'artifact_base64')>43692
 OR (j->>'artifact_base64') !~ '^[A-Za-z0-9+/]*={0,2}$'
 OR (j->>'artifact_digest') !~ '^[a-f0-9]{64}$'
 OR NOT EXISTS(SELECT 1 FROM company.artifacts a WHERE a.tenant_id=x.tenant_id AND a.project_id=x.project_id AND a.task_id=x.task_id AND a.attempt_id=x.attempt_id AND a.id=m.id AND a.state='AVAILABLE' AND a.sha256=m.raw_digest AND a.size_bytes=octet_length(m.raw_bytes))
 THEN RAISE EXCEPTION 'R65_PATCH_PROPOSAL_SCOPE'; END IF;
 raw=decode(j->>'artifact_base64','base64');
 IF octet_length(raw)>32768 OR replace(encode(raw,'base64'),chr(10),'') IS DISTINCT FROM j->>'artifact_base64' OR encode(sha256(raw),'hex') IS DISTINCT FROM j->>'artifact_digest' THEN RAISE EXCEPTION 'R65_PATCH_ARTIFACT_DIGEST'; END IF;
 PERFORM company_private.r58_unique_json(convert_from(raw,'UTF8')::json);p=convert_from(raw,'UTF8')::jsonb;
 PERFORM company_private.r58_shape(p,ARRAY['format','path','base_content_digest','replacement_base64']);
 IF p->>'format' IS DISTINCT FROM 'company.replace-file/1' OR p->>'path' IS DISTINCT FROM 'task_title.py'
 OR (p->>'base_content_digest') !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p->'replacement_base64') IS DISTINCT FROM 'string'
 OR length(p->>'replacement_base64')>21848 OR (p->>'replacement_base64') !~ '^[A-Za-z0-9+/]*={0,2}$' THEN RAISE EXCEPTION 'R65_PILOT_PATCH_SHAPE'; END IF;
 replacement=decode(p->>'replacement_base64','base64');
 IF octet_length(replacement)>16384 OR position(decode('00','hex') in replacement)>0 OR replace(encode(replacement,'base64'),chr(10),'') IS DISTINCT FROM p->>'replacement_base64' THEN RAISE EXCEPTION 'R65_BOUNDED_UTF8_PATCH'; END IF;
 PERFORM convert_from(replacement,'UTF8');
 RETURN jsonb_build_object('artifact_id',m.id,'sha256',j->>'artifact_digest','content_base64',j->>'artifact_base64','consume_id',p_consume,'frame_digest',g->>'frame_digest','base_content_digest',p->>'base_content_digest','replacement_content_digest',encode(sha256(replacement),'hex'),'kind','BOUND_PATCH_PROPOSAL_NOT_VERIFICATION');
END $$;
ALTER FUNCTION company_private.r65_patch_artifact_read(uuid,uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r65_patch_artifact_read(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r65_patch_artifact_read(uuid,uuid) TO company_transport_r54,company_execution_functions_r58;
ROLLBACK;
