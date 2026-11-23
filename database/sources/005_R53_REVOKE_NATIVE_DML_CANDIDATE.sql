BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE ROLE company_revoke_functions_r53 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_revoke_functions_r53;
GRANT EXECUTE ON FUNCTION company_private.r53_allowed(uuid,uuid,text,uuid,boolean) TO company_revoke_functions_r53;
-- Dar SECURITY DEFINER owner yalnız aşağıdaki sabit body'yi taşır.
-- RLS scope helper current session+HUMAN doğrular; full grant yetkisi body girişinde kontrol edilir.
-- Kendi grant'ini revoke etme, final epoch değişiminden sonra self-auth gerektirmez.
CREATE FUNCTION company_private.r53_revoke_scope(p_tenant uuid,p_project uuid) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(SELECT 1 FROM company_private.request_contexts x JOIN company.sessions s ON s.tenant_id=x.tenant_id AND s.id=x.session_id AND s.principal_id=x.principal_id
 JOIN company.principals p ON p.tenant_id=x.tenant_id AND p.id=x.principal_id
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user
 AND x.writer_generation=53 AND x.operation_id='CAP-017.revoke' AND x.tenant_id=p_tenant AND x.project_id=p_project
 AND x.resource_kind='PROJECT' AND p.kind='HUMAN' AND x.principal_kind='HUMAN'
 AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() AND x.expires_at>clock_timestamp());
$$;
ALTER FUNCTION company_private.r53_revoke_scope(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r53_revoke_scope(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r53_revoke_scope(uuid,uuid) TO company_revoke_functions_r53;
GRANT SELECT ON company_private.request_contexts TO company_revoke_functions_r53;
CREATE POLICY r53_revoke_context ON company_private.request_contexts FOR SELECT TO company_revoke_functions_r53 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=53 AND operation_id='CAP-017.revoke');
GRANT SELECT ON company.project_grants,company.commands,company.authority_scope_heads TO company_revoke_functions_r53;
GRANT UPDATE(revoked_at,revision) ON company.project_grants TO company_revoke_functions_r53;
GRANT UPDATE(epoch) ON company.authority_scope_heads TO company_revoke_functions_r53;
GRANT INSERT ON company.commands,company.audit_events,company.outbox TO company_revoke_functions_r53;
GRANT USAGE ON SEQUENCE company.audit_events_id_seq,company.outbox_event_id_seq TO company_revoke_functions_r53;
CREATE POLICY r53_revoke_grant_read ON company.project_grants FOR SELECT TO company_revoke_functions_r53 USING(company_private.r53_revoke_scope(tenant_id,project_id));
CREATE POLICY r53_revoke_grant_write ON company.project_grants FOR UPDATE TO company_revoke_functions_r53 USING(company_private.r53_revoke_scope(tenant_id,project_id)) WITH CHECK(company_private.r53_revoke_scope(tenant_id,project_id));
CREATE POLICY r53_revoke_head_read ON company.authority_scope_heads FOR SELECT TO company_revoke_functions_r53 USING(scope_kind='PROJECT' AND company_private.r53_revoke_scope(tenant_id,project_id));
CREATE POLICY r53_revoke_head_write ON company.authority_scope_heads FOR UPDATE TO company_revoke_functions_r53 USING(scope_kind='PROJECT' AND company_private.r53_revoke_scope(tenant_id,project_id)) WITH CHECK(scope_kind='PROJECT' AND company_private.r53_revoke_scope(tenant_id,project_id));
CREATE POLICY r53_revoke_command_read ON company.commands FOR SELECT TO company_revoke_functions_r53 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND commands.operation='CAP-017.revoke' AND company_private.r53_revoke_scope(x.tenant_id,x.project_id)));
CREATE POLICY r53_revoke_command_insert ON company.commands FOR INSERT TO company_revoke_functions_r53 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=commands.tenant_id AND x.principal_id=commands.principal_id AND commands.operation='CAP-017.revoke' AND company_private.r53_revoke_scope(x.tenant_id,x.project_id)));
CREATE POLICY r53_revoke_audit_insert ON company.audit_events FOR INSERT TO company_revoke_functions_r53 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=audit_events.tenant_id AND x.principal_id=audit_events.actor_id AND company_private.r53_revoke_scope(x.tenant_id,x.project_id)));
CREATE POLICY r53_revoke_outbox_insert ON company.outbox FOR INSERT TO company_revoke_functions_r53 WITH CHECK(kind='GrantRevoked' AND company_private.r53_revoke_scope(tenant_id,project_id));

CREATE FUNCTION company_private.r53_revoke_project_grant(p_request jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; g company.project_grants%ROWTYPE; c company.commands%ROWTYPE;
 q jsonb; ids uuid[]; scope_body jsonb; scope_digest text; payload_digest text; cid uuid; correlation uuid; target uuid; expected bigint; k text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='CAP-017.revoke';
 IF NOT company_private.r53_revoke_scope(x.tenant_id,x.project_id) OR NOT company_private.r53_allowed(x.tenant_id,x.project_id,'cap-017.revoke',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_HUMAN_REVOKER'; END IF;
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
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='CAP-017.revoke' AND idempotency_key=k;
 IF FOUND THEN
  IF c.payload_digest<>payload_digest THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('operation','CAP-017.revoke','status','RECORDED','resource_id',target,'revision',expected+1,'command_receipt_ref',c.id,'result',jsonb_build_object('revocation_receipt_ref',c.id));
 END IF;
 SELECT * INTO STRICT g FROM company.project_grants WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target FOR UPDATE;
 IF g.revision<>expected OR g.revoked_at IS NOT NULL THEN RAISE EXCEPTION 'STALE_GRANT'; END IF;
 WITH RECURSIVE descendants AS (
 SELECT grant_id FROM company.project_grants WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target
 UNION SELECT ch.grant_id FROM company.project_grants ch JOIN descendants p ON ch.parent_grant_id=p.grant_id WHERE ch.tenant_id=x.tenant_id AND ch.project_id=x.project_id
 ) SELECT array_agg(pg.grant_id ORDER BY pg.grant_id),jsonb_agg(jsonb_build_object('grant_id',pg.grant_id,'revision',pg.revision,'task_scope_id',pg.task_scope_id,'permission',pg.permission,'parent_grant_id',pg.parent_grant_id) ORDER BY pg.grant_id)
 INTO ids,scope_body FROM descendants d JOIN company.project_grants pg ON pg.tenant_id=x.tenant_id AND pg.project_id=x.project_id AND pg.grant_id=d.grant_id;
 scope_digest=encode(sha256(convert_to(scope_body::text,'UTF8')),'hex');
 IF scope_digest IS DISTINCT FROM q->>'revocation_scope_digest' THEN RAISE EXCEPTION 'STALE_REVOCATION_SCOPE'; END IF;
 -- Ancestor currentness r53_grant_chain'de her kullanımda zorunlu; descendant kayıtları silinmez.
 UPDATE company.project_grants SET revoked_at=clock_timestamp(),revision=revision+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND grant_id=target AND revision=expected AND revoked_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_GRANT'; END IF;
 cid=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref) VALUES(x.tenant_id,cid,x.principal_id,'CAP-017.revoke',k,payload_digest,correlation,'SUCCEEDED',target);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,correlation,x.principal_id,'GrantRevoked');
 INSERT INTO company.outbox(tenant_id,project_id,aggregate_id,aggregate_revision,kind,payload) VALUES(x.tenant_id,x.project_id,target,expected+1,'GrantRevoked',jsonb_build_object('grant_id',target,'descendant_ids',ids,'command_id',cid,'scope_digest',scope_digest));
 -- Son authority write: eski context bu noktadan sonra geçersiz; self-revoke meşrudur.
 UPDATE company.authority_scope_heads SET epoch=epoch+1 WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND epoch=x.project_epoch;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_AUTHORITY_EPOCH'; END IF;
 RETURN jsonb_build_object('operation','CAP-017.revoke','status','RECORDED','resource_id',target,'revision',expected+1,'command_receipt_ref',cid,'result',jsonb_build_object('revocation_receipt_ref',cid));
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;
ALTER FUNCTION company_private.r53_revoke_project_grant(jsonb) OWNER TO company_revoke_functions_r53;
REVOKE ALL ON FUNCTION company_private.r53_revoke_project_grant(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r53_revoke_project_grant(jsonb) TO company_transport_r53;
ROLLBACK;
