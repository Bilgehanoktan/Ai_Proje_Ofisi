-- Inert r56 FIRST BOOTSTRAP source overlay; not an authorized migration.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
DO $preflight$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname IN ('company','company_private') AND (coalesce(pg_get_expr(p.polqual,p.polrelid),'') LIKE '%app.tenant_id%'
 OR coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'') LIKE '%app.tenant_id%'))
 THEN RAISE EXCEPTION 'LEGACY_GUC_POLICY_NOT_FENCED'; END IF;
END $preflight$;

CREATE ROLE company_bootstrap_functions_r56 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE ROLE company_bootstrap_transport_r56 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_bootstrap_functions_r56;
GRANT USAGE ON SCHEMA company_private TO company_bootstrap_transport_r56;
-- No member/login/key/enrollment row is created. Physical enrollment is separate.
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_anchor_boottime_ns numeric(20,0);
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_anchor_utc_lower timestamptz;
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_anchor_utc_upper timestamptz;
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_issuer_class text;
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_approved_manifest_digest text;
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_approved_nonce_hash text;
ALTER TABLE company_private.r55_setup_root_enrollments ADD COLUMN r56_human_consent_evidence_digest text;
ALTER TABLE company_private.r55_setup_root_enrollments ADD CONSTRAINT r56_root_anchor_shape CHECK(
 (r56_anchor_boottime_ns IS NULL AND r56_anchor_utc_lower IS NULL AND r56_anchor_utc_upper IS NULL AND r56_issuer_class IS NULL)
 OR ((r56_anchor_boottime_ns>=0 AND r56_anchor_boottime_ns IS NOT NULL
 AND r56_anchor_utc_lower IS NOT NULL AND r56_anchor_utc_upper IS NOT NULL
 AND isfinite(r56_anchor_utc_lower) AND isfinite(r56_anchor_utc_upper)
 AND r56_anchor_utc_lower<=r56_anchor_utc_upper AND r56_issuer_class='PROVISIONING_SERVICE') IS TRUE));
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r56_manifest jsonb;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r56_command_id uuid;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r56_final_proof jsonb;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r56_grants_digest text;
ALTER TABLE company_private.bootstrap_receipts ADD COLUMN r56_final_proof jsonb;
ALTER TABLE company_private.bootstrap_receipts ADD COLUMN r56_result_digest text;
ALTER TABLE company.commands DROP CONSTRAINT r55_command_finality_shape;
ALTER TABLE company.commands ADD CONSTRAINT r56_command_finality_shape CHECK(
 (r55_project_id IS NULL AND r55_result_payload IS NULL AND r55_result_digest IS NULL AND r55_event_sequence IS NULL AND r55_audit_id IS NULL AND r55_source_revision IS NULL)
 OR ((state='SUCCEEDED' AND r55_project_id IS NOT NULL AND jsonb_typeof(r55_result_payload)='object'
 AND r55_result_digest ~ '^[a-f0-9]{64}$' AND r55_event_sequence>0 AND r55_audit_id IS NOT NULL
 AND r55_source_revision IN ('r55-cp1','r56')) IS TRUE));

GRANT SELECT ON company_private.r55_setup_root_enrollments,company_private.installation_bootstrap_control,
 company_private.bootstrap_request_contexts,company_private.bootstrap_receipts,
 company_private.scope_lock_registry,company_private.operation_permissions TO company_bootstrap_functions_r56;
GRANT UPDATE(revoked_at) ON company_private.r55_setup_root_enrollments TO company_bootstrap_functions_r56;
GRANT INSERT,UPDATE,DELETE ON company_private.bootstrap_request_contexts TO company_bootstrap_functions_r56;
GRANT UPDATE(state,consumed_command_id) ON company_private.installation_bootstrap_control TO company_bootstrap_functions_r56;
GRANT INSERT ON company_private.bootstrap_receipts,company_private.scope_lock_registry TO company_bootstrap_functions_r56;
GRANT UPDATE(policy_revision) ON company_private.operation_permissions TO company_bootstrap_functions_r56;
GRANT SELECT,INSERT ON company.tenants,company.principals,company.memberships,company.workspaces,
 company.projects,company.objectives,company.plans,company.authority_scope_heads,company.project_grants,
 company.commands,company.audit_events,company.outbox,company.project_event_heads TO company_bootstrap_functions_r56;
GRANT UPDATE ON company.commands,company.project_event_heads TO company_bootstrap_functions_r56;
GRANT USAGE ON SEQUENCE company_private.scope_lock_registry_lock_id_seq,company.audit_events_id_seq,
 company.outbox_event_id_seq TO company_bootstrap_functions_r56;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_hmac_sha256(bytea,bytea),
 company_private.r55_cp_tag_equal(bytea,bytea),company_private.r55_cp_clock_observe_local()
 TO company_bootstrap_functions_r56;
CREATE POLICY r56_root_read ON company_private.r55_setup_root_enrollments FOR SELECT TO company_bootstrap_functions_r56 USING(true);
CREATE POLICY r56_root_lock ON company_private.r55_setup_root_enrollments FOR UPDATE TO company_bootstrap_functions_r56 USING(true) WITH CHECK(false);
CREATE POLICY r56_control_read ON company_private.installation_bootstrap_control FOR SELECT TO company_bootstrap_functions_r56 USING(true);
CREATE POLICY r56_control_update ON company_private.installation_bootstrap_control FOR UPDATE TO company_bootstrap_functions_r56 USING(true) WITH CHECK(state='CONSUMED');
CREATE POLICY r56_boot_context ON company_private.bootstrap_request_contexts TO company_bootstrap_functions_r56
 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user)
 WITH CHECK(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user);
CREATE POLICY r56_receipt_read ON company_private.bootstrap_receipts FOR SELECT TO company_bootstrap_functions_r56 USING(true);
CREATE POLICY r56_locks ON company_private.scope_lock_registry TO company_bootstrap_functions_r56 USING(true) WITH CHECK(true);
CREATE POLICY r56_registry_read ON company_private.operation_permissions FOR SELECT TO company_bootstrap_functions_r56 USING(true);
CREATE POLICY r56_registry_lock ON company_private.operation_permissions FOR UPDATE TO company_bootstrap_functions_r56 USING(true) WITH CHECK(false);

CREATE FUNCTION company_private.r56_root_bounds(p_installation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e company_private.r55_setup_root_enrollments%ROWTYPE;b company_private.installation_bootstrap_control%ROWTYPE;
 o jsonb;bt0 numeric;bt1 numeric;age numeric;drift numeric;lo timestamptz;hi timestamptz;wall timestamptz;
BEGIN
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation;
 SELECT * INTO STRICT e FROM company_private.r55_setup_root_enrollments WHERE installation_id=p_installation AND generation=b.generation FOR SHARE;
 IF e.revoked_at IS NOT NULL OR e.compromised_at IS NOT NULL OR e.r56_issuer_class IS DISTINCT FROM 'PROVISIONING_SERVICE'
 OR e.actual_human_id IS DISTINCT FROM e.custodian_id OR e.actual_human_id=e.issuer_id
 OR e.r56_approved_manifest_digest IS NULL OR e.r56_approved_manifest_digest IS DISTINCT FROM b.payload_digest
 OR e.r56_approved_nonce_hash IS NULL OR e.r56_approved_nonce_hash IS DISTINCT FROM b.nonce_hash
 OR e.r56_human_consent_evidence_digest IS NULL OR e.r56_human_consent_evidence_digest !~ '^[a-f0-9]{64}$'
 OR e.r56_anchor_boottime_ns IS NULL OR e.r56_anchor_utc_lower IS NULL OR e.r56_anchor_utc_upper IS NULL
 OR e.enrollment_digest IS DISTINCT FROM b.r55_root_enrollment_digest
 OR e.host_boot_id IS DISTINCT FROM b.r55_host_boot_id OR e.clock_policy_digest IS DISTINCT FROM b.r55_clock_policy_digest
 THEN RAISE EXCEPTION 'ROOT_ENROLLMENT_OR_SINGLE_HUMAN_BINDING_REQUIRED'; END IF;
 o=company_private.r55_cp_clock_observe_local();
 IF o->>'profile' IS DISTINCT FROM 'LINUX_ADJTIMEX_DB_LOCAL_V1' OR o->>'host_boot_id' IS DISTINCT FROM e.host_boot_id::text
 OR o->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text OR o->>'source_sync_state' IS DISTINCT FROM 'SYNC'
 OR NOT ((o ?& ARRAY['boottime_before_ns','boottime_after_ns','utc_ns','maxerror_us','esterror_us','tolerance_scaled_ppm']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(o) z WHERE z.key=ANY(ARRAY['boottime_before_ns','boottime_after_ns','utc_ns','maxerror_us','esterror_us','tolerance_scaled_ppm'])
 AND (jsonb_typeof(z.value) IS DISTINCT FROM 'number' OR z.value::text !~ '^[0-9]+$'))
 THEN RAISE EXCEPTION 'ROOT_TRUSTED_LOCAL_OBSERVATION_REQUIRED'; END IF;
 bt0=(o->>'boottime_before_ns')::numeric;bt1=(o->>'boottime_after_ns')::numeric;
 IF bt0<e.r56_anchor_boottime_ns OR bt1<bt0 OR bt1>=e.not_after_boottime_ns
 OR bt1>=b.r55_not_after_boottime_ns THEN RAISE EXCEPTION 'ROOT_BOOTTIME_EXPIRED_OR_REBOOTED'; END IF;
 age=bt1-e.r56_anchor_boottime_ns;
 drift=ceil(age*(o->>'tolerance_scaled_ppm')::numeric/65536/1000000)
       +greatest((o->>'maxerror_us')::numeric,(o->>'esterror_us')::numeric)*1000;
 IF age>9007199254740991 OR drift>9007199254740991 THEN RAISE EXCEPTION 'ROOT_TIME_NUMERIC_PROFILE_RANGE'; END IF;
 lo=e.r56_anchor_utc_lower+((bt0-e.r56_anchor_boottime_ns-drift)/1000000000)::double precision*interval '1 second';
 hi=e.r56_anchor_utc_upper+((bt1-e.r56_anchor_boottime_ns+drift)/1000000000)::double precision*interval '1 second';
 -- Timestamp precision is microseconds. Expand, never round toward eligibility.
 lo=lo-interval '1 microsecond';hi=hi+interval '1 microsecond';
 wall=to_timestamp(((o->>'utc_ns')::numeric/1000000000)::double precision);
 IF NOT ((isfinite(lo) AND isfinite(hi) AND e.not_before<=lo AND lo<=hi AND hi<e.not_after
 AND hi<b.expires_at AND lo<=wall AND wall<=hi) IS TRUE) THEN RAISE EXCEPTION 'ROOT_TIME_EXPIRED_OR_AMBIGUOUS'; END IF;
 RETURN jsonb_build_object('utc_lower',lo,'utc_upper',hi,'boottime_ns',bt1,'host_boot_id',e.host_boot_id,
 'installation_id',b.installation_id,'generation',b.generation,'backend_pid',pg_backend_pid(),'transaction_id',pg_current_xact_id()::text,'db_login',session_user);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'ROOT_TRUST_ANCHOR_NOT_ENROLLED';
END $$;
ALTER FUNCTION company_private.r56_root_bounds(uuid) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_root_bounds(uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r56_setup_scope(p_tenant uuid,p_project uuid,p_write boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 RETURN EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts x
 JOIN company_private.installation_bootstrap_control b ON b.installation_id=x.installation_id AND b.generation=x.generation
 WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user
 AND b.expected_tenant_id=p_tenant AND (p_project IS NULL OR b.expected_project_id=p_project)
 AND ((p_write IS TRUE AND b.state='ARMED') OR (p_write IS FALSE AND
 (b.state='ARMED' OR (b.state='CONSUMED' AND b.consumed_command_id=x.r56_command_id))))
 AND x.r55_verified_proof_digest IS NOT NULL AND x.r56_manifest IS NOT NULL
 AND x.manifest_digest=b.payload_digest
 AND pg_has_role(session_user,'company_bootstrap_transport_r56','MEMBER'));
END $$;
ALTER FUNCTION company_private.r56_setup_scope(uuid,uuid,boolean) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_setup_scope(uuid,uuid,boolean) FROM PUBLIC;

-- The canonical r50 trigger treats added r55 fields as identity. Allow only the
-- one protected r56 RUNNING -> SUCCEEDED finalization; retain its old rule for
-- every ordinary operation and every later mutation.
CREATE OR REPLACE FUNCTION company.r50_command_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF OLD.operation='trusted_setup.consume' AND OLD.state='RUNNING' AND OLD.r55_result_digest IS NULL
 AND NEW.state='SUCCEEDED' AND NEW.r55_source_revision='r56' THEN
  IF (to_jsonb(OLD)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
   IS DISTINCT FROM
   (to_jsonb(NEW)-ARRAY['state','result_ref','r55_project_id','r55_result_payload','r55_result_digest','r55_event_sequence','r55_audit_id','r55_source_revision'])
  OR NOT EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts x
   JOIN company_private.installation_bootstrap_control b ON b.installation_id=x.installation_id AND b.generation=x.generation
   WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user
   AND x.r56_command_id=OLD.id AND b.expected_tenant_id=OLD.tenant_id AND b.expected_human_id=OLD.principal_id
   AND b.expected_project_id=NEW.r55_project_id AND b.installation_id=NEW.result_ref
   AND b.state='ARMED' AND x.manifest_digest=OLD.payload_digest)
  THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 ELSE
  IF (to_jsonb(OLD)-'state'-'result_ref') IS DISTINCT FROM (to_jsonb(NEW)-'state'-'result_ref')
  OR (OLD.state IN ('SUCCEEDED','FAILED') AND ROW(OLD.state,OLD.result_ref) IS DISTINCT FROM ROW(NEW.state,NEW.result_ref))
  THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION company.r50_command_identity_immutable() FROM PUBLIC;

CREATE FUNCTION company_private.r56_bootstrap_enter(p_installation uuid,p_generation bigint,p_nonce bytea,p_raw bytea,p_tag bytea,p_key bytea)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE b company_private.installation_bootstrap_control%ROWTYPE;e company_private.r55_setup_root_enrollments%ROWTYPE;
 j jsonb;m jsonb;item bytea;raw bytea;n uuid;bounds jsonb;v bytea[];op text;reg company_private.operation_permissions%ROWTYPE;
BEGIN
 IF NOT pg_has_role(session_user,'company_bootstrap_transport_r56','MEMBER') THEN RAISE EXCEPTION 'TRUSTED_BOOTSTRAP_TRANSPORT_REQUIRED'; END IF;
 IF p_installation IS NULL OR p_generation IS NULL OR p_generation<1 OR p_nonce IS NULL OR octet_length(p_nonce)<>32
 OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 65536 OR p_tag IS NULL OR octet_length(p_tag)<>32
 OR p_key IS NULL OR octet_length(p_key)<>32 THEN RAISE EXCEPTION 'INVALID_BOOTSTRAP_WIRE'; END IF;
 IF EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id())
 THEN RAISE EXCEPTION 'BOOTSTRAP_CONTEXT_ALREADY_BOUND'; END IF;
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation;
 PERFORM pg_advisory_xact_lock(b.lock_id);
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation FOR UPDATE;
 SELECT * INTO STRICT e FROM company_private.r55_setup_root_enrollments WHERE installation_id=p_installation AND generation=p_generation FOR SHARE;
 IF b.generation IS DISTINCT FROM p_generation OR b.state NOT IN ('ARMED','CONSUMED')
 OR encode(sha256(p_nonce),'hex') IS DISTINCT FROM b.nonce_hash
 OR e.key_fingerprint IS DISTINCT FROM encode(sha256(p_key),'hex')
 OR NOT EXISTS(SELECT 1 FROM company_private.scope_lock_registry WHERE lock_id=b.lock_id AND rank=0
 AND identity_key=jsonb_build_object('kind','INSTALLATION_BOOTSTRAP','installation_id',p_installation))
 THEN RAISE EXCEPTION 'BOOTSTRAP_INSTALLATION_BINDING_REJECTED'; END IF;
 bounds=company_private.r56_root_bounds(p_installation);
 j=convert_from(p_raw,'UTF8')::jsonb;
 IF jsonb_typeof(j) IS DISTINCT FROM 'object' OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1)
 THEN RAISE EXCEPTION 'AMBIGUOUS_BOOTSTRAP_PROOF'; END IF;
 IF NOT ((j ?& ARRAY['profile','phase','installation_id','generation','backend_pid','transaction_id','db_login','human_id','host_boot_id','nonce_hash','manifest_digest','root_proof_digest','release_digest']) IS TRUE)
 OR (SELECT count(*) FROM jsonb_object_keys(j))<>13
 OR EXISTS(SELECT 1 FROM jsonb_each(j) z WHERE z.key NOT IN ('generation','backend_pid') AND jsonb_typeof(z.value) IS DISTINCT FROM 'string')
 OR jsonb_typeof(j->'generation') IS DISTINCT FROM 'number' OR j->>'generation' !~ '^[1-9][0-9]*$'
 OR jsonb_typeof(j->'backend_pid') IS DISTINCT FROM 'number' OR j->>'backend_pid' !~ '^[1-9][0-9]*$'
 THEN RAISE EXCEPTION 'BOOTSTRAP_PROOF_TYPED_FIELDS_REQUIRED'; END IF;
 IF NOT ((j->>'profile'='r56.bootstrap-enter.v1' AND j->>'phase'='BOOTSTRAP_ENTER'
 AND j->>'installation_id'=b.installation_id::text AND j->>'generation'=b.generation::text
 AND j->>'backend_pid'=pg_backend_pid()::text AND j->>'transaction_id'=pg_current_xact_id()::text
 AND j->>'db_login'=session_user::text AND j->>'human_id'=e.actual_human_id::text
 AND j->>'host_boot_id'=e.host_boot_id::text AND j->>'nonce_hash'=b.nonce_hash
 AND j->>'manifest_digest'=b.payload_digest AND j->>'root_proof_digest'=b.r55_root_proof_digest AND j->>'release_digest'=e.release_digest) IS TRUE)
 THEN RAISE EXCEPTION 'BOOTSTRAP_PROOF_CONTEXT_MISMATCH'; END IF;
 raw=convert_to('R56-BOOTSTRAP-v1','UTF8')||decode('00','hex');
 v=ARRAY[convert_to(b.installation_id::text,'UTF8'),convert_to(b.generation::text,'UTF8'),convert_to(e.issuer_id::text,'UTF8'),
 convert_to(e.key_id::text,'UTF8'),convert_to(e.enrollment_revision::text,'UTF8'),p_raw];
 FOREACH item IN ARRAY v LOOP raw=raw||convert_to(octet_length(item)::text||':','UTF8')||item; END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(p_key,raw),p_tag) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_BOOTSTRAP_HMAC'; END IF;
 m=(convert_from(b.r55_root_proof,'UTF8')::jsonb)->'manifest';
 IF m IS NULL OR jsonb_typeof(m) IS DISTINCT FROM 'object'
 OR encode(sha256(convert_to(m::text,'UTF8')),'hex') IS DISTINCT FROM b.payload_digest
 OR encode(sha256(convert_to((m-'setup_manifest_digest')::text,'UTF8')),'hex') IS DISTINCT FROM b.setup_manifest_digest
 OR m->>'verified_human_id' IS DISTINCT FROM e.actual_human_id::text
 OR (m->>'tenant_id')::uuid IS DISTINCT FROM b.expected_tenant_id
 OR (m->>'project_id')::uuid IS DISTINCT FROM b.expected_project_id
 OR (m->>'workspace_id')::uuid IS DISTINCT FROM b.expected_workspace_id
 OR jsonb_typeof(m->'finite_initial_operations') IS DISTINCT FROM 'array'
 OR jsonb_array_length(m->'finite_initial_operations') NOT BETWEEN 1 AND 4
 THEN RAISE EXCEPTION 'BOOTSTRAP_CANONICAL_MANIFEST_MISMATCH'; END IF;
 FOR op IN SELECT value FROM jsonb_array_elements_text(m->'finite_initial_operations') ORDER BY value LOOP
  IF op IS NULL OR op NOT IN ('projects.read','projects.create','e0.setup_mandate_consume','e0.evaluation_attempt_create')
  OR NOT ((op=ANY(e.allowed_operations) AND op=ANY(b.r55_allowed_operations)) IS TRUE) THEN RAISE EXCEPTION 'BOOTSTRAP_SCOPE_EXPANSION'; END IF;
  SELECT * INTO STRICT reg FROM company_private.operation_permissions WHERE operation_id=op FOR SHARE;
  IF reg.scope_kind IS DISTINCT FROM 'PROJECT' OR reg.permission LIKE '%*%' OR reg.permission LIKE 'secret.read:%'
  THEN RAISE EXCEPTION 'BOOTSTRAP_PERMISSION_NOT_FINITE_PROJECT_SCOPE'; END IF;
 END LOOP;
 IF jsonb_array_length(m->'finite_initial_operations')<1 OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(m->'finite_initial_operations') z GROUP BY value HAVING count(*)>1)
 THEN RAISE EXCEPTION 'BOOTSTRAP_DUPLICATE_OR_EMPTY_PERMISSION'; END IF;
 n=gen_random_uuid();
 INSERT INTO company_private.bootstrap_request_contexts(backend_pid,transaction_id,db_login,context_nonce,installation_id,generation,manifest_digest,
 human_proof_digest,expires_at,r55_verified_proof_digest,r55_mandate_digest,r56_manifest,r56_command_id)
 VALUES(pg_backend_pid(),pg_current_xact_id(),session_user,n,b.installation_id,b.generation,b.payload_digest,
 encode(sha256(p_raw),'hex'),b.expires_at,b.r55_root_proof_digest,
 encode(sha256(convert_to((m->'e0_mandate')::text,'UTF8')),'hex'),m,b.consumed_command_id);
 RETURN n;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'BOOTSTRAP_TRUSTED_SOURCE_MISSING';
END $$;
ALTER FUNCTION company_private.r56_bootstrap_enter(uuid,bigint,bytea,bytea,bytea,bytea) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_enter(uuid,bigint,bytea,bytea,bytea,bytea) FROM PUBLIC;

CREATE FUNCTION company_private.r56_bootstrap_final_proof(p_nonce uuid,p_phase text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.bootstrap_request_contexts%ROWTYPE;p jsonb;b jsonb;d text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id()
 AND db_login=session_user AND context_nonce=p_nonce;
 IF NOT pg_has_role(session_user,'company_bootstrap_transport_r56','MEMBER') THEN RAISE EXCEPTION 'BOOTSTRAP_TRANSPORT_REVOKED'; END IF;
 IF p_phase IS NULL OR p_phase NOT IN ('AFTER_DOMAIN_LOCKS','COMMIT_CUT','REPLAY_READ') THEN RAISE EXCEPTION 'INVALID_BOOTSTRAP_PHASE'; END IF;
 b=company_private.r56_root_bounds(x.installation_id);
 p=jsonb_build_object('profile','r56.bootstrap-final.v1','phase',p_phase,'context_nonce',x.context_nonce,
 'installation_id',x.installation_id,'generation',x.generation,'manifest_digest',x.manifest_digest,
 'human_proof_digest',x.human_proof_digest,'bounds',b);
 d=encode(sha256(convert_to(p::text,'UTF8')),'hex');
 UPDATE company_private.bootstrap_request_contexts SET r56_final_proof=p,r55_final_proof_digest=d
 WHERE backend_pid=x.backend_pid AND transaction_id=x.transaction_id AND context_nonce=x.context_nonce AND db_login=session_user;
 IF NOT FOUND THEN RAISE EXCEPTION 'BOOTSTRAP_FINAL_CONTEXT_LOST'; END IF;
 RETURN p;
END $$;
ALTER FUNCTION company_private.r56_bootstrap_final_proof(uuid,text) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_final_proof(uuid,text) FROM PUBLIC;

-- Finite domain policies use a protected bootstrap context, never app.* GUC.
CREATE POLICY r56_tenant_read ON company.tenants FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(id,NULL,false));
CREATE POLICY r56_tenant_insert ON company.tenants FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(id,NULL,true));
DO $policies$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['principals','memberships','workspaces'] LOOP
  EXECUTE format('CREATE POLICY r56_boot_read ON company.%I FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,NULL,false))',t);
  EXECUTE format('CREATE POLICY r56_boot_insert ON company.%I FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,NULL,true))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['projects'] LOOP
  EXECUTE format('CREATE POLICY r56_boot_read ON company.%I FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,id,false))',t);
  EXECUTE format('CREATE POLICY r56_boot_insert ON company.%I FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,id,true))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['objectives','plans','project_grants','outbox','project_event_heads'] LOOP
  EXECUTE format('CREATE POLICY r56_boot_read ON company.%I FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,project_id,false))',t);
  EXECUTE format('CREATE POLICY r56_boot_insert ON company.%I FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,project_id,true))',t);
 END LOOP;
END $policies$;
CREATE POLICY r56_heads_read ON company.authority_scope_heads FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,project_id,false));
CREATE POLICY r56_heads_insert ON company.authority_scope_heads FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,project_id,true) AND scope_kind IN ('TENANT','PROJECT') AND epoch=0 AND revision=0);
CREATE POLICY r56_command_read ON company.commands FOR SELECT TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,r55_project_id,false) AND operation='trusted_setup.consume');
CREATE POLICY r56_command_insert ON company.commands FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,NULL,true) AND operation='trusted_setup.consume' AND state='RUNNING');
CREATE POLICY r56_command_update ON company.commands FOR UPDATE TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,NULL,true) AND operation='trusted_setup.consume') WITH CHECK(company_private.r56_setup_scope(tenant_id,r55_project_id,true) AND operation='trusted_setup.consume' AND state='SUCCEEDED');
CREATE POLICY r56_event_head_update ON company.project_event_heads FOR UPDATE TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,project_id,true)) WITH CHECK(company_private.r56_setup_scope(tenant_id,project_id,true) AND writer_generation=54);
CREATE POLICY r56_audit ON company.audit_events TO company_bootstrap_functions_r56 USING(company_private.r56_setup_scope(tenant_id,NULL,false)) WITH CHECK(company_private.r56_setup_scope(tenant_id,NULL,true));
CREATE POLICY r56_receipt_insert ON company_private.bootstrap_receipts FOR INSERT TO company_bootstrap_functions_r56 WITH CHECK(company_private.r56_setup_scope(tenant_id,project_id,true));

CREATE FUNCTION company_private.r56_bootstrap_initial_write(p_nonce uuid,p_correlation uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.bootstrap_request_contexts%ROWTYPE;b company_private.installation_bootstrap_control%ROWTYPE;
 m jsonb;v jsonb;op text;permission_text text;cmd uuid;tl bigint;pl bigint;gd text;bounds jsonb;
BEGIN
 SELECT * INTO STRICT x FROM company_private.bootstrap_request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND context_nonce=p_nonce;
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=x.installation_id FOR UPDATE;
 IF b.state IS DISTINCT FROM 'ARMED' OR b.generation IS DISTINCT FROM x.generation OR p_correlation IS NULL THEN RAISE EXCEPTION 'BOOTSTRAP_NOT_FRESH_ARMED'; END IF;
 m=x.r56_manifest;
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
ALTER FUNCTION company_private.r56_bootstrap_initial_write(uuid,uuid) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_initial_write(uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r56_bootstrap_finish(p_nonce uuid,p_command uuid) RETURNS jsonb
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
 proof=company_private.r56_bootstrap_final_proof(p_nonce,'AFTER_DOMAIN_LOCKS');
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
 PERFORM company_private.r56_bootstrap_final_proof(p_nonce,'COMMIT_CUT');
 RETURN jsonb_build_object('command_id',c.id,'state','SUCCEEDED','result_ref',b.installation_id,'receipt_digest',d,'spawned',false);
END $$;
ALTER FUNCTION company_private.r56_bootstrap_finish(uuid,uuid) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_finish(uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r56_bootstrap_invariant() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE c company.commands%ROWTYPE;b company_private.bootstrap_receipts%ROWTYPE;
BEGIN
 IF NEW.operation IS DISTINCT FROM 'trusted_setup.consume' OR NEW.r55_source_revision IS DISTINCT FROM 'r56' THEN RETURN NULL; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=NEW.tenant_id AND id=NEW.id;
 SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE command_id=c.id AND tenant_id=c.tenant_id;
 IF c.state IS DISTINCT FROM 'SUCCEEDED' OR b.r56_result_digest IS DISTINCT FROM c.r55_result_digest
 OR b.accepted_human_id IS DISTINCT FROM c.principal_id OR b.payload_digest IS DISTINCT FROM c.payload_digest
 OR NOT EXISTS(SELECT 1 FROM company_private.installation_bootstrap_control z WHERE z.installation_id=b.installation_id AND z.generation=b.generation AND z.state='CONSUMED' AND z.consumed_command_id=c.id)
 OR NOT EXISTS(SELECT 1 FROM company.audit_events a WHERE a.id=c.r55_audit_id AND a.tenant_id=c.tenant_id AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id AND a.kind='InstallationBootstrapped')
 OR NOT EXISTS(SELECT 1 FROM company.outbox e WHERE e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.project_sequence=1 AND e.event_instance_id=c.id AND e.event_writer_generation=54 AND e.payload->>'result_digest'=c.r55_result_digest)
 THEN RAISE EXCEPTION 'BOOTSTRAP_ATOMIC_WITNESS_MISSING'; END IF;
 PERFORM company_private.r56_root_bounds(b.installation_id);
 RETURN NULL;
END $$;
ALTER FUNCTION company_private.r56_bootstrap_invariant() OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_invariant() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER r56_bootstrap_invariant AFTER INSERT OR UPDATE ON company.commands DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION company_private.r56_bootstrap_invariant();

CREATE FUNCTION company_private.r56_bootstrap_consume(p_installation uuid,p_generation bigint,p_nonce bytea,p_raw bytea,p_tag bytea,p_key bytea,p_correlation uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n uuid;cmd uuid;result jsonb;b company_private.bootstrap_receipts%ROWTYPE;ctl company_private.installation_bootstrap_control%ROWTYPE;
BEGIN
 IF p_correlation IS NULL THEN RAISE EXCEPTION 'BOOTSTRAP_CORRELATION_REQUIRED'; END IF;
 n=company_private.r56_bootstrap_enter(p_installation,p_generation,p_nonce,p_raw,p_tag,p_key);
 SELECT * INTO STRICT ctl FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation;
 IF ctl.state='CONSUMED' THEN
  SELECT * INTO STRICT b FROM company_private.bootstrap_receipts WHERE installation_id=p_installation AND generation=p_generation AND payload_digest=ctl.payload_digest AND accepted_human_id=ctl.expected_human_id;
  IF b.r56_result_digest IS NULL OR b.r56_final_proof IS NULL OR NOT EXISTS(
   SELECT 1 FROM company.commands c JOIN company.audit_events a ON a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id
   JOIN company.outbox e ON e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.event_instance_id=c.id
   WHERE c.tenant_id=b.tenant_id AND c.id=b.command_id AND c.principal_id=b.accepted_human_id
   AND c.state='SUCCEEDED' AND c.result_ref=b.installation_id AND c.payload_digest=b.payload_digest
   AND c.r55_source_revision='r56' AND c.r55_result_digest=b.r56_result_digest
   AND a.kind='InstallationBootstrapped' AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id
   AND e.kind='InstallationBootstrapped' AND e.project_sequence=1 AND e.event_writer_generation=54
   AND e.payload->>'result_digest'=c.r55_result_digest)
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
ALTER FUNCTION company_private.r56_bootstrap_consume(uuid,bigint,bytea,bytea,bytea,bytea,uuid) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.r56_bootstrap_consume(uuid,bigint,bytea,bytea,bytea,bytea,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r56_bootstrap_consume(uuid,bigint,bytea,bytea,bytea,bytea,uuid) TO company_bootstrap_transport_r56;
-- Fresh/native catalog preflight and explicit G0/human enrollment remain mandatory.
-- Domain DML and private helper EXECUTE are never granted to the transport.
ROLLBACK;
