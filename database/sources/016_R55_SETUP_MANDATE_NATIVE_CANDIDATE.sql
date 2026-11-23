-- SOURCE CANDIDATE ONLY. No root credential, human assignment or migration is installed.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

-- Built-in SHA256 only; no extension install. Restrict keys to the 32-byte profile.
CREATE FUNCTION company_private.r55_cp_hmac_sha256(p_key bytea,p_message bytea)
RETURNS bytea LANGUAGE plpgsql IMMUTABLE STRICT SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE k bytea; ip bytea; op bytea; i integer;
BEGIN
 IF octet_length(p_key)<>32 THEN RAISE EXCEPTION 'KEY_32_BYTES_REQUIRED'; END IF;
 k=p_key||decode(repeat('00',32),'hex'); ip=k; op=k;
 FOR i IN 0..63 LOOP
  ip=set_byte(ip,i,get_byte(k,i)#54); op=set_byte(op,i,get_byte(k,i)#92);
 END LOOP;
 RETURN sha256(op||sha256(ip||p_message));
END $$;
REVOKE ALL ON FUNCTION company_private.r55_cp_hmac_sha256(bytea,bytea) FROM PUBLIC;

-- No new tenant/task/grant authority: these columns attach a separately enrolled
-- root statement to the existing BASE-01 installation identity. Historical rows
-- remain NULL, never backfilled with fabricated evidence.
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_root_proof_digest text;
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_root_enrollment_digest text;
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_allowed_operations text[];
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_clock_policy_digest text;
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_host_boot_id uuid;
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_not_after_boottime_ns numeric(20,0);
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_root_proof bytea;
ALTER TABLE company_private.installation_bootstrap_control ADD COLUMN r55_root_tag bytea;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r55_verified_proof_digest text;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r55_final_proof_digest text;
ALTER TABLE company_private.bootstrap_request_contexts ADD COLUMN r55_mandate_digest text;

-- One necessary PRE-TENANT trust record. Existing signer_enrollments has a
-- tenant/principal FK and cannot authenticate the first human before that tenant
-- exists. It remains the post-tenant signer authority; no duplicate grant table.
CREATE TABLE company_private.r55_setup_root_enrollments (
 installation_id uuid NOT NULL,generation bigint NOT NULL CHECK(generation>0),
 enrollment_revision bigint NOT NULL CHECK(enrollment_revision>0),
 issuer_id uuid NOT NULL,key_id uuid NOT NULL,key_fingerprint text NOT NULL CHECK(key_fingerprint ~ '^[a-f0-9]{64}$'),
 actual_human_id uuid NOT NULL,custodian_id uuid NOT NULL,
 verified_identity_evidence_digest text NOT NULL CHECK(verified_identity_evidence_digest ~ '^[a-f0-9]{64}$'),
 release_digest text NOT NULL CHECK(release_digest ~ '^[a-f0-9]{64}$'),
 enrollment_digest text NOT NULL CHECK(enrollment_digest ~ '^[a-f0-9]{64}$'),
 allowed_operations text[] NOT NULL CHECK(cardinality(allowed_operations)>0),
 host_boot_id uuid NOT NULL,clock_policy_digest text NOT NULL CHECK(clock_policy_digest ~ '^[a-f0-9]{64}$'),
 not_before timestamptz NOT NULL,not_after timestamptz NOT NULL,not_after_boottime_ns numeric(20,0) NOT NULL,
 lock_id bigint NOT NULL REFERENCES company_private.scope_lock_registry(lock_id),
 revoked_at timestamptz,compromised_at timestamptz,
 PRIMARY KEY(installation_id,generation),CHECK(not_after>not_before),CHECK(actual_human_id<>issuer_id)
);
ALTER TABLE company_private.r55_setup_root_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_private.r55_setup_root_enrollments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company_private.r55_setup_root_enrollments FROM PUBLIC;
-- NO INSERT policy or runtime grant. Actual records can only follow independent
-- approved physical provisioning; this candidate inserts NO actual humans/keys.

CREATE FUNCTION company_private.r55_cp_setup_control_arm(p_installation uuid,p_generation bigint,p_raw bytea,p_tag bytea,p_secret bytea)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e company_private.r55_setup_root_enrollments%ROWTYPE;j jsonb;m jsonb;
 message bytea;item bytea;values bytea[];op text;
BEGIN
 IF session_user<>'company_provisioning_runtime_r55' THEN RAISE EXCEPTION 'TRUSTED_PROVISIONING_LOGIN_REQUIRED'; END IF;
 IF p_installation IS NULL OR p_generation IS NULL OR p_generation<1 OR p_raw IS NULL
 OR octet_length(p_raw)=0 OR octet_length(p_raw)>65536 OR p_tag IS NULL OR octet_length(p_tag)<>32
 OR p_secret IS NULL OR octet_length(p_secret)<>32 THEN RAISE EXCEPTION 'INVALID_ROOT_PROOF'; END IF;
 SELECT * INTO STRICT e FROM company_private.r55_setup_root_enrollments WHERE installation_id=p_installation AND generation=p_generation FOR SHARE;
 IF e.revoked_at IS NOT NULL OR e.compromised_at IS NOT NULL OR e.actual_human_id IS NULL OR e.custodian_id IS NULL
 OR e.key_fingerprint IS DISTINCT FROM encode(sha256(p_secret),'hex')
 OR NOT isfinite(e.not_before) OR NOT isfinite(e.not_after)
 THEN RAISE EXCEPTION 'BLOCKED_HUMAN_ENROLLMENT'; END IF;
 PERFORM pg_advisory_xact_lock(e.lock_id);
 IF NOT EXISTS(SELECT 1 FROM company_private.scope_lock_registry WHERE lock_id=e.lock_id
 AND rank=0 AND identity_key=jsonb_build_object('kind','INSTALLATION_BOOTSTRAP','installation_id',p_installation))
 THEN RAISE EXCEPTION 'ROOT_LOCK_IDENTITY_MISMATCH'; END IF;
 j=convert_from(p_raw,'UTF8')::jsonb;
 IF jsonb_typeof(j)<>'object' OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1)
 THEN RAISE EXCEPTION 'AMBIGUOUS_ROOT_JSON'; END IF;
 IF jsonb_typeof(j->'utc_lower_bound') IS DISTINCT FROM 'string'
 OR jsonb_typeof(j->'utc_upper_bound') IS DISTINCT FROM 'string'
 OR j->>'utc_lower_bound' IS NULL OR j->>'utc_upper_bound' IS NULL
 THEN RAISE EXCEPTION 'ROOT_REQUIRED_TYPED_TIME'; END IF;
 IF NOT ((j ?& ARRAY['installation_id','generation','backend_pid','transaction_id','db_login','host_boot_id','utc_lower_bound','utc_upper_bound','manifest']) IS TRUE)
 OR j->>'installation_id' IS DISTINCT FROM p_installation::text OR j->>'generation' IS DISTINCT FROM p_generation::text
 OR j->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text OR j->>'transaction_id' IS DISTINCT FROM pg_current_xact_id()::text
 OR j->>'db_login' IS DISTINCT FROM session_user::text OR j->>'host_boot_id' IS DISTINCT FROM e.host_boot_id::text
 OR NOT ((isfinite((j->>'utc_lower_bound')::timestamptz) AND isfinite((j->>'utc_upper_bound')::timestamptz)
 AND e.not_before<=(j->>'utc_lower_bound')::timestamptz
 AND (j->>'utc_lower_bound')::timestamptz<=(j->>'utc_upper_bound')::timestamptz
 AND (j->>'utc_upper_bound')::timestamptz<e.not_after) IS TRUE)
 THEN RAISE EXCEPTION 'ROOT_PROOF_BINDING_MISMATCH'; END IF;
 message=convert_to('R55-CP-PROOF-v1','UTF8')||decode('00','hex');
 values=ARRAY[convert_to('SETUP','UTF8'),convert_to(e.issuer_id::text,'UTF8'),convert_to(e.key_id::text,'UTF8'),convert_to(e.enrollment_revision::text,'UTF8'),p_raw];
 FOREACH item IN ARRAY values LOOP message=message||convert_to(octet_length(item)::text||':','UTF8')||item; END LOOP;
 IF company_private.r55_cp_hmac_sha256(p_secret,message) IS DISTINCT FROM p_tag THEN RAISE EXCEPTION 'INVALID_ROOT_HMAC'; END IF;
 m=j->'manifest';
 IF NOT ((jsonb_typeof(m)='object' AND m ?& ARRAY['tenant_id','project_id','workspace_id','verified_human_id','nonce_hash','setup_manifest_digest','finite_initial_operations','valid_until']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(m) z WHERE z.key IN ('tenant_id','project_id','workspace_id','verified_human_id','nonce_hash','setup_manifest_digest','valid_until')
 AND jsonb_typeof(z.value) IS DISTINCT FROM 'string')
 OR m->>'verified_human_id' IS DISTINCT FROM e.actual_human_id::text
 OR NOT ((isfinite((m->>'valid_until')::timestamptz) AND (m->>'valid_until')::timestamptz<=e.not_after
 AND (j->>'utc_upper_bound')::timestamptz<(m->>'valid_until')::timestamptz) IS TRUE)
 OR m->>'nonce_hash' !~ '^[a-f0-9]{64}$' OR m->>'setup_manifest_digest' !~ '^[a-f0-9]{64}$'
 OR jsonb_typeof(m->'finite_initial_operations') IS DISTINCT FROM 'array' OR jsonb_array_length(m->'finite_initial_operations')<1
 THEN RAISE EXCEPTION 'INVALID_FINITE_ROOT_MANIFEST'; END IF;
 FOR op IN SELECT jsonb_array_elements_text(m->'finite_initial_operations') LOOP
  IF op IS NULL OR NOT ((op=ANY(e.allowed_operations)) IS TRUE) OR op LIKE '%*%' OR op NOT IN ('projects.read','projects.create','e0.setup_mandate_consume','e0.evaluation_attempt_create')
  THEN RAISE EXCEPTION 'ROOT_SCOPE_EXPANSION'; END IF;
 END LOOP;
 INSERT INTO company_private.installation_bootstrap_control(installation_id,generation,state,expected_tenant_id,expected_project_id,expected_workspace_id,
 expected_human_id,nonce_hash,payload_digest,setup_manifest_digest,expires_at,lock_id,r55_root_proof_digest,r55_root_enrollment_digest,
 r55_allowed_operations,r55_clock_policy_digest,r55_host_boot_id,r55_not_after_boottime_ns,r55_root_proof,r55_root_tag)
 VALUES(p_installation,p_generation,'ARMED',(m->>'tenant_id')::uuid,(m->>'project_id')::uuid,(m->>'workspace_id')::uuid,e.actual_human_id,
 m->>'nonce_hash',encode(sha256(convert_to(m::text,'UTF8')),'hex'),m->>'setup_manifest_digest',(m->>'valid_until')::timestamptz,e.lock_id,
 encode(sha256(p_raw),'hex'),e.enrollment_digest,ARRAY(SELECT jsonb_array_elements_text(m->'finite_initial_operations')),e.clock_policy_digest,e.host_boot_id,e.not_after_boottime_ns,p_raw,p_tag);
 RETURN p_installation;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'BLOCKED_HUMAN_ENROLLMENT';
END $$;
ALTER FUNCTION company_private.r55_cp_setup_control_arm(uuid,bigint,bytea,bytea,bytea) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_setup_control_arm(uuid,bigint,bytea,bytea,bytea) FROM PUBLIC;

-- A bootstrap receipt is immutable. The mandate is populated in the initial
-- INSERT, never by UPDATE after setup. This source supplies the missing writer
-- seam, not a general-purpose ability to invent accepted_human_id.
CREATE FUNCTION company_private.r55_cp_setup_receipt_issue(
 p_installation uuid,p_command uuid,p_initial_grants_digest text,
 p_mandate jsonb,p_valid_until timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE b company_private.installation_bootstrap_control%ROWTYPE;
 x company_private.bootstrap_request_contexts%ROWTYPE; c company.commands%ROWTYPE;
 v_digest text; g_digest text;
BEGIN
 IF session_user<>'company_setup_runtime' THEN RAISE EXCEPTION 'TRUSTED_SETUP_LOGIN_REQUIRED'; END IF;
 IF p_installation IS NULL OR p_command IS NULL OR p_initial_grants_digest IS NULL
 OR p_initial_grants_digest !~ '^[a-f0-9]{64}$' OR p_mandate IS NULL OR p_valid_until IS NULL
 THEN RAISE EXCEPTION 'INVALID_SETUP_RECEIPT_BINDING'; END IF;
 SELECT * INTO STRICT b FROM company_private.installation_bootstrap_control WHERE installation_id=p_installation FOR UPDATE;
 SELECT * INTO STRICT x FROM company_private.bootstrap_request_contexts
 WHERE installation_id=p_installation AND backend_pid=pg_backend_pid()
 AND transaction_id=pg_current_xact_id() AND db_login=session_user;
 IF b.state IS DISTINCT FROM 'ARMED' OR b.generation IS DISTINCT FROM x.generation
 OR b.payload_digest IS DISTINCT FROM x.manifest_digest
 OR b.r55_root_proof_digest IS NULL OR b.r55_root_enrollment_digest IS NULL
 OR x.r55_verified_proof_digest IS DISTINCT FROM b.r55_root_proof_digest
 OR x.r55_final_proof_digest IS NULL OR b.r55_allowed_operations IS NULL
 OR b.r55_host_boot_id IS NULL OR b.r55_clock_policy_digest IS NULL
 OR b.r55_not_after_boottime_ns IS NULL
 THEN RAISE EXCEPTION 'BLOCKED_VERIFIED_ROOT_AND_FINAL_CLOCK_PROOF'; END IF;
 -- Root verifier adapter must have checked fresh BOOTTIME after every lock/FK
 -- wait. UTC here is only an additional rejection, never the health proof.
 IF b.expires_at<=clock_timestamp() OR x.expires_at<=clock_timestamp()
 OR p_valid_until>b.expires_at OR p_valid_until<=clock_timestamp()
 THEN RAISE EXCEPTION 'EXPIRED_SETUP_MANDATE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=b.expected_tenant_id
 AND id=b.expected_human_id AND kind='HUMAN') THEN RAISE EXCEPTION 'BLOCKED_HUMAN_DECISION'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.projects WHERE tenant_id=b.expected_tenant_id
 AND id=b.expected_project_id AND workspace_id=b.expected_workspace_id)
 THEN RAISE EXCEPTION 'SETUP_PROJECT_WORKSPACE_MISMATCH'; END IF;
 IF NOT ((jsonb_typeof(p_mandate)='object' AND p_mandate->>'kind'='EVALUATION_ONLY'
 AND p_mandate->>'network'='DENY' AND p_mandate->>'external_effects'='DENY'
 AND p_mandate->>'workspace_id'=b.expected_workspace_id::text
 AND p_mandate ?& ARRAY['subject_principal_id','role_id','model_digest','fixture_digest','plan_id','profile_digest','negative_suite_digest','required_positive_oracle_ids','required_negative_oracle_ids']
 AND p_mandate->>'model_digest' ~ '^[a-f0-9]{64}$' AND p_mandate->>'fixture_digest' ~ '^[a-f0-9]{64}$'
 AND p_mandate->>'profile_digest' ~ '^[a-f0-9]{64}$' AND p_mandate->>'negative_suite_digest' ~ '^[a-f0-9]{64}$'
 AND jsonb_typeof(p_mandate->'required_positive_oracle_ids')='array'
 AND jsonb_array_length(p_mandate->'required_positive_oracle_ids')>0
 AND jsonb_typeof(p_mandate->'required_negative_oracle_ids')='array'
 AND jsonb_array_length(p_mandate->'required_negative_oracle_ids')>0) IS TRUE)
 THEN RAISE EXCEPTION 'INVALID_FINITE_E0_MANDATE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=b.expected_tenant_id
 AND id=(p_mandate->>'subject_principal_id')::uuid AND kind IN ('VERIFIER','WORKER'))
 THEN RAISE EXCEPTION 'EVALUATOR_PRINCIPAL_NOT_ENROLLED'; END IF;
 -- Digest must have been signed as part of the root setup manifest, not supplied
 -- as a new mandate by an ordinary authenticated human after provisioning.
 v_digest=encode(sha256(convert_to(p_mandate::text,'UTF8')),'hex');
 IF NOT EXISTS(SELECT 1 FROM company_private.bootstrap_request_contexts z
 WHERE z.backend_pid=pg_backend_pid() AND z.transaction_id=pg_current_xact_id()
 AND z.db_login=session_user AND z.r55_mandate_digest=v_digest)
 THEN RAISE EXCEPTION 'MANDATE_NOT_IN_SIGNED_ROOT_PROOF'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.project_grants WHERE tenant_id=b.expected_tenant_id
 AND project_id=b.expected_project_id AND principal_id=b.expected_human_id)
 OR EXISTS(SELECT 1 FROM company.project_grants g WHERE g.tenant_id=b.expected_tenant_id AND g.project_id=b.expected_project_id
 AND (g.principal_id IS DISTINCT FROM b.expected_human_id OR g.granted_by IS DISTINCT FROM b.expected_human_id
 OR g.parent_grant_id IS NOT NULL OR g.task_scope_id IS NOT NULL OR g.grant_id IS NULL
 OR g.revoked_at IS NOT NULL OR g.valid_until>p_valid_until OR g.valid_until<=clock_timestamp()
 OR g.permission LIKE '%*%' OR COALESCE(g.base_permission,g.permission) LIKE 'secret.read:%'
 OR NOT EXISTS(SELECT 1 FROM company_private.operation_permissions op WHERE op.operation_id=ANY(b.r55_allowed_operations)
 AND op.permission=COALESCE(g.base_permission,g.permission))))
 THEN RAISE EXCEPTION 'INITIAL_GRANT_CEILING_VIOLATED'; END IF;
 SELECT encode(sha256(convert_to(jsonb_agg(jsonb_build_array(g.grant_id,g.permission,g.valid_from,g.valid_until) ORDER BY g.grant_id)::text,'UTF8')),'hex')
 INTO g_digest FROM company.project_grants g WHERE g.tenant_id=b.expected_tenant_id AND g.project_id=b.expected_project_id;
 IF g_digest IS DISTINCT FROM p_initial_grants_digest THEN RAISE EXCEPTION 'INITIAL_GRANT_DIGEST_MISMATCH'; END IF;
 SELECT * INTO STRICT c FROM company.commands WHERE tenant_id=b.expected_tenant_id AND id=p_command FOR UPDATE;
 IF c.principal_id IS DISTINCT FROM b.expected_human_id OR c.operation IS DISTINCT FROM 'trusted_setup.consume'
 OR c.payload_digest IS DISTINCT FROM b.payload_digest OR c.state IS DISTINCT FROM 'SUCCEEDED'
 THEN RAISE EXCEPTION 'SETUP_COMMAND_MISMATCH'; END IF;
 INSERT INTO company_private.bootstrap_receipts(installation_id,generation,tenant_id,project_id,command_id,
 payload_digest,setup_manifest_digest,initial_grants_digest,accepted_human_id,e0_mandate,e0_valid_until)
 VALUES(b.installation_id,b.generation,b.expected_tenant_id,b.expected_project_id,p_command,
 b.payload_digest,b.setup_manifest_digest,p_initial_grants_digest,b.expected_human_id,p_mandate,p_valid_until);
 UPDATE company_private.installation_bootstrap_control SET state='CONSUMED',consumed_command_id=p_command
 WHERE installation_id=b.installation_id AND generation=b.generation AND state='ARMED';
 IF NOT FOUND THEN RAISE EXCEPTION 'SETUP_CONSUME_CAS_CONFLICT'; END IF;
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind)
 VALUES(b.expected_tenant_id,c.correlation_id,b.expected_human_id,'SetupMandatePersisted');
 -- Caller must finish canonical setup event/finalizer in the same transaction.
 -- No EXECUTE is granted while that pretenant bridge remains unimplemented.
 RETURN b.installation_id;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'SETUP_ROOT_UNRESOLVED';
END $$;
ALTER FUNCTION company_private.r55_cp_setup_receipt_issue(uuid,uuid,text,jsonb,timestamptz) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_setup_receipt_issue(uuid,uuid,text,jsonb,timestamptz) FROM PUBLIC;
-- Deliberately NO GRANT: bootstrap_enter, verified physical enrollment, final
-- BOOTTIME cut and setup-specific event finalization are not installed sources.
-- Exact table/lock privileges are source designs, never executed here.
GRANT SELECT ON company_private.r55_setup_root_enrollments,company_private.installation_bootstrap_control,company_private.bootstrap_request_contexts TO company_context_owner;
GRANT INSERT ON company_private.installation_bootstrap_control,company_private.bootstrap_receipts TO company_context_owner;
GRANT UPDATE(state,consumed_command_id) ON company_private.installation_bootstrap_control TO company_context_owner;
GRANT UPDATE(revoked_at) ON company_private.r55_setup_root_enrollments TO company_context_owner;
CREATE POLICY r55_setup_enrollment_read ON company_private.r55_setup_root_enrollments FOR SELECT TO company_context_owner USING(session_user IN ('company_provisioning_runtime_r55','company_setup_runtime'));
CREATE POLICY r55_setup_enrollment_lock ON company_private.r55_setup_root_enrollments FOR UPDATE TO company_context_owner USING(session_user IN ('company_provisioning_runtime_r55','company_setup_runtime')) WITH CHECK(false);
CREATE POLICY r55_setup_control_insert ON company_private.installation_bootstrap_control FOR INSERT TO company_context_owner WITH CHECK(session_user='company_provisioning_runtime_r55');
CREATE POLICY r55_setup_receipt_insert ON company_private.bootstrap_receipts FOR INSERT TO company_context_owner WITH CHECK(session_user='company_setup_runtime');
ROLLBACK;
