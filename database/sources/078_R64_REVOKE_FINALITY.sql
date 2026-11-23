BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r53_revoke_project_grant(p_request jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; g company.project_grants%ROWTYPE; c company.commands%ROWTYPE;
 q jsonb; ids uuid[]; scope_body jsonb; scope_digest text; payload_digest text; cid uuid; correlation uuid; target uuid; expected bigint; k text; sealed jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='CAP-017.revoke';
 IF NOT company_private.r53_revoke_scope(x.tenant_id,x.project_id) OR NOT company_private.r54_allowed(x.tenant_id,x.project_id,'cap-017.revoke',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_HUMAN_REVOKER'; END IF;
 IF p_request IS NULL OR jsonb_typeof(p_request)<>'object' OR NOT(p_request ?& ARRAY['schema_version','operation','correlation_id','tenant_id','project_id','resource_id','payload','expected_revision','idempotency_key']) OR (SELECT count(*) FROM jsonb_object_keys(p_request))<>9 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF p_request->>'schema_version' IS DISTINCT FROM 'PK04-r1' OR p_request->>'operation' IS DISTINCT FROM 'CAP-017.revoke' OR jsonb_typeof(p_request->'payload')<>'object' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 q=p_request->'payload';
 IF NOT(q ?& ARRAY['grant_id','grant_revision','reason_code','revocation_scope_digest']) OR (SELECT count(*) FROM jsonb_object_keys(q))<>4 OR q->>'reason_code' NOT IN ('OWNER_REQUEST','POLICY_CHANGED','INCIDENT') OR q->>'revocation_scope_digest' !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF jsonb_typeof(p_request->'schema_version') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'operation') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'correlation_id') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'tenant_id') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'project_id') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'resource_id') IS DISTINCT FROM 'string' OR jsonb_typeof(p_request->'expected_revision') IS DISTINCT FROM 'number' OR jsonb_typeof(p_request->'idempotency_key') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF jsonb_typeof(q->'grant_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'grant_revision') IS DISTINCT FROM 'number' OR jsonb_typeof(q->'reason_code') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'revocation_scope_digest') IS DISTINCT FROM 'string' OR q->>'grant_revision' !~ '^[0-9]+$' OR p_request->>'expected_revision' !~ '^[0-9]+$' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 target=(q->>'grant_id')::uuid; expected=(q->>'grant_revision')::bigint; correlation=(p_request->>'correlation_id')::uuid; k=p_request->>'idempotency_key';
 IF (p_request->>'tenant_id')::uuid IS DISTINCT FROM x.tenant_id OR (p_request->>'project_id')::uuid IS DISTINCT FROM x.project_id OR (p_request->>'resource_id')::uuid IS DISTINCT FROM target OR (p_request->>'expected_revision')::bigint IS DISTINCT FROM expected THEN RAISE EXCEPTION 'INVALID_SCOPE_OR_REVISION'; END IF;
 IF expected<0 OR expected>9007199254740991 OR length(k) NOT BETWEEN 16 AND 128 OR k !~ '^[A-Za-z0-9_.:-]+$' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 payload_digest=encode(sha256(convert_to((p_request-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 c=company_private.r64_begin_digest(k,correlation,payload_digest);
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 cid=c.id;
 SELECT * INTO STRICT g FROM company.project_grants WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target FOR UPDATE;
 IF g.revision<>expected OR g.revoked_at IS NOT NULL THEN RAISE EXCEPTION 'STALE_GRANT'; END IF;
 WITH RECURSIVE descendants AS (
 SELECT grant_id FROM company.project_grants WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target
 UNION SELECT ch.grant_id FROM company.project_grants ch JOIN descendants p ON ch.parent_grant_id=p.grant_id WHERE ch.tenant_id=x.tenant_id AND ch.project_id=x.project_id
 ) SELECT array_agg(pg.grant_id ORDER BY pg.grant_id),jsonb_agg(jsonb_build_object('grant_id',pg.grant_id,'revision',pg.revision,'task_scope_id',pg.task_scope_id,'permission',pg.permission,'parent_grant_id',pg.parent_grant_id) ORDER BY pg.grant_id)
 INTO ids,scope_body FROM descendants d JOIN company.project_grants pg ON pg.tenant_id=x.tenant_id AND pg.project_id=x.project_id AND pg.grant_id=d.grant_id;
 scope_digest=encode(sha256(convert_to(scope_body::text,'UTF8')),'hex');
 IF scope_digest IS DISTINCT FROM q->>'revocation_scope_digest' THEN RAISE EXCEPTION 'STALE_REVOCATION_SCOPE'; END IF;
 -- Seal while the current authority is still valid. Both the seal and the
 -- authority cut are in this same transaction; any failed CAS rolls all back.
 sealed=company_private.r60_finish_revision(cid,target,expected+1,
  jsonb_build_object('operation','CAP-017.revoke','status','RECORDED','resource_id',target,
   'revision',expected+1,'command_receipt_ref',cid,'descendant_ids',ids,'scope_digest',scope_digest,
   'result',jsonb_build_object('revocation_receipt_ref',cid)));
 -- The fixed NOLOGIN revoke owner has only revoked_at/revision and epoch UPDATE.
 -- Its existing r53_revoke_scope RLS requires this transaction's actual HUMAN
 -- PROJECT context and live session; it deliberately permits the self-cut.
 UPDATE company.project_grants SET revoked_at=clock_timestamp(),revision=revision+1
 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target AND revision=expected AND revoked_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_GRANT'; END IF;
 UPDATE company.authority_scope_heads SET epoch=epoch+1
 WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND epoch=x.project_epoch;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_AUTHORITY_EPOCH'; END IF;
 -- This result is private to the host. After COMMIT, emit must enter a fresh
 -- context and validate the pre-cut snapshot; old authority cannot emit it.
 RETURN sealed;
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;
ALTER FUNCTION company_private.r53_revoke_project_grant(jsonb) OWNER TO company_revoke_functions_r53;
REVOKE ALL ON FUNCTION company_private.r53_revoke_project_grant(jsonb) FROM PUBLIC;

ROLLBACK;
