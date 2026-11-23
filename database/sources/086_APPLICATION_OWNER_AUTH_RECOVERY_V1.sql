-- Inert owner authentication & recovery lifecycle source (v1); not an authorized migration.
-- Preserves existing tenant data without re-running disposable bootstrap or touching root expiry.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

DO $dependency$ BEGIN
 IF NOT EXISTS(
  SELECT 1 FROM pg_constraint c
  JOIN pg_class t ON t.oid=c.conrelid
  JOIN pg_namespace n ON n.oid=t.relnamespace
  WHERE n.nspname='company' AND t.relname='signer_enrollments' AND c.conname='r55_signer_purpose'
 )
 OR NOT EXISTS(
  SELECT 1 FROM pg_constraint c
  JOIN pg_class t ON t.oid=c.conrelid
  JOIN pg_namespace n ON n.oid=t.relnamespace
  WHERE n.nspname='company_private' AND t.relname='r58_key_material' AND c.conname='r58_key_material_purpose_check'
 )
 OR to_regprocedure('company_private.r55_cp_clock_current_bounds(uuid,uuid)') IS NULL
 OR to_regprocedure('company_private.r55_cp_hmac_sha256(bytea,bytea)') IS NULL
 OR to_regprocedure('company_private.r55_cp_tag_equal(bytea,bytea)') IS NULL
 THEN RAISE EXCEPTION 'OWNER_AUTH_V1_DEPENDENCY_MISSING';
 END IF;
END $dependency$;

ALTER TABLE company.signer_enrollments DROP CONSTRAINT r55_signer_purpose;
ALTER TABLE company.signer_enrollments ADD CONSTRAINT owner_auth_v1_signer_purpose
 CHECK(purpose IN ('TASK_VERIFICATION','EVALUATION','EGRESS_QUIESCENCE','CLOCK_OBSERVATION','OWNER_AUTH'));

ALTER TABLE company_private.r58_key_material DROP CONSTRAINT r58_key_material_purpose_check;
ALTER TABLE company_private.r58_key_material ADD CONSTRAINT owner_auth_v1_key_purpose
 CHECK(purpose IN ('EXECUTION_ATTESTATION','CLOCK_POLICY','OWNER_AUTH'));

-- Narrow least-privilege roles; no role memberships, logins, keys or enrollments created here.
CREATE ROLE company_owner_auth_owner_v1 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE company_owner_auth_readback_v1 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE company_owner_auth_transport_v1 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;

GRANT USAGE ON SCHEMA company,company_private TO company_owner_auth_owner_v1;
GRANT USAGE ON SCHEMA company,company_private TO company_owner_auth_readback_v1;
GRANT USAGE ON SCHEMA company_private TO company_owner_auth_transport_v1;

CREATE TABLE company_private.owner_auth_receipts_v1 (
 tenant_id uuid NOT NULL,
 auth_request_id uuid NOT NULL,
 installation_id uuid NOT NULL,
 project_id uuid NOT NULL,
 human_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN ('ISSUE_SESSION','REVOKE_SESSION','RECOVER_ROTATE_SESSIONS')),
 key_id uuid NOT NULL,
 enrollment_revision bigint NOT NULL CHECK(enrollment_revision>=0),
 statement_digest text NOT NULL CHECK(statement_digest ~ '^[a-f0-9]{64}$'),
 session_id uuid NOT NULL,
 token_hash text NOT NULL CHECK(token_hash ~ '^[a-f0-9]{64}$'),
 session_expires_at timestamptz NOT NULL CHECK(isfinite(session_expires_at)),
 revoked_session_count integer NOT NULL DEFAULT 0 CHECK(revoked_session_count>=0),
 clock_bounds jsonb NOT NULL CHECK(jsonb_typeof(clock_bounds)='object'),
 audit_id bigint NOT NULL,
 receipt_digest text NOT NULL CHECK(receipt_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(tenant_id,auth_request_id),
 FOREIGN KEY(installation_id) REFERENCES company_private.installation_bootstrap_control(installation_id),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,human_id) REFERENCES company.principals(tenant_id,id),
 FOREIGN KEY(tenant_id,session_id) REFERENCES company.sessions(tenant_id,id),
 FOREIGN KEY(audit_id) REFERENCES company.audit_events(id)
);

CREATE TRIGGER owner_auth_receipt_v1_immutable
 BEFORE UPDATE OR DELETE ON company_private.owner_auth_receipts_v1
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

ALTER TABLE company_private.owner_auth_receipts_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_private.owner_auth_receipts_v1 FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company_private.owner_auth_receipts_v1 FROM PUBLIC;

-- Scoped privileges for company_owner_auth_owner_v1; zero grants on project_grants, memberships or bootstrap_receipts writes.
GRANT SELECT ON company_private.installation_bootstrap_control,company_private.bootstrap_receipts,
 company_private.scope_lock_registry,company_private.r58_key_material,company_private.owner_auth_receipts_v1,
 company.principals,company.memberships,company.signer_enrollments,company.sessions,
 company.authority_scope_heads,company.audit_events TO company_owner_auth_owner_v1;
GRANT INSERT ON company_private.scope_lock_registry,company.sessions,company.authority_scope_heads,
 company.audit_events,company_private.owner_auth_receipts_v1 TO company_owner_auth_owner_v1;
GRANT UPDATE(revoked_at) ON company.sessions TO company_owner_auth_owner_v1;
GRANT UPDATE(epoch,revision) ON company.authority_scope_heads TO company_owner_auth_owner_v1;
-- Row lock support only; WITH CHECK(false) blocks mutations on enrollments and key material.
GRANT UPDATE(revoked_at) ON company.signer_enrollments TO company_owner_auth_owner_v1;
GRANT UPDATE(revoked) ON company_private.r58_key_material TO company_owner_auth_owner_v1;
GRANT USAGE ON SEQUENCE company_private.scope_lock_registry_lock_id_seq,company.audit_events_id_seq TO company_owner_auth_owner_v1;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_clock_current_bounds(uuid,uuid),
 company_private.r55_cp_hmac_sha256(bytea,bytea),
 company_private.r55_cp_tag_equal(bytea,bytea) TO company_owner_auth_owner_v1;

CREATE POLICY owner_auth_v1_control_read ON company_private.installation_bootstrap_control
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_boot_read ON company_private.bootstrap_receipts
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_principal_read ON company.principals
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND kind='HUMAN');
CREATE POLICY owner_auth_v1_membership_read ON company.memberships
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND role='OWNER');
CREATE POLICY owner_auth_v1_key_read ON company_private.r58_key_material
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND purpose='OWNER_AUTH' AND NOT revoked);
CREATE POLICY owner_auth_v1_key_lock ON company_private.r58_key_material
 FOR UPDATE TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND purpose='OWNER_AUTH')
 WITH CHECK(false);
CREATE POLICY owner_auth_v1_signer_read ON company.signer_enrollments
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND purpose='OWNER_AUTH');
CREATE POLICY owner_auth_v1_signer_lock ON company.signer_enrollments
 FOR UPDATE TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND purpose='OWNER_AUTH')
 WITH CHECK(false);
CREATE POLICY owner_auth_v1_lock_read ON company_private.scope_lock_registry
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_lock_insert ON company_private.scope_lock_registry
 FOR INSERT TO company_owner_auth_owner_v1
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND rank=2);
CREATE POLICY owner_auth_v1_session_read ON company.sessions
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_session_insert ON company.sessions
 FOR INSERT TO company_owner_auth_owner_v1
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_session_update ON company.sessions
 FOR UPDATE TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'))
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND revoked_at IS NOT NULL);
CREATE POLICY owner_auth_v1_head_read ON company.authority_scope_heads
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_head_insert ON company.authority_scope_heads
 FOR INSERT TO company_owner_auth_owner_v1
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND scope_kind='SESSION' AND epoch=0 AND revision=0);
CREATE POLICY owner_auth_v1_head_update ON company.authority_scope_heads
 FOR UPDATE TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND scope_kind='SESSION')
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND scope_kind='SESSION');
CREATE POLICY owner_auth_v1_audit_read ON company.audit_events
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_audit_insert ON company.audit_events
 FOR INSERT TO company_owner_auth_owner_v1
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER')
 AND kind IN ('OwnerSessionIssuedV1','OwnerSessionRevokedV1','OwnerSessionRecoveredV1'));
CREATE POLICY owner_auth_v1_receipt_read ON company_private.owner_auth_receipts_v1
 FOR SELECT TO company_owner_auth_owner_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_receipt_insert ON company_private.owner_auth_receipts_v1
 FOR INSERT TO company_owner_auth_owner_v1
 WITH CHECK(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));

-- Column-narrow SELECT privileges for company_owner_auth_readback_v1; zero DML.
GRANT SELECT(tenant_id,auth_request_id,installation_id,project_id,human_id,action,key_id,enrollment_revision,statement_digest,session_id,token_hash,session_expires_at,revoked_session_count,clock_bounds,audit_id,receipt_digest)
 ON company_private.owner_auth_receipts_v1 TO company_owner_auth_readback_v1;
GRANT SELECT(installation_id,generation,tenant_id,project_id,accepted_human_id)
 ON company_private.bootstrap_receipts TO company_owner_auth_readback_v1;
GRANT SELECT(installation_id,generation,state,expected_tenant_id,expected_project_id,expected_human_id)
 ON company_private.installation_bootstrap_control TO company_owner_auth_readback_v1;
GRANT SELECT(tenant_id,id,kind) ON company.principals TO company_owner_auth_readback_v1;
GRANT SELECT(tenant_id,principal_id,role) ON company.memberships TO company_owner_auth_readback_v1;
GRANT SELECT(tenant_id,id,principal_id,token_hash,expires_at,revoked_at) ON company.sessions TO company_owner_auth_readback_v1;
GRANT SELECT(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision) ON company.authority_scope_heads TO company_owner_auth_readback_v1;
GRANT SELECT(lock_id,rank,identity_key) ON company_private.scope_lock_registry TO company_owner_auth_readback_v1;
GRANT SELECT(tenant_id,id,actor_id,correlation_id,kind) ON company.audit_events TO company_owner_auth_readback_v1;

CREATE POLICY owner_auth_v1_rb_receipt ON company_private.owner_auth_receipts_v1
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_rb_boot ON company_private.bootstrap_receipts
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_rb_ctl ON company_private.installation_bootstrap_control
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_rb_principal ON company.principals
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND kind='HUMAN');
CREATE POLICY owner_auth_v1_rb_membership ON company.memberships
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND role='OWNER');
CREATE POLICY owner_auth_v1_rb_session ON company.sessions
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_rb_head ON company.authority_scope_heads
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER') AND scope_kind='SESSION');
CREATE POLICY owner_auth_v1_rb_lock ON company_private.scope_lock_registry
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));
CREATE POLICY owner_auth_v1_rb_audit ON company.audit_events
 FOR SELECT TO company_owner_auth_readback_v1
 USING(pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER'));

CREATE FUNCTION company_private.owner_auth_execute_v1(
 p_installation uuid,p_auth_request uuid,p_key_id uuid,p_enrollment_revision bigint,p_raw bytea,p_tag bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
 v_j jsonb;
 v_stmt jsonb;
 v_params jsonb;
 v_tenant uuid;
 v_project uuid;
 v_human uuid;
 v_action text;
 v_token_hash text;
 v_ttl integer;
 v_target_session uuid;
 v_ctl company_private.installation_bootstrap_control%ROWTYPE;
 v_boot company_private.bootstrap_receipts%ROWTYPE;
 v_key company_private.r58_key_material%ROWTYPE;
 v_enroll company.signer_enrollments%ROWTYPE;
 v_existing company_private.owner_auth_receipts_v1%ROWTYPE;
 v_target_sess company.sessions%ROWTYPE;
 v_rec record;
 v_lock_count integer:=0;
 v_expected_lock jsonb;
 v_msg bytea;
 v_item bytea;
 v_bounds jsonb;
 v_lo timestamptz;
 v_hi timestamptz;
 v_stmt_digest text;
 v_session_id uuid;
 v_session_expires timestamptz;
 v_new_lock_id bigint;
 v_revoked_count integer:=0;
 v_bumped_count integer:=0;
 v_audit_kind text;
 v_aid bigint;
 v_receipt_digest text;
 v_outcome text;
BEGIN
 IF NOT pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER')
 OR NOT EXISTS(
  SELECT 1 FROM pg_catalog.pg_roles r
  WHERE r.rolname=session_user AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreaterole
 ) THEN
  RAISE EXCEPTION 'OWNER_AUTH_TRANSPORT_REQUIRED';
 END IF;
 IF num_nulls(p_installation,p_auth_request,p_key_id,p_enrollment_revision,p_raw,p_tag)<>0
 OR p_enrollment_revision<0
 OR octet_length(p_raw) NOT BETWEEN 1 AND 65536
 OR octet_length(p_tag)<>32 THEN
  RAISE EXCEPTION 'INVALID_OWNER_AUTH_WIRE';
 END IF;
 v_j=convert_from(p_raw,'UTF8')::jsonb;
 IF jsonb_typeof(v_j) IS DISTINCT FROM 'object'
 OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1) THEN
  RAISE EXCEPTION 'AMBIGUOUS_OWNER_AUTH_JSON';
 END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(v_j))<>5
 OR NOT ((v_j ?& ARRAY['profile','backend_pid','transaction_id','db_login','statement']) IS TRUE)
 OR jsonb_typeof(v_j->'profile') IS DISTINCT FROM 'string'
 OR jsonb_typeof(v_j->'backend_pid') IS DISTINCT FROM 'number'
 OR v_j->>'backend_pid' !~ '^[1-9][0-9]*$'
 OR jsonb_typeof(v_j->'transaction_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(v_j->'db_login') IS DISTINCT FROM 'string'
 OR jsonb_typeof(v_j->'statement') IS DISTINCT FROM 'object'
 OR v_j->>'profile' IS DISTINCT FROM 'application.owner-auth.v1'
 OR v_j->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text
 OR v_j->>'transaction_id' IS DISTINCT FROM pg_current_xact_id()::text
 OR v_j->>'db_login' IS DISTINCT FROM session_user::text THEN
  RAISE EXCEPTION 'OWNER_AUTH_CONTEXT_MISMATCH';
 END IF;
 v_stmt=v_j->'statement';
 IF (SELECT count(*) FROM jsonb_object_keys(v_stmt))<>7
 OR NOT ((v_stmt ?& ARRAY['auth_request_id','installation_id','tenant_id','project_id','human_id','action','params']) IS TRUE)
 OR EXISTS(
  SELECT 1 FROM jsonb_each(v_stmt) z
  WHERE z.key IN ('auth_request_id','installation_id','tenant_id','project_id','human_id','action')
  AND jsonb_typeof(z.value) IS DISTINCT FROM 'string'
 )
 OR jsonb_typeof(v_stmt->'params') IS DISTINCT FROM 'object'
 OR v_stmt->>'auth_request_id' IS DISTINCT FROM p_auth_request::text
 OR v_stmt->>'installation_id' IS DISTINCT FROM p_installation::text
 OR v_stmt->>'action' NOT IN ('ISSUE_SESSION','REVOKE_SESSION','RECOVER_ROTATE_SESSIONS') THEN
  RAISE EXCEPTION 'OWNER_AUTH_STATEMENT_SHAPE';
 END IF;
 IF v_stmt->>'tenant_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
 OR v_stmt->>'project_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
 OR v_stmt->>'human_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
  RAISE EXCEPTION 'OWNER_AUTH_STATEMENT_SHAPE';
 END IF;
 v_tenant=(v_stmt->>'tenant_id')::uuid;
 v_project=(v_stmt->>'project_id')::uuid;
 v_human=(v_stmt->>'human_id')::uuid;
 v_action=v_stmt->>'action';
 v_params=v_stmt->'params';
 IF v_tenant::text IS DISTINCT FROM v_stmt->>'tenant_id'
 OR v_project::text IS DISTINCT FROM v_stmt->>'project_id'
 OR v_human::text IS DISTINCT FROM v_stmt->>'human_id' THEN
  RAISE EXCEPTION 'OWNER_AUTH_STATEMENT_SHAPE';
 END IF;
 IF v_action IN ('ISSUE_SESSION','RECOVER_ROTATE_SESSIONS') THEN
  IF (SELECT count(*) FROM jsonb_object_keys(v_params))<>2
  OR NOT ((v_params ?& ARRAY['token_hash','ttl_seconds']) IS TRUE)
  OR jsonb_typeof(v_params->'token_hash') IS DISTINCT FROM 'string'
  OR v_params->>'token_hash' !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(v_params->'ttl_seconds') IS DISTINCT FROM 'number'
  OR v_params->>'ttl_seconds' !~ '^[1-9][0-9]*$' THEN
   RAISE EXCEPTION 'OWNER_AUTH_PARAMS_INVALID';
  END IF;
  v_ttl=(v_params->>'ttl_seconds')::integer;
  IF v_ttl<1 OR v_ttl>900 THEN
   RAISE EXCEPTION 'OWNER_AUTH_PARAMS_INVALID';
  END IF;
  v_token_hash=v_params->>'token_hash';
 ELSE
  IF (SELECT count(*) FROM jsonb_object_keys(v_params))<>1
  OR NOT (v_params ? 'target_session_id')
  OR jsonb_typeof(v_params->'target_session_id') IS DISTINCT FROM 'string'
  OR v_params->>'target_session_id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
   RAISE EXCEPTION 'OWNER_AUTH_PARAMS_INVALID';
  END IF;
  v_target_session=(v_params->>'target_session_id')::uuid;
  IF v_target_session::text IS DISTINCT FROM v_params->>'target_session_id' THEN
   RAISE EXCEPTION 'OWNER_AUTH_PARAMS_INVALID';
  END IF;
 END IF;
 v_stmt_digest=encode(sha256(convert_to(v_stmt::text,'UTF8')),'hex');

 SELECT * INTO v_ctl FROM company_private.installation_bootstrap_control
 WHERE installation_id=p_installation;
 IF NOT FOUND OR v_ctl.state IS DISTINCT FROM 'CONSUMED' THEN
  RAISE EXCEPTION 'OWNER_AUTH_INSTALLATION_NOT_CONSUMED';
 END IF;
 SELECT * INTO v_boot FROM company_private.bootstrap_receipts
 WHERE installation_id=v_ctl.installation_id AND generation=v_ctl.generation;
 IF NOT FOUND
 OR v_boot.tenant_id IS DISTINCT FROM v_tenant
 OR v_boot.project_id IS DISTINCT FROM v_project
 OR v_boot.accepted_human_id IS DISTINCT FROM v_human THEN
  RAISE EXCEPTION 'OWNER_AUTH_INSTALLATION_MISMATCH';
 END IF;
 PERFORM 1 FROM company.principals p
 JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id
 WHERE p.tenant_id=v_tenant AND p.id=v_human AND p.kind='HUMAN' AND m.role='OWNER';
 IF NOT FOUND THEN
  RAISE EXCEPTION 'OWNER_AUTH_HUMAN_OWNER_REQUIRED';
 END IF;

 -- Deadlock-free advisory lock acquisition: TENANT (rank 0) -> PROJECT (rank 1) -> SESSION (rank 2).
 FOR v_rec IN
  SELECT l.lock_id,l.rank,l.identity_key
  FROM company.authority_scope_heads h
  JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
  WHERE h.tenant_id=v_tenant
  AND ((h.scope_kind='TENANT' AND h.scope_ref=v_tenant)
   OR (h.scope_kind='PROJECT' AND h.scope_ref=v_project))
  ORDER BY l.rank,l.lock_id
 LOOP
  v_expected_lock=CASE
   WHEN v_lock_count=0 THEN jsonb_build_object('kind','TENANT','tenant_id',v_tenant)
   ELSE jsonb_build_object('kind','PROJECT','tenant_id',v_tenant,'project_id',v_project)
  END;
  IF v_rec.rank IS DISTINCT FROM v_lock_count OR v_rec.identity_key IS DISTINCT FROM v_expected_lock THEN
   RAISE EXCEPTION 'EXACT_OWNER_AUTH_LOCK_IDENTITY_REQUIRED';
  END IF;
  PERFORM pg_advisory_xact_lock(v_rec.lock_id);
  v_lock_count=v_lock_count+1;
 END LOOP;
 IF v_lock_count<>2 THEN
  RAISE EXCEPTION 'EXACT_OWNER_AUTH_LOCK_IDENTITY_REQUIRED';
 END IF;

 IF v_action='REVOKE_SESSION' THEN
  SELECT l.lock_id,l.rank,l.identity_key INTO v_rec
  FROM company.authority_scope_heads h
  JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
  WHERE h.tenant_id=v_tenant AND h.scope_kind='SESSION' AND h.scope_ref=v_target_session AND h.session_id=v_target_session;
  IF NOT FOUND THEN
   RAISE EXCEPTION 'OWNER_SESSION_NOT_FOUND';
  END IF;
  IF v_rec.rank IS DISTINCT FROM 2
  OR v_rec.identity_key IS DISTINCT FROM jsonb_build_object('kind','SESSION','tenant_id',v_tenant,'session_id',v_target_session) THEN
   RAISE EXCEPTION 'EXACT_OWNER_AUTH_LOCK_IDENTITY_REQUIRED';
  END IF;
  PERFORM pg_advisory_xact_lock(v_rec.lock_id);
 ELSIF v_action='RECOVER_ROTATE_SESSIONS' THEN
  FOR v_rec IN
   SELECT l.lock_id,l.rank,l.identity_key,s.id AS sid
   FROM company.sessions s
   JOIN company.authority_scope_heads h
    ON h.tenant_id=s.tenant_id AND h.scope_kind='SESSION' AND h.scope_ref=s.id AND h.session_id=s.id
   JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
   WHERE s.tenant_id=v_tenant AND s.principal_id=v_human AND s.revoked_at IS NULL
   ORDER BY l.lock_id
  LOOP
   IF v_rec.rank IS DISTINCT FROM 2
   OR v_rec.identity_key IS DISTINCT FROM jsonb_build_object('kind','SESSION','tenant_id',v_tenant,'session_id',v_rec.sid) THEN
    RAISE EXCEPTION 'EXACT_OWNER_AUTH_LOCK_IDENTITY_REQUIRED';
   END IF;
   PERFORM pg_advisory_xact_lock(v_rec.lock_id);
  END LOOP;
 END IF;

 SELECT * INTO v_key FROM company_private.r58_key_material
 WHERE key_id=p_key_id AND purpose='OWNER_AUTH' AND NOT revoked FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'OWNER_AUTH_KEY_OR_ENROLLMENT_INVALID';
 END IF;
 SELECT * INTO v_enroll FROM company.signer_enrollments
 WHERE tenant_id=v_tenant AND issuer_id=v_human AND key_id=p_key_id
 AND purpose='OWNER_AUTH' AND enrollment_revision=p_enrollment_revision FOR SHARE;
 IF NOT FOUND
 OR v_enroll.profile_id IS DISTINCT FROM 'APPLICATION_OWNER_AUTH_V1_RAW_JSON'
 OR v_enroll.revoked_at IS NOT NULL
 OR v_enroll.compromised_since IS NOT NULL
 OR v_enroll.approved_by IS DISTINCT FROM v_human
 OR v_enroll.r55_project_id IS DISTINCT FROM v_project
 OR v_enroll.key_fingerprint IS DISTINCT FROM encode(sha256(v_key.secret),'hex')
 OR NOT isfinite(v_enroll.valid_from)
 OR NOT isfinite(v_enroll.valid_until) THEN
  RAISE EXCEPTION 'OWNER_AUTH_KEY_OR_ENROLLMENT_INVALID';
 END IF;

 v_msg=convert_to('APP-OWNER-AUTH-v1','UTF8')||decode('00','hex');
 FOREACH v_item IN ARRAY ARRAY[
  convert_to(p_auth_request::text,'UTF8'),
  convert_to(v_tenant::text,'UTF8'),
  convert_to(v_project::text,'UTF8'),
  convert_to(v_human::text,'UTF8'),
  convert_to(p_key_id::text,'UTF8'),
  convert_to(p_enrollment_revision::text,'UTF8'),
  p_raw
 ] LOOP
  v_msg=v_msg||convert_to(octet_length(v_item)::text||':','UTF8')||v_item;
 END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(v_key.secret,v_msg),p_tag) IS NOT TRUE THEN
  RAISE EXCEPTION 'INVALID_OWNER_AUTH_HMAC';
 END IF;

 -- Live trusted project clock evaluated AFTER acquiring authority locks; never wall clock.
 v_bounds=company_private.r55_cp_clock_current_bounds(v_tenant,v_project);
 v_lo=(v_bounds->>'utc_lower_bound')::timestamptz;
 v_hi=(v_bounds->>'utc_upper_bound')::timestamptz;
 IF NOT ((isfinite(v_lo) AND isfinite(v_hi) AND v_lo<=v_hi
          AND v_enroll.valid_from<=v_lo AND v_hi<v_enroll.valid_until) IS TRUE) THEN
  RAISE EXCEPTION 'OWNER_AUTH_ENROLLMENT_EXPIRED_OR_AMBIGUOUS';
 END IF;

 SELECT * INTO v_existing FROM company_private.owner_auth_receipts_v1
 WHERE tenant_id=v_tenant AND auth_request_id=p_auth_request;
 IF FOUND THEN
  IF v_existing.action IS DISTINCT FROM v_action
  OR v_existing.statement_digest IS DISTINCT FROM v_stmt_digest
  OR v_existing.installation_id IS DISTINCT FROM p_installation
  OR v_existing.project_id IS DISTINCT FROM v_project
  OR v_existing.human_id IS DISTINCT FROM v_human THEN
   RAISE EXCEPTION 'OWNER_AUTH_REQUEST_CONFLICT';
  END IF;
  RETURN jsonb_build_object(
   'auth_request_id',v_existing.auth_request_id,
   'installation_id',v_existing.installation_id,
   'tenant_id',v_existing.tenant_id,
   'project_id',v_existing.project_id,
   'principal_id',v_existing.human_id,
   'action',v_existing.action,
   'session_id',v_existing.session_id,
   'token_hash',v_existing.token_hash,
   'expires_at',v_existing.session_expires_at,
   'revoked_session_count',v_existing.revoked_session_count,
   'receipt_digest',v_existing.receipt_digest,
   'audit_id',v_existing.audit_id,
   'outcome','REPLAY_ALREADY_RECORDED',
   'new_grants',0,
   'new_memberships',0,
   'authorization','SESSION_LIFECYCLE_ONLY_NOT_WORKFLOW_ACCEPTANCE'
  );
 END IF;

 IF v_action='REVOKE_SESSION' THEN
  SELECT * INTO v_target_sess FROM company.sessions
  WHERE tenant_id=v_tenant AND id=v_target_session AND principal_id=v_human FOR UPDATE;
  IF NOT FOUND THEN
   RAISE EXCEPTION 'OWNER_SESSION_NOT_FOUND';
  END IF;
  IF v_target_sess.revoked_at IS NOT NULL THEN
   RAISE EXCEPTION 'OWNER_SESSION_ALREADY_REVOKED';
  END IF;
  UPDATE company.sessions SET revoked_at=v_hi
  WHERE tenant_id=v_tenant AND id=v_target_session AND revoked_at IS NULL;
  IF NOT FOUND THEN
   RAISE EXCEPTION 'OWNER_SESSION_ALREADY_REVOKED';
  END IF;
  UPDATE company.authority_scope_heads SET epoch=epoch+1,revision=revision+1
  WHERE tenant_id=v_tenant AND scope_kind='SESSION' AND scope_ref=v_target_session AND session_id=v_target_session;
  IF NOT FOUND THEN
   RAISE EXCEPTION 'OWNER_SESSION_HEAD_MISSING';
  END IF;
  v_session_id=v_target_sess.id;
  v_token_hash=v_target_sess.token_hash;
  v_session_expires=v_target_sess.expires_at;
  v_revoked_count=1;
  v_audit_kind='OwnerSessionRevokedV1';
  v_outcome='REVOKED';
 ELSE
  v_session_expires=least(v_enroll.valid_until,v_lo+v_ttl*interval '1 second');
  IF v_session_expires<=v_hi THEN
   RAISE EXCEPTION 'UNAMBIGUOUS_SESSION_EXPIRY_REQUIRED';
  END IF;
  IF v_action='RECOVER_ROTATE_SESSIONS' THEN
   WITH revoked AS (
    UPDATE company.sessions SET revoked_at=v_hi
    WHERE tenant_id=v_tenant AND principal_id=v_human AND revoked_at IS NULL
    RETURNING id
   ),
   bumped AS (
    UPDATE company.authority_scope_heads h SET epoch=h.epoch+1,revision=h.revision+1
    FROM revoked r
    WHERE h.tenant_id=v_tenant AND h.scope_kind='SESSION' AND h.scope_ref=r.id AND h.session_id=r.id
    RETURNING h.session_id
   )
   SELECT (SELECT count(*) FROM revoked),(SELECT count(*) FROM bumped) INTO v_revoked_count,v_bumped_count;
   IF v_revoked_count IS DISTINCT FROM v_bumped_count THEN
    RAISE EXCEPTION 'OWNER_SESSION_HEAD_MISSING';
   END IF;
   v_audit_kind='OwnerSessionRecoveredV1';
   v_outcome='RECOVERED_ROTATED';
  ELSE
   v_revoked_count=0;
   v_audit_kind='OwnerSessionIssuedV1';
   v_outcome='ISSUED';
  END IF;
  v_session_id=gen_random_uuid();
  INSERT INTO company_private.scope_lock_registry(rank,identity_key)
  VALUES(2,jsonb_build_object('kind','SESSION','tenant_id',v_tenant,'session_id',v_session_id))
  RETURNING lock_id INTO v_new_lock_id;
  INSERT INTO company.sessions(tenant_id,id,principal_id,token_hash,expires_at)
  VALUES(v_tenant,v_session_id,v_human,v_token_hash,v_session_expires);
  INSERT INTO company.authority_scope_heads(tenant_id,scope_kind,scope_ref,session_id,epoch,lock_id,revision)
  VALUES(v_tenant,'SESSION',v_session_id,v_session_id,0,v_new_lock_id,0);
 END IF;

 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind)
 VALUES(v_tenant,p_auth_request,v_human,v_audit_kind)
 RETURNING id INTO v_aid;

 v_receipt_digest=encode(sha256(convert_to(jsonb_build_array(
  v_tenant,p_auth_request,p_installation,v_project,v_human,v_action,p_key_id,p_enrollment_revision,
  v_stmt_digest,v_session_id,v_token_hash,v_session_expires,v_revoked_count,v_bounds,v_aid
 )::text,'UTF8')),'hex');

 INSERT INTO company_private.owner_auth_receipts_v1(
  tenant_id,auth_request_id,installation_id,project_id,human_id,action,key_id,enrollment_revision,
  statement_digest,session_id,token_hash,session_expires_at,revoked_session_count,clock_bounds,audit_id,receipt_digest
 ) VALUES(
  v_tenant,p_auth_request,p_installation,v_project,v_human,v_action,p_key_id,p_enrollment_revision,
  v_stmt_digest,v_session_id,v_token_hash,v_session_expires,v_revoked_count,v_bounds,v_aid,v_receipt_digest
 );

 RETURN jsonb_build_object(
  'auth_request_id',p_auth_request,
  'installation_id',p_installation,
  'tenant_id',v_tenant,
  'project_id',v_project,
  'principal_id',v_human,
  'action',v_action,
  'session_id',v_session_id,
  'token_hash',v_token_hash,
  'expires_at',v_session_expires,
  'revoked_session_count',v_revoked_count,
  'receipt_digest',v_receipt_digest,
  'audit_id',v_aid,
  'outcome',v_outcome,
  'new_grants',0,
  'new_memberships',0,
  'authorization','SESSION_LIFECYCLE_ONLY_NOT_WORKFLOW_ACCEPTANCE'
 );
END $$;
ALTER FUNCTION company_private.owner_auth_execute_v1(uuid,uuid,uuid,bigint,bytea,bytea)
 OWNER TO company_owner_auth_owner_v1;
REVOKE ALL ON FUNCTION company_private.owner_auth_execute_v1(uuid,uuid,uuid,bigint,bytea,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.owner_auth_execute_v1(uuid,uuid,uuid,bigint,bytea,bytea)
 TO company_owner_auth_transport_v1;

CREATE FUNCTION company_private.owner_auth_receipt_readback_v1(
 p_tenant uuid,p_auth_request uuid,p_installation uuid,p_project uuid,
 p_human uuid,p_action text,p_session uuid,p_token_hash text,p_receipt_digest text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
 v_matches integer;
 v_expires timestamptz;
 v_revoked_count integer;
 v_audit_id bigint;
BEGIN
 IF NOT pg_has_role(session_user,'company_owner_auth_transport_v1','MEMBER')
 OR NOT EXISTS(
  SELECT 1 FROM pg_catalog.pg_roles r
  WHERE r.rolname=session_user AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreaterole
 ) THEN
  RAISE EXCEPTION 'OWNER_AUTH_TRANSPORT_REQUIRED';
 END IF;
 IF num_nulls(p_tenant,p_auth_request,p_installation,p_project,p_human,p_action,p_session,p_token_hash,p_receipt_digest)<>0
 OR p_action NOT IN ('ISSUE_SESSION','REVOKE_SESSION','RECOVER_ROTATE_SESSIONS')
 OR p_token_hash !~ '^[a-f0-9]{64}$'
 OR p_receipt_digest !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'EXACT_OWNER_AUTH_READBACK_INPUT_REQUIRED';
 END IF;

 SELECT count(*),min(witnesses.session_expires_at),min(witnesses.revoked_session_count),min(witnesses.audit_id)
 INTO v_matches,v_expires,v_revoked_count,v_audit_id
 FROM (
  SELECT r.session_expires_at,r.revoked_session_count,r.audit_id
  FROM company_private.owner_auth_receipts_v1 r
  JOIN company_private.installation_bootstrap_control ctl ON ctl.installation_id=r.installation_id
  JOIN company_private.bootstrap_receipts b ON b.installation_id=ctl.installation_id AND b.generation=ctl.generation
  JOIN company.principals p ON p.tenant_id=r.tenant_id AND p.id=r.human_id
  JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id
  JOIN company.sessions s ON s.tenant_id=r.tenant_id AND s.id=r.session_id
  JOIN company.authority_scope_heads h ON h.tenant_id=s.tenant_id AND h.scope_kind='SESSION' AND h.scope_ref=s.id AND h.session_id=s.id
  JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id
  JOIN company.audit_events a ON a.tenant_id=r.tenant_id AND a.id=r.audit_id
  WHERE r.tenant_id=p_tenant AND r.auth_request_id=p_auth_request
  AND r.installation_id=p_installation AND r.project_id=p_project AND r.human_id=p_human
  AND r.action=p_action AND r.session_id=p_session
  AND r.token_hash=p_token_hash AND r.receipt_digest=p_receipt_digest
  AND ctl.state='CONSUMED'
  AND b.tenant_id=r.tenant_id AND b.project_id=r.project_id AND b.accepted_human_id=r.human_id
  AND p.kind='HUMAN' AND m.role='OWNER'
  AND s.principal_id=r.human_id AND s.token_hash=r.token_hash AND s.expires_at=r.session_expires_at
  AND (
   (r.action IN ('ISSUE_SESSION','RECOVER_ROTATE_SESSIONS') AND s.revoked_at IS NULL AND h.epoch=0 AND h.revision=0)
   OR (r.action='REVOKE_SESSION' AND s.revoked_at IS NOT NULL AND h.epoch>=1 AND h.revision>=1)
  )
  AND l.rank=2 AND l.identity_key=jsonb_build_object('kind','SESSION','tenant_id',r.tenant_id,'session_id',r.session_id)
  AND a.actor_id=r.human_id AND a.correlation_id=r.auth_request_id
  AND a.kind=CASE r.action
   WHEN 'ISSUE_SESSION' THEN 'OwnerSessionIssuedV1'
   WHEN 'REVOKE_SESSION' THEN 'OwnerSessionRevokedV1'
   ELSE 'OwnerSessionRecoveredV1'
  END
  AND r.receipt_digest=encode(sha256(convert_to(jsonb_build_array(
   r.tenant_id,r.auth_request_id,r.installation_id,r.project_id,r.human_id,r.action,r.key_id,
   r.enrollment_revision,r.statement_digest,r.session_id,r.token_hash,r.session_expires_at,
   r.revoked_session_count,r.clock_bounds,r.audit_id
  )::text,'UTF8')),'hex')
  LIMIT 2
 ) AS witnesses(session_expires_at,revoked_session_count,audit_id);

 IF v_matches<>1 THEN
  RAISE EXCEPTION 'OWNER_AUTH_READBACK_WITNESS_MISMATCH';
 END IF;

 RETURN jsonb_build_object(
  'tenant_id',p_tenant,
  'auth_request_id',p_auth_request,
  'installation_id',p_installation,
  'project_id',p_project,
  'human_id',p_human,
  'action',p_action,
  'session_id',p_session,
  'token_hash',p_token_hash,
  'expires_at',v_expires,
  'revoked_session_count',v_revoked_count,
  'audit_id',v_audit_id,
  'receipt_digest',p_receipt_digest,
  'readback','EXACT_COMMITTED_WITNESS_MATCH',
  'authorization','SESSION_RECORD_READBACK_NOT_WORKFLOW_ACCEPTANCE',
  'new_grants',0,
  'new_memberships',0
 );
END $$;
ALTER FUNCTION company_private.owner_auth_receipt_readback_v1(uuid,uuid,uuid,uuid,uuid,text,uuid,text,text)
 OWNER TO company_owner_auth_readback_v1;
REVOKE ALL ON FUNCTION company_private.owner_auth_receipt_readback_v1(uuid,uuid,uuid,uuid,uuid,text,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.owner_auth_receipt_readback_v1(uuid,uuid,uuid,uuid,uuid,text,uuid,text,text)
 TO company_owner_auth_transport_v1;

ROLLBACK;
