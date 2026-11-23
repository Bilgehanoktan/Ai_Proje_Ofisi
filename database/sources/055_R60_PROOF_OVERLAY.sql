BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r60_store_effect_proof(p_id uuid,p_issuer uuid,p_key_id uuid,p_revision bigint,p_profile text,p_raw bytea,p_tag bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.signer_enrollments%ROWTYPE;k company_private.r58_key_material%ROWTYPE;c company.commands%ROWTYPE;j jsonb;msg bytea;part bytea;d text;
BEGIN
 x=company_private.r58_context('tool.effect');
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=x.principal_id AND kind IN ('WORKER','VERIFIER')) THEN RAISE EXCEPTION 'R58_TECHNICAL_SIGNER_REQUIRED'; END IF;
 IF p_id IS NULL OR p_issuer IS DISTINCT FROM x.principal_id OR p_key_id IS NULL OR p_revision IS NULL OR p_revision<0 OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 65536 OR p_tag IS NULL OR octet_length(p_tag)<>32
 OR p_profile IS DISTINCT FROM 'r60.tool-effect.v1' THEN RAISE EXCEPTION 'R58_ATTESTATION_WIRE'; END IF;
 SELECT * INTO STRICT e FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=p_issuer AND key_id=p_key_id AND enrollment_revision=p_revision AND purpose='TASK_VERIFICATION' FOR SHARE;
 SELECT * INTO STRICT k FROM company_private.r58_key_material WHERE key_id=p_key_id AND purpose='EXECUTION_ATTESTATION' AND NOT revoked FOR SHARE;
 IF e.profile_id IS DISTINCT FROM p_profile OR e.revoked_at IS NOT NULL OR e.compromised_since IS NOT NULL OR e.key_fingerprint IS DISTINCT FROM k.fingerprint
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=e.approved_by AND kind='HUMAN') OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,e.valid_from,e.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'R58_SIGNER_ENROLLMENT'; END IF;
 PERFORM company_private.r58_unique_json(convert_from(p_raw,'UTF8')::json);
 j=convert_from(p_raw,'UTF8')::jsonb;
 PERFORM company_private.r58_shape(j,ARRAY['tenant_id','project_id','receipt_id','profile','binding']);
 IF j->>'tenant_id' IS DISTINCT FROM x.tenant_id::text OR j->>'project_id' IS DISTINCT FROM x.project_id::text OR j->>'receipt_id' IS DISTINCT FROM p_id::text OR j->>'profile' IS DISTINCT FROM p_profile OR jsonb_typeof(j->'binding') IS DISTINCT FROM 'object'
 OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1) THEN RAISE EXCEPTION 'R58_ATTESTATION_SCOPE'; END IF;
 msg=convert_to('R58-EXECUTION-ATTESTATION-v1','UTF8')||decode('00','hex');
 FOREACH part IN ARRAY ARRAY[convert_to(p_issuer::text,'UTF8'),convert_to(p_key_id::text,'UTF8'),convert_to(p_revision::text,'UTF8'),convert_to(p_profile,'UTF8'),p_raw] LOOP msg=msg||convert_to(octet_length(part)::text||':','UTF8')||part; END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(k.secret,msg),p_tag) IS NOT TRUE THEN RAISE EXCEPTION 'R58_INVALID_ATTESTATION_HMAC'; END IF;
 d=encode(sha256(p_raw),'hex');
 INSERT INTO company_private.r58_attestations(tenant_id,project_id,id,issuer_id,key_id,enrollment_revision,profile,raw_digest,raw_bytes,auth_tag,payload) VALUES(x.tenant_id,x.project_id,p_id,p_issuer,p_key_id,p_revision,p_profile,d,p_raw,encode(p_tag,'hex'),j->'binding');
 PERFORM company_private.r58_store_signed_artifact(p_id);
 RETURN jsonb_build_object('receipt_id',p_id,'raw_digest',d,'profile',p_profile);
END $$;
CREATE OR REPLACE FUNCTION company_private.r58_store_signed_artifact(p_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id IN ('evidence.attestation_ingest','tool.effect');
 SELECT * INTO STRICT m FROM company_private.r58_attestations WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_id AND issuer_id=x.principal_id;
 IF x.task_id IS NOT NULL AND x.attempt_id IS NOT NULL THEN
  -- These are real DB-resident signed-statement bytes, not an invented file.
  INSERT INTO company.artifacts(tenant_id,project_id,task_id,attempt_id,id,storage_key,sha256,size_bytes,state)
  VALUES(x.tenant_id,x.project_id,x.task_id,x.attempt_id,m.id,gen_random_uuid(),m.raw_digest,octet_length(m.raw_bytes),'AVAILABLE');
  INSERT INTO company.verifier_receipts(tenant_id,project_id,task_id,attempt_id,id,purpose,signer_id,key_id,receipt_digest,signature) VALUES(x.tenant_id,x.project_id,x.task_id,x.attempt_id,m.id,'TASK_VERIFICATION',m.issuer_id,m.key_id,m.raw_digest,m.auth_tag);
 END IF;
END $$;
CREATE OR REPLACE FUNCTION company_private.r58_attestation_ingest(p_id uuid,p_issuer uuid,p_key_id uuid,p_revision bigint,p_profile text,p_raw bytea,p_tag bytea,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company.signer_enrollments%ROWTYPE;k company_private.r58_key_material%ROWTYPE;c company.commands%ROWTYPE;j jsonb;msg bytea;part bytea;d text;
BEGIN
 x=company_private.r58_context('evidence.attestation_ingest');
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=x.principal_id AND kind IN ('WORKER','VERIFIER')) THEN RAISE EXCEPTION 'R58_TECHNICAL_SIGNER_REQUIRED'; END IF;
 IF p_id IS NULL OR p_issuer IS DISTINCT FROM x.principal_id OR p_key_id IS NULL OR p_revision IS NULL OR p_revision<0 OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 65536 OR p_tag IS NULL OR octet_length(p_tag)<>32
 OR p_profile NOT IN ('r58.workspace.v1','r58.launch-manifest.v1','r58.launch-callback.v1','r58.patch.v1','r58.verification.v1','r58.evidence.v1','r58.quiescence.v1','r60.engine-binding.v1','r60.lease-prepared.v1','r60.lease-active.v1','r60.process-observation.v1','r60.patch-proposal.v1') THEN RAISE EXCEPTION 'R58_ATTESTATION_WIRE'; END IF;
 SELECT * INTO STRICT e FROM company.signer_enrollments WHERE tenant_id=x.tenant_id AND issuer_id=p_issuer AND key_id=p_key_id AND enrollment_revision=p_revision AND purpose='TASK_VERIFICATION' FOR SHARE;
 SELECT * INTO STRICT k FROM company_private.r58_key_material WHERE key_id=p_key_id AND purpose='EXECUTION_ATTESTATION' AND NOT revoked FOR SHARE;
 IF e.profile_id IS DISTINCT FROM p_profile OR e.revoked_at IS NOT NULL OR e.compromised_since IS NOT NULL OR e.key_fingerprint IS DISTINCT FROM k.fingerprint
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=e.approved_by AND kind='HUMAN') OR company_private.r55_cp_time_window_current(x.tenant_id,x.project_id,e.valid_from,e.valid_until) IS NOT TRUE THEN RAISE EXCEPTION 'R58_SIGNER_ENROLLMENT'; END IF;
 PERFORM company_private.r58_unique_json(convert_from(p_raw,'UTF8')::json);
 j=convert_from(p_raw,'UTF8')::jsonb;
 PERFORM company_private.r58_shape(j,ARRAY['tenant_id','project_id','receipt_id','profile','binding']);
 IF j->>'tenant_id' IS DISTINCT FROM x.tenant_id::text OR j->>'project_id' IS DISTINCT FROM x.project_id::text OR j->>'receipt_id' IS DISTINCT FROM p_id::text OR j->>'profile' IS DISTINCT FROM p_profile OR jsonb_typeof(j->'binding') IS DISTINCT FROM 'object'
 OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1) THEN RAISE EXCEPTION 'R58_ATTESTATION_SCOPE'; END IF;
 msg=convert_to('R58-EXECUTION-ATTESTATION-v1','UTF8')||decode('00','hex');
 FOREACH part IN ARRAY ARRAY[convert_to(p_issuer::text,'UTF8'),convert_to(p_key_id::text,'UTF8'),convert_to(p_revision::text,'UTF8'),convert_to(p_profile,'UTF8'),p_raw] LOOP msg=msg||convert_to(octet_length(part)::text||':','UTF8')||part; END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(k.secret,msg),p_tag) IS NOT TRUE THEN RAISE EXCEPTION 'R58_INVALID_ATTESTATION_HMAC'; END IF;
 d=encode(sha256(p_raw),'hex');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('receipt_id',p_id,'issuer',p_issuer,'key',p_key_id,'revision',p_revision,'profile',p_profile,'raw_digest',d));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 INSERT INTO company_private.r58_attestations(tenant_id,project_id,id,issuer_id,key_id,enrollment_revision,profile,raw_digest,raw_bytes,auth_tag,payload) VALUES(x.tenant_id,x.project_id,p_id,p_issuer,p_key_id,p_revision,p_profile,d,p_raw,encode(p_tag,'hex'),j->'binding');
 PERFORM company_private.r58_store_signed_artifact(p_id);
 RETURN company_private.r58_finish(c.id,p_id,jsonb_build_object('receipt_id',p_id,'raw_digest',d,'profile',p_profile));
END $$;
ROLLBACK;
