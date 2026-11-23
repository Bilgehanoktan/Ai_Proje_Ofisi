BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r60_effect_complete(p_consume uuid,p_proof uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;u company_private.r60_tool_consumptions%ROWTYPE;m company_private.r58_attestations%ROWTYPE;c company.commands%ROWTYPE;g jsonb;j jsonb;proposal jsonb;frame jsonb;
BEGIN
 x=company_private.r58_context('tool.effect');g=company_private.r65_effect_guard(p_consume);
 m=company_private.r58_attestation(p_proof,'r60.tool-effect.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['consume_id','frame_digest','process_id','base_head','result_head','effect_digest','outcome','effect']);
 IF m.issuer_id IS DISTINCT FROM x.principal_id OR j->>'consume_id' IS DISTINCT FROM p_consume::text OR j->>'frame_digest' IS DISTINCT FROM g->>'frame_digest' OR j->>'process_id' IS DISTINCT FROM g->>'process_id' OR j->>'base_head' IS DISTINCT FROM g->>'base_head' OR j->>'result_head' !~ '^[a-f0-9]{64}$' OR j->>'effect_digest' !~ '^[a-f0-9]{64}$' OR j->>'outcome' IS DISTINCT FROM 'SUCCEEDED' THEN RAISE EXCEPTION 'R60_EFFECT_PROOF_BINDING'; END IF;
 frame=convert_from(decode(g->>'frame_base64','base64'),'UTF8')::jsonb;
 IF frame->'call'->>'tool_id'='patch.apply' THEN
  proposal=company_private.r65_patch_artifact_read(p_consume,(frame->'call'->>'patch_artifact_id')::uuid);
  PERFORM company_private.r58_shape(j->'effect',ARRAY['kind','base_head','result_head','base_content_digest','result_content_digest','patch_digest']);
  IF j->'effect'->>'kind' IS DISTINCT FROM 'PATCH' OR j->>'effect_digest' IS DISTINCT FROM proposal->>'sha256'
  OR j->'effect'->>'patch_digest' IS DISTINCT FROM proposal->>'sha256'
  OR j->'effect'->>'base_content_digest' IS DISTINCT FROM proposal->>'base_content_digest'
  OR j->'effect'->>'result_content_digest' IS DISTINCT FROM proposal->>'replacement_content_digest'
  OR j->'effect'->>'base_head' IS DISTINCT FROM j->>'base_head' OR j->'effect'->>'result_head' IS DISTINCT FROM j->>'result_head'
  THEN RAISE EXCEPTION 'R65_EFFECT_PATCH_CONTENT_BINDING'; END IF;
 ELSIF frame->'call'->>'tool_id'='workspace.read' THEN
  PERFORM company_private.r58_shape(j->'effect',ARRAY['kind','head_digest','content_base64','content_digest','truncated']);
  IF j->'effect'->>'kind' IS DISTINCT FROM 'READ' OR j->>'base_head' IS DISTINCT FROM j->>'result_head'
  OR j->'effect'->>'head_digest' IS DISTINCT FROM j->>'base_head' OR j->'effect'->>'content_digest' IS DISTINCT FROM j->>'effect_digest'
  OR jsonb_typeof(j->'effect'->'truncated') IS DISTINCT FROM 'boolean'
  OR length(j->'effect'->>'content_base64')>21848 OR (j->'effect'->>'content_base64') !~ '^[A-Za-z0-9+/]*={0,2}$'
  OR octet_length(decode(j->'effect'->>'content_base64','base64'))>(frame->'call'->'arguments'->>'max_bytes')::bigint
  THEN RAISE EXCEPTION 'R65_EFFECT_READ_BINDING'; END IF;
 ELSE RAISE EXCEPTION 'R65_EFFECT_TOOL_UNSUPPORTED'; END IF;
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('consume_id',p_consume,'proof_id',p_proof));
 SELECT * INTO STRICT u FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume;
 UPDATE company_private.r60_tool_consumptions SET state='SUCCEEDED',effect_attestation_id=m.id WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_consume AND state='CONSUMED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_EFFECT_CAS'; END IF;
 UPDATE company_private.r60_engine_streams SET next_sequence=next_sequence+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND engine_session_id=u.engine_session_id AND next_sequence=u.sequence;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_SEQUENCE_CAS'; END IF;
 RETURN company_private.r58_finish(c.id,m.id,jsonb_build_object('consume_id',u.id,'frame_digest',u.frame_digest,'receipt_id',m.id,'status','SUCCEEDED','artifact_ids',jsonb_build_array(m.id)));
END $$;
ALTER FUNCTION company_private.r60_effect_complete(uuid,uuid,text,uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r60_effect_complete(uuid,uuid,text,uuid) FROM PUBLIC;

ROLLBACK;
