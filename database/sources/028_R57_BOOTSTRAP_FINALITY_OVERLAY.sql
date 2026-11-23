BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Replacement bodies AFTER r56. No historical DDL repeated.
CREATE OR REPLACE FUNCTION company_private.r56_bootstrap_initial_write(p_nonce uuid,p_correlation uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.bootstrap_request_contexts%ROWTYPE;b company_private.installation_bootstrap_control%ROWTYPE;
 m jsonb;v jsonb;op text;permission_text text;cmd uuid;tl bigint;pl bigint;gd text;bounds jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND context_nonce=p_nonce;
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=x.installation_id FOR UPDATE;
 IF b.state IS DISTINCT FROM 'ARMED' OR b.generation IS DISTINCT FROM x.generation OR p_correlation IS NULL THEN RAISE EXCEPTION 'BOOTSTRAP_NOT_FRESH_ARMED'; END IF;
 m=x.r56_manifest;
 IF jsonb_typeof(m) IS DISTINCT FROM 'object' OR NOT ((m ?& ARRAY['tenant_id','project_id','workspace_id','verified_human_id','nonce_hash','setup_manifest_digest','valid_until','finite_initial_operations','tenant_name','human_name','project_name','initial_principals','evaluation_objective','evaluation_plan','e0_mandate']) IS TRUE) OR EXISTS(SELECT 1 FROM jsonb_object_keys(m) k WHERE k<>ALL(ARRAY['tenant_id','project_id','workspace_id','verified_human_id','nonce_hash','setup_manifest_digest','valid_until','finite_initial_operations','tenant_name','human_name','project_name','initial_principals','evaluation_objective','evaluation_plan','e0_mandate']))
 OR jsonb_typeof((m->'evaluation_objective')) IS DISTINCT FROM 'object' OR NOT (((m->'evaluation_objective') ?& ARRAY['id','goal','constraints','expected_outputs']) IS TRUE) OR EXISTS(SELECT 1 FROM jsonb_object_keys((m->'evaluation_objective')) k WHERE k<>ALL(ARRAY['id','goal','constraints','expected_outputs']))
 OR jsonb_typeof((m->'evaluation_plan')) IS DISTINCT FROM 'object' OR NOT (((m->'evaluation_plan') ?& ARRAY['id','objective_id','assumptions','acceptance_criteria']) IS TRUE) OR EXISTS(SELECT 1 FROM jsonb_object_keys((m->'evaluation_plan')) k WHERE k<>ALL(ARRAY['id','objective_id','assumptions','acceptance_criteria']))
 OR jsonb_typeof((m->'e0_mandate')) IS DISTINCT FROM 'object' OR NOT (((m->'e0_mandate') ?& ARRAY['kind','network','external_effects','workspace_id','plan_id','subject_principal_id','model_digest','fixture_digest','profile_digest','negative_suite_digest','role_id','required_positive_oracle_ids','required_negative_oracle_ids']) IS TRUE) OR EXISTS(SELECT 1 FROM jsonb_object_keys((m->'e0_mandate')) k WHERE k<>ALL(ARRAY['kind','network','external_effects','workspace_id','plan_id','subject_principal_id','model_digest','fixture_digest','profile_digest','negative_suite_digest','role_id','required_positive_oracle_ids','required_negative_oracle_ids']))
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(m->'initial_principals') elem(value) WHERE jsonb_typeof(elem.value) IS DISTINCT FROM 'object' OR NOT ((elem.value ?& ARRAY['id','name','kind']) IS TRUE) OR EXISTS(SELECT 1 FROM jsonb_object_keys(elem.value) k WHERE k<>ALL(ARRAY['id','name','kind']))) THEN RAISE EXCEPTION 'CLOSED_BOOTSTRAP_MANIFEST_REQUIRED'; END IF;
 IF NOT ((m ?& ARRAY['tenant_name','human_name','project_name','initial_principals','evaluation_objective','evaluation_plan','e0_mandate']) IS TRUE)
 OR jsonb_typeof(m->'tenant_name') IS DISTINCT FROM 'string' OR length(m->>'tenant_name') NOT BETWEEN 3 AND 200
 OR jsonb_typeof(m->'human_name') IS DISTINCT FROM 'string' OR length(m->>'human_name') NOT BETWEEN 1 AND 200
 OR jsonb_typeof(m->'project_name') IS DISTINCT FROM 'string' OR length(m->>'project_name') NOT BETWEEN 3 AND 200
 OR jsonb_typeof(m->'initial_principals') IS DISTINCT FROM 'array' OR jsonb_array_length(m->'initial_principals') NOT BETWEEN 1 AND 32
 THEN RAISE EXCEPTION 'INVALID_BOOTSTRAP_INITIAL_SHAPE'; END IF;
 IF EXISTS(SELECT 1 FROM company.tenants WHERE id=b.expected_tenant_id) THEN RAISE EXCEPTION 'PREEXISTING_TENANT_NOT_FRESH_BOOTSTRAP'; END IF;
 bounds=company_private.r56_root_bounds(b.installation_id);
 INSERT INTO company_private.scope_lock_registry(rank,identity_key) VALUES(0,jsonb_build_object('kind','TENANT','tenant_id',b.expected_tenant_id)) RETURNING lock_id INTO tl;
 INSERT INTO company_private.scope_lock_registry(rank,identity_key) VALUES(1,jsonb_build_object('kind','PROJECT','tenant_id',b.expected_tenant_id,'project_id',b.expected_project_id)) RETURNING lock_id INTO pl;
 IF tl<=b.lock_id THEN RAISE EXCEPTION 'BOOTSTRAP_LOCK_ORDER_PREFLIGHT_FAILED'; END IF;
 PERFORM pg_advisory_xact_lock(tl);PERFORM pg_advisory_xact_lock(pl);
 INSERT INTO company.tenants(id,name) VALUES(b.expected_tenant_id,m->>'tenant_name');
 INSERT INTO company.principals(tenant_id,id,name,kind) VALUES(b.expected_tenant_id,b.expected_human_id,m->>'human_name','HUMAN');
 INSERT INTO company.memberships(tenant_id,principal_id,role) VALUES(b.expected_tenant_id,b.expected_human_id,'OPERATOR');
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(m->'initial_principals') z GROUP BY (z->>'id')::uuid HAVING count(*)>1) THEN RAISE EXCEPTION 'DUPLICATE_BOOTSTRAP_PRINCIPAL'; END IF;
 FOR v IN SELECT value FROM jsonb_array_elements(m->'initial_principals') LOOP
  IF NOT ((jsonb_typeof(v)='object' AND v ?& ARRAY['id','name','kind'] AND v->>'kind' IN ('AGENT','WORKER','VERIFIER')
  AND jsonb_typeof(v->'name')='string' AND length(v->>'name') BETWEEN 1 AND 200
  AND (v->>'id')::uuid<>b.expected_human_id) IS TRUE) THEN RAISE EXCEPTION 'SINGLE_HUMAN_ONLY_NO_AGENT_HUMAN_ALIAS'; END IF;
  INSERT INTO company.principals(tenant_id,id,name,kind) VALUES(b.expected_tenant_id,(v->>'id')::uuid,v->>'name',v->>'kind');
 END LOOP;
 INSERT INTO company.workspaces(tenant_id,id,root_ref,trust_class) VALUES(b.expected_tenant_id,b.expected_workspace_id,'bootstrap:'||b.installation_id::text||':'||b.expected_workspace_id::text,'DISPOSABLE_TEST');
 INSERT INTO company.projects(tenant_id,id,workspace_id,name,revision) VALUES(b.expected_tenant_id,b.expected_project_id,b.expected_workspace_id,m->>'project_name',0);
 INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,project_id,epoch,lock_id,revision) VALUES(b.expected_tenant_id,'TENANT',b.expected_tenant_id,NULL,0,tl,0),(b.expected_tenant_id,'PROJECT',b.expected_project_id,b.expected_project_id,0,pl,0);
 FOR op IN SELECT value FROM jsonb_array_elements_text(m->'finite_initial_operations') ORDER BY value LOOP
  SELECT permission INTO STRICT permission_text FROM company_private.operation_permissions WHERE operation_id=op;
  INSERT INTO company.project_grants(tenant_id,project_id,principal_id,permission,base_permission,grant_id,revision,valid_from,valid_until,granted_by)
  VALUES(b.expected_tenant_id,b.expected_project_id,b.expected_human_id,permission_text,permission_text,gen_random_uuid(),0,(bounds->>'utc_lower')::timestamptz,b.expires_at,b.expected_human_id);
 END LOOP;
 -- Exactly one signed, disposable E0 seed; not a general Objective/Plan writer.
 v=m->'evaluation_objective';
 IF NOT ((jsonb_typeof(v)='object' AND v ?& ARRAY['id','goal','constraints','expected_outputs'] AND jsonb_typeof(v->'goal')='string'
 AND length(v->>'goal') BETWEEN 1 AND 2000 AND jsonb_typeof(v->'constraints')='array' AND jsonb_typeof(v->'expected_outputs')='array') IS TRUE)
 THEN RAISE EXCEPTION 'INVALID_SIGNED_E0_OBJECTIVE'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v->'constraints') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(v->'expected_outputs') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string')
 THEN RAISE EXCEPTION 'INVALID_SIGNED_E0_OBJECTIVE_ITEMS'; END IF;
 INSERT INTO company.objectives(tenant_id,project_id,id,goal,constraints,expected_outputs,created_by) VALUES(b.expected_tenant_id,b.expected_project_id,(v->>'id')::uuid,v->>'goal',v->'constraints',v->'expected_outputs',b.expected_human_id);
 v=m->'evaluation_plan';
 IF NOT ((jsonb_typeof(v)='object' AND v ?& ARRAY['id','objective_id','assumptions','acceptance_criteria']
 AND v->>'objective_id'=m#>>'{evaluation_objective,id}' AND v->>'id'=m#>>'{e0_mandate,plan_id}'
 AND jsonb_typeof(v->'assumptions')='array' AND jsonb_typeof(v->'acceptance_criteria')='array' AND jsonb_array_length(v->'acceptance_criteria')>0) IS TRUE)
 THEN RAISE EXCEPTION 'INVALID_SIGNED_E0_PLAN'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v->'assumptions') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(v->'acceptance_criteria') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string')
 THEN RAISE EXCEPTION 'INVALID_SIGNED_E0_PLAN_ITEMS'; END IF;
 INSERT INTO company.plans(tenant_id,project_id,id,objective_id,revision,assumptions,acceptance_criteria) VALUES(b.expected_tenant_id,b.expected_project_id,(v->>'id')::uuid,(v->>'objective_id')::uuid,0,v->'assumptions',v->'acceptance_criteria');
 v=m->'e0_mandate';
 IF NOT ((jsonb_typeof(v)='object' AND v->>'kind'='EVALUATION_ONLY' AND v->>'network'='DENY' AND v->>'external_effects'='DENY'
 AND v->>'workspace_id'=b.expected_workspace_id::text AND v->>'model_digest' ~ '^[a-f0-9]{64}$'
 AND v->>'fixture_digest' ~ '^[a-f0-9]{64}$' AND v->>'profile_digest' ~ '^[a-f0-9]{64}$'
 AND v->>'negative_suite_digest' ~ '^[a-f0-9]{64}$' AND jsonb_typeof(v->'role_id')='string' AND length(v->>'role_id')>0
 AND jsonb_typeof(v->'required_positive_oracle_ids')='array' AND jsonb_array_length(v->'required_positive_oracle_ids')>0
 AND jsonb_typeof(v->'required_negative_oracle_ids')='array' AND jsonb_array_length(v->'required_negative_oracle_ids')>0) IS TRUE)
 OR NOT EXISTS(SELECT 1 FROM company.principals p WHERE p.tenant_id=b.expected_tenant_id AND p.id=(v->>'subject_principal_id')::uuid AND p.kind IN ('WORKER','VERIFIER'))
 THEN RAISE EXCEPTION 'INVALID_E0_ONLY_MANDATE_OR_SUBJECT'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements((v->'required_positive_oracle_ids')||(v->'required_negative_oracle_ids')) z
 WHERE jsonb_typeof(z) IS DISTINCT FROM 'string') THEN RAISE EXCEPTION 'INVALID_E0_ORACLE_ID_TYPE'; END IF;
 SELECT encode(sha256(convert_to(jsonb_agg(jsonb_build_array(g.grant_id,g.permission,g.valid_from,g.valid_until) ORDER BY g.grant_id)::text,'UTF8')),'hex') INTO gd FROM company.project_grants g WHERE g.tenant_id=b.expected_tenant_id AND g.project_id=b.expected_project_id;
 cmd=gen_random_uuid();
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(b.expected_tenant_id,cmd,b.expected_human_id,'trusted_setup.consume','setup:'||b.installation_id::text||':'||b.generation::text,b.payload_digest,p_correlation,'RUNNING',NULL);
 INSERT INTO company.project_event_heads(tenant_id,project_id,writer_generation,committed_sequence,migration_manifest_digest) VALUES(b.expected_tenant_id,b.expected_project_id,54,0,b.setup_manifest_digest);
 UPDATE company_private.bootstrap_request_contexts SET r56_command_id=cmd,r56_grants_digest=gd WHERE backend_pid=x.backend_pid AND transaction_id=x.transaction_id AND context_nonce=p_nonce;
 RETURN cmd;
END $$;

CREATE OR REPLACE FUNCTION company_private.r56_bootstrap_finish(p_nonce uuid,p_command uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.bootstrap_request_contexts%ROWTYPE;b company_private.installation_bootstrap_control%ROWTYPE;c company.commands%ROWTYPE;
 proof jsonb;result jsonb;payload jsonb;d text;event_d text;aid bigint;n bigint;
BEGIN
 SELECT * INTO STRICT x FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND context_nonce=p_nonce;
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=x.installation_id FOR UPDATE;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=b.expected_tenant_id AND id=p_command FOR UPDATE;
 SELECT committed_sequence INTO STRICT n FROM company.project_event_heads WHERE tenant_id=b.expected_tenant_id AND project_id=b.expected_project_id AND writer_generation=54 FOR UPDATE;
 IF b.state IS DISTINCT FROM 'ARMED' OR c.operation IS DISTINCT FROM 'trusted_setup.consume' OR c.state IS DISTINCT FROM 'RUNNING'
 OR c.principal_id IS DISTINCT FROM b.expected_human_id OR c.payload_digest IS DISTINCT FROM b.payload_digest
 OR x.r56_command_id IS DISTINCT FROM c.id OR x.r56_grants_digest IS NULL OR n<>0 THEN RAISE EXCEPTION 'BOOTSTRAP_FINALIZER_BINDING_MISMATCH'; END IF;
 PERFORM company_private.r56_bootstrap_final_proof(p_nonce,'AFTER_DOMAIN_LOCKS');
 -- Logical final authorization cut precedes immutable result sealing.
 -- Held authority locks serialize revoke until the transaction ends.
 proof=company_private.r56_bootstrap_final_proof(p_nonce,'COMMIT_CUT');
 result=jsonb_build_object('installation_id',b.installation_id,'generation',b.generation,'tenant_id',b.expected_tenant_id,'project_id',b.expected_project_id,
 'workspace_id',b.expected_workspace_id,'accepted_human_id',b.expected_human_id,'grants_digest',x.r56_grants_digest,'human_count',1,
 'source_revision','r56','e0_started',false,'ordinary_worker_authorized',false,'final_proof',proof);
 d=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,b.installation_id,result)::text,'UTF8')),'hex');
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(b.expected_tenant_id,c.correlation_id,b.expected_human_id,'InstallationBootstrapped') RETURNING id INTO aid;
 payload=jsonb_build_object('command_id',c.id,'request_digest',c.payload_digest,'result_digest',d,'installation_id',b.installation_id,'source_revision','r56');
 event_d=encode(sha256(convert_to(jsonb_build_array(b.expected_project_id,0,'InstallationBootstrapped',payload)::text,'UTF8')),'hex');
 INSERT INTO company.outbox(tenant_id,project_id,aggregate_id,aggregate_revision,kind,payload,project_sequence,event_writer_generation,event_instance_id,event_digest)
 VALUES(b.expected_tenant_id,b.expected_project_id,b.expected_project_id,0,'InstallationBootstrapped',payload,1,54,c.id,event_d);
 UPDATE company.project_event_heads SET committed_sequence=1 WHERE tenant_id=b.expected_tenant_id AND project_id=b.expected_project_id AND committed_sequence=0 AND writer_generation=54;
 IF NOT FOUND THEN RAISE EXCEPTION 'BOOTSTRAP_EVENT_HEAD_CONFLICT'; END IF;
 UPDATE company.commands SET state='SUCCEEDED',result_ref=b.installation_id,r55_project_id=b.expected_project_id,r55_result_payload=result,
 r55_result_digest=d,r55_event_sequence=1,r55_audit_id=aid,r55_source_revision='r56' WHERE tenant_id=c.tenant_id AND id=c.id AND state='RUNNING';
 IF NOT FOUND THEN RAISE EXCEPTION 'BOOTSTRAP_COMMAND_CONFLICT'; END IF;
 INSERT INTO company_private.bootstrap_receipts(installation_id,generation,tenant_id,project_id,command_id,payload_digest,setup_manifest_digest,initial_grants_digest,accepted_human_id,
 e0_mandate,e0_valid_until,r56_final_proof,r56_result_digest)
 VALUES(b.installation_id,b.generation,b.expected_tenant_id,b.expected_project_id,c.id,b.payload_digest,b.setup_manifest_digest,x.r56_grants_digest,b.expected_human_id,
 x.r56_manifest->'e0_mandate',b.expires_at,proof,d);
 UPDATE company_private.installation_bootstrap_control SET state='CONSUMED',consumed_command_id=c.id WHERE installation_id=b.installation_id AND generation=b.generation AND state='ARMED';
 IF NOT FOUND THEN RAISE EXCEPTION 'BOOTSTRAP_CONSUME_CAS_CONFLICT'; END IF;
 -- Post-seal freshness is an additional abort check, never a discarded final proof.
 PERFORM company_private.r56_root_bounds(b.installation_id);
 RETURN jsonb_build_object('command_id',c.id,'state','SUCCEEDED','result_ref',b.installation_id,'receipt_digest',d,'spawned',false);
END $$;

CREATE OR REPLACE FUNCTION company_private.r56_bootstrap_invariant() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE c company.commands%ROWTYPE;b company_private.bootstrap_receipts%ROWTYPE;
BEGIN
 IF NEW.operation IS DISTINCT FROM 'trusted_setup.consume' OR NEW.r55_source_revision IS DISTINCT FROM 'r56' THEN RETURN NULL; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=NEW.tenant_id AND id=NEW.id;
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE command_id=c.id AND tenant_id=c.tenant_id;
 IF c.state IS DISTINCT FROM 'SUCCEEDED' OR b.r56_result_digest IS DISTINCT FROM c.r55_result_digest
 OR b.r56_final_proof->>'phase' IS DISTINCT FROM 'COMMIT_CUT'
 OR b.r56_final_proof IS DISTINCT FROM c.r55_result_payload->'final_proof'
 OR b.r56_final_proof->>'installation_id' IS DISTINCT FROM b.installation_id::text
 OR b.r56_final_proof->>'generation' IS DISTINCT FROM b.generation::text
 OR b.r56_final_proof->>'manifest_digest' IS DISTINCT FROM b.payload_digest
 OR b.r56_result_digest IS DISTINCT FROM encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,b.installation_id,c.r55_result_payload)::text,'UTF8')),'hex')
 OR b.accepted_human_id IS DISTINCT FROM c.principal_id OR b.payload_digest IS DISTINCT FROM c.payload_digest
 OR NOT EXISTS(SELECT 1 FROM company_private.installation_bootstrap_control z WHERE z.installation_id=b.installation_id AND z.generation=b.generation AND z.state='CONSUMED' AND z.consumed_command_id=c.id)
 OR NOT EXISTS(SELECT 1 FROM company.audit_events a WHERE a.id=c.r55_audit_id AND a.tenant_id=c.tenant_id AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id AND a.kind='InstallationBootstrapped')
 OR NOT EXISTS(SELECT 1 FROM company.outbox e WHERE e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.project_sequence=1 AND e.event_instance_id=c.id AND e.event_writer_generation=54 AND e.payload->>'result_digest'=c.r55_result_digest AND e.kind='InstallationBootstrapped' AND e.aggregate_id=b.project_id AND e.aggregate_revision=0 AND e.payload->>'request_digest'=c.payload_digest AND e.event_digest=encode(sha256(convert_to(jsonb_build_array(e.aggregate_id,e.aggregate_revision,e.kind,e.payload)::text,'UTF8')),'hex'))
 THEN RAISE EXCEPTION 'BOOTSTRAP_ATOMIC_WITNESS_MISSING'; END IF;
 PERFORM company_private.r56_root_bounds(b.installation_id);
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION company_private.r56_bootstrap_consume(p_installation uuid,p_generation bigint,p_nonce bytea,p_raw bytea,p_tag bytea,p_key bytea,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n uuid;cmd uuid;result jsonb;b company_private.bootstrap_receipts%ROWTYPE;ctl company_private.installation_bootstrap_control%ROWTYPE;
BEGIN
 IF p_correlation IS NULL THEN RAISE EXCEPTION 'BOOTSTRAP_CORRELATION_REQUIRED'; END IF;
 n=company_private.r56_bootstrap_enter(p_installation,p_generation,p_nonce,p_raw,p_tag,p_key);
 SELECT * INTO STRICT ctl FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation;
 IF ctl.state='CONSUMED' THEN
  SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=p_installation AND generation=p_generation AND payload_digest=ctl.payload_digest AND accepted_human_id=ctl.expected_human_id;
  IF b.r56_result_digest IS NULL OR b.r56_final_proof IS NULL
 OR b.r56_final_proof->>'phase' IS DISTINCT FROM 'COMMIT_CUT' OR NOT EXISTS(
   SELECT 1 FROM company.commands c JOIN company.audit_events a ON a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id
   JOIN company.outbox e ON e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.event_instance_id=c.id
   WHERE c.tenant_id=b.tenant_id AND c.id=b.command_id AND c.principal_id=b.accepted_human_id
   AND c.state='SUCCEEDED' AND c.result_ref=b.installation_id AND c.payload_digest=b.payload_digest
   AND c.r55_source_revision='r56' AND c.r55_result_digest=b.r56_result_digest
   AND c.r55_result_payload->'final_proof'=b.r56_final_proof
   AND b.r56_final_proof->>'installation_id'=b.installation_id::text
   AND b.r56_final_proof->>'generation'=b.generation::text
   AND b.r56_final_proof->>'manifest_digest'=b.payload_digest
   AND c.r55_result_digest=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,b.installation_id,c.r55_result_payload)::text,'UTF8')),'hex')
   AND a.kind='InstallationBootstrapped' AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id
   AND e.kind='InstallationBootstrapped' AND e.project_sequence=1 AND e.event_writer_generation=54
   AND e.payload->>'result_digest'=c.r55_result_digest AND e.aggregate_id=b.project_id AND e.aggregate_revision=0 AND e.payload->>'request_digest'=c.payload_digest AND e.event_digest=encode(sha256(convert_to(jsonb_build_array(e.aggregate_id,e.aggregate_revision,e.kind,e.payload)::text,'UTF8')),'hex'))
  THEN RAISE EXCEPTION 'BOOTSTRAP_REPLAY_WITNESS_MISSING_OR_LEGACY'; END IF;
  PERFORM company_private.r56_bootstrap_final_proof(n,'REPLAY_READ');
  result=jsonb_build_object('command_id',b.command_id,'state','SUCCEEDED','result_ref',b.installation_id,'receipt_digest',b.r56_result_digest,'outcome','REPLAY_NO_NEW_GRANT');
 ELSE
  cmd=company_private.r56_bootstrap_initial_write(n,p_correlation);
  result=company_private.r56_bootstrap_finish(n,cmd);
 END IF;
 -- Deferred witnesses must execute while the protected setup context exists.
 SET CONSTRAINTS company.r56_bootstrap_invariant IMMEDIATE;
 DELETE FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND context_nonce=n;
 IF NOT FOUND THEN RAISE EXCEPTION 'BOOTSTRAP_EXIT_CONTEXT_LOST'; END IF;
 RETURN result;
END $$;
ROLLBACK;
