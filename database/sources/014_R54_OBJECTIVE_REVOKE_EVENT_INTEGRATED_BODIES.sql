BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r53_objectives_create(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; c company.commands%ROWTYPE; v_project uuid; v_correlation uuid;
 v_key text; v_digest text; v_id uuid; v_command uuid; v_revision bigint; element jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND operation_id='objectives.create';
 IF p_request IS NULL OR jsonb_typeof(p_request)<>'object' OR NOT (p_request ?& ARRAY['idempotency_key','correlation_id','project_id','goal','constraints','expected_outputs'])
 OR (SELECT count(*) FROM jsonb_object_keys(p_request))<>6 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 IF jsonb_typeof(p_request->'idempotency_key')<>'string' OR jsonb_typeof(p_request->'correlation_id')<>'string' OR jsonb_typeof(p_request->'project_id')<>'string'
 OR jsonb_typeof(p_request->'goal')<>'string' OR jsonb_typeof(p_request->'constraints')<>'array' OR jsonb_typeof(p_request->'expected_outputs')<>'array' THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 v_project=(p_request->>'project_id')::uuid; v_correlation=(p_request->>'correlation_id')::uuid; v_key=p_request->>'idempotency_key';
 IF v_project IS DISTINCT FROM x.project_id OR x.resource_kind<>'PROJECT' OR NOT company_private.r54_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_CURRENT_AUTHORITY'; END IF;
 IF length(v_key) NOT BETWEEN 16 AND 128 OR v_key !~ '^[A-Za-z0-9_.:-]+$' OR length(p_request->>'goal') NOT BETWEEN 10 AND 4000
 OR jsonb_array_length(p_request->'constraints') NOT BETWEEN 1 AND 20 OR jsonb_array_length(p_request->'expected_outputs') NOT BETWEEN 1 AND 10 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 FOR element IN SELECT value FROM jsonb_array_elements((p_request->'constraints')||(p_request->'expected_outputs')) LOOP
  IF jsonb_typeof(element)<>'string' OR length(element#>>'{}') NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING'; END IF;
 END LOOP;
 -- Server-owned profile PG_JSONB_TEXT_UTF8_R53; JCS veya caller digest iddiası yok.
 -- correlation_id semantik payload dışıdır: replay ilk correlation id'yi döndürür.
 v_digest=encode(sha256(convert_to((p_request-'correlation_id'-'idempotency_key')::text,'UTF8')),'hex');
 -- Project authority advisory lock context enter'da alınmıştır; row lock bundan sonra.
 SELECT revision INTO STRICT v_revision FROM company.projects WHERE tenant_id=x.tenant_id AND id=v_project FOR UPDATE;
 SELECT * INTO c FROM company.commands WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation='objectives.create' AND idempotency_key=v_key;
 IF FOUND THEN
  IF c.payload_digest<>v_digest THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST'; END IF;
  RETURN jsonb_build_object('command_id',c.id,'correlation_id',c.correlation_id,'state',c.state,'result_ref',c.result_ref);
 END IF;
 v_id=gen_random_uuid(); v_command=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,v_command,x.principal_id,'objectives.create',v_key,v_digest,v_correlation,'RUNNING',NULL);
 INSERT INTO company.objectives(tenant_id,project_id,id,goal,constraints,expected_outputs,created_by)
 VALUES(x.tenant_id,v_project,v_id,p_request->>'goal',p_request->'constraints',p_request->'expected_outputs',x.principal_id);
 UPDATE company.projects SET revision=revision+1 WHERE tenant_id=x.tenant_id AND id=v_project AND revision=v_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_PROJECT'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(x.tenant_id,v_correlation,x.principal_id,'ObjectiveCreated');
 PERFORM company_private.r54_emit_event(x.tenant_id,v_project,v_id,v_revision+1,'ObjectiveCreated',jsonb_build_object('objective_id',v_id,'command_id',v_command,'project_revision',v_revision+1));
 UPDATE company.commands SET state='SUCCEEDED',result_ref=v_id WHERE tenant_id=x.tenant_id AND id=v_command;
 IF NOT company_private.r54_allowed(x.tenant_id,v_project,'objectives.create',NULL,true) THEN RAISE EXCEPTION 'DENIED_COMMIT_CUT'; END IF;
 RETURN jsonb_build_object('command_id',v_command,'correlation_id',v_correlation,'state','SUCCEEDED','result_ref',v_id);
EXCEPTION WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
WHEN INVALID_TEXT_REPRESENTATION THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
END $$;
ALTER FUNCTION company_private.r53_objectives_create(jsonb) OWNER TO company_first_run_functions_r53;
REVOKE ALL ON FUNCTION company_private.r53_objectives_create(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r53_objectives_create(jsonb) TO company_transport_r54;
CREATE OR REPLACE FUNCTION company_private.r53_revoke_project_grant(p_request jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE; g company.project_grants%ROWTYPE; c company.commands%ROWTYPE;
 q jsonb; ids uuid[]; scope_body jsonb; scope_digest text; payload_digest text; cid uuid; correlation uuid; target uuid; expected bigint; k text;
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
 PERFORM company_private.r54_emit_event(x.tenant_id,x.project_id,target,expected+1,'GrantRevoked',jsonb_build_object('grant_id',target,'descendant_ids',ids,'command_id',cid,'scope_digest',scope_digest));
 -- Son authority write: eski context bu noktadan sonra geçersiz; self-revoke meşrudur.
 UPDATE company.authority_scope_heads SET epoch=epoch+1 WHERE tenant_id=x.tenant_id AND scope_kind='PROJECT' AND scope_ref=x.project_id AND epoch=x.project_epoch;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_AUTHORITY_EPOCH'; END IF;
 RETURN jsonb_build_object('operation','CAP-017.revoke','status','RECORDED','resource_id',target,'revision',expected+1,'command_receipt_ref',cid,'result',jsonb_build_object('revocation_receipt_ref',cid));
EXCEPTION WHEN INVALID_TEXT_REPRESENTATION OR NUMERIC_VALUE_OUT_OF_RANGE THEN RAISE EXCEPTION 'INVALID_TYPED_BINDING';
 WHEN UNIQUE_VIOLATION THEN RAISE EXCEPTION 'CONFLICT_IDEMPOTENCY_DIGEST';
END $$;
ALTER FUNCTION company_private.r53_revoke_project_grant(jsonb) OWNER TO company_revoke_functions_r53;
REVOKE ALL ON FUNCTION company_private.r53_revoke_project_grant(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r53_revoke_project_grant(jsonb) TO company_transport_r54;
ROLLBACK;
