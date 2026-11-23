-- Source candidate AFTER r56; no policy values, login or enrollment installed.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE ROLE company_clock_policy_owner_r57 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE ROLE company_clock_policy_transport_r57 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company,company_private TO company_clock_policy_owner_r57;
GRANT USAGE ON SCHEMA company_private TO company_clock_policy_transport_r57;

-- operation_permissions is installation-global in the existing ABI. Exactly
-- one enrolled installation owns this head. Multi-installation use is denied.
CREATE TABLE company_private.r57_clock_policy_authority (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 installation_id uuid NOT NULL UNIQUE REFERENCES company_private.installation_bootstrap_control(installation_id),
 tenant_id uuid NOT NULL,
 human_id uuid NOT NULL,
 FOREIGN KEY(tenant_id,human_id) REFERENCES company.principals(tenant_id,id)
);
CREATE TABLE company_private.r57_clock_policy_consents (
 consent_id uuid PRIMARY KEY,
 installation_id uuid NOT NULL REFERENCES company_private.r57_clock_policy_authority(installation_id),
 root_generation bigint NOT NULL CHECK(root_generation>0),
 action text NOT NULL CHECK(action IN ('ACTIVATE','REVOKE')),
 expected_revision bigint NOT NULL CHECK(expected_revision>=0),
 approved_statement_digest text NOT NULL CHECK(approved_statement_digest ~ '^[a-f0-9]{64}$'),
 human_consent_evidence_digest text NOT NULL CHECK(human_consent_evidence_digest ~ '^[a-f0-9]{64}$'),
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)),
 valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 revoked_at timestamptz,
 CHECK(valid_from<valid_until)
);
CREATE TABLE company_private.r57_clock_policy_receipts (
 consent_id uuid PRIMARY KEY REFERENCES company_private.r57_clock_policy_consents(consent_id),
 installation_id uuid NOT NULL,
 tenant_id uuid NOT NULL,
 human_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0),
 action text NOT NULL CHECK(action IN ('ACTIVATE','REVOKE')),
 statement_digest text NOT NULL CHECK(statement_digest ~ '^[a-f0-9]{64}$'),
 policy_digest text CHECK(policy_digest ~ '^[a-f0-9]{64}$'),
 policy jsonb,
 final_proof jsonb NOT NULL,
 receipt_digest text NOT NULL CHECK(receipt_digest ~ '^[a-f0-9]{64}$'),
 audit_id bigint NOT NULL,
 UNIQUE(installation_id,revision),
 FOREIGN KEY(tenant_id,human_id) REFERENCES company.principals(tenant_id,id),
 FOREIGN KEY(audit_id) REFERENCES company.audit_events(id),
 CHECK((action='REVOKE' AND policy_digest IS NULL AND policy IS NULL)
 OR ((action='ACTIVATE' AND policy_digest IS NOT NULL AND jsonb_typeof(policy)='object') IS TRUE))
);
CREATE TRIGGER r57_clock_receipt_immutable BEFORE UPDATE OR DELETE ON company_private.r57_clock_policy_receipts
FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();
CREATE TRIGGER r57_clock_authority_immutable BEFORE UPDATE OR DELETE ON company_private.r57_clock_policy_authority
FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();
-- Authority/consent insertion and revocation are offline trusted provisioning
-- seams. Runtime owner cannot INSERT, UPDATE or DELETE them. No enrollment is
-- fabricated by a runtime call or by executing this design file.
DO $rls$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['r57_clock_policy_authority','r57_clock_policy_consents','r57_clock_policy_receipts'] LOOP
  EXECUTE format('ALTER TABLE company_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE company_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON company_private.%I FROM PUBLIC',t);
  EXECUTE format('CREATE POLICY r57_clock_read ON company_private.%I FOR SELECT TO company_clock_policy_owner_r57 USING(true)',t);
 END LOOP;
END $rls$;
GRANT SELECT ON company_private.r57_clock_policy_authority,company_private.r57_clock_policy_consents,
 company_private.r57_clock_policy_receipts,company_private.installation_bootstrap_control,
 company_private.r55_setup_root_enrollments,company_private.operation_permissions,
 company.principals TO company_clock_policy_owner_r57;
GRANT UPDATE(revoked_at) ON company_private.r57_clock_policy_consents TO company_clock_policy_owner_r57;
CREATE POLICY r57_consent_lock ON company_private.r57_clock_policy_consents FOR UPDATE TO company_clock_policy_owner_r57 USING(true) WITH CHECK(false);
GRANT UPDATE(revoked_at) ON company_private.r55_setup_root_enrollments TO company_clock_policy_owner_r57;
CREATE POLICY r57_clock_root_lock ON company_private.r55_setup_root_enrollments FOR UPDATE TO company_clock_policy_owner_r57 USING(true) WITH CHECK(false);
-- UPDATE privilege only permits row locks; WITH CHECK(false) forbids changes.
GRANT INSERT ON company_private.r57_clock_policy_receipts TO company_clock_policy_owner_r57;
GRANT SELECT,UPDATE(invalidated_at) ON company.clock_epochs TO company_clock_policy_owner_r57;
CREATE POLICY r57_clock_epoch_policy ON company.clock_epochs TO company_clock_policy_owner_r57
 USING(EXISTS(SELECT 1 FROM company_private.r57_clock_policy_authority a WHERE a.tenant_id=clock_epochs.tenant_id))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.r57_clock_policy_authority a WHERE a.tenant_id=clock_epochs.tenant_id) AND invalidated_at IS NOT NULL);
CREATE POLICY r57_clock_insert ON company_private.r57_clock_policy_receipts FOR INSERT TO company_clock_policy_owner_r57 WITH CHECK(true);
GRANT UPDATE(policy_revision,approved_policy_digest) ON company_private.operation_permissions TO company_clock_policy_owner_r57;
CREATE POLICY r57_clock_registry ON company_private.operation_permissions TO company_clock_policy_owner_r57
 USING(operation_id='clock.policy.activate') WITH CHECK(operation_id='clock.policy.activate');
CREATE POLICY r57_clock_control ON company_private.installation_bootstrap_control FOR SELECT TO company_clock_policy_owner_r57 USING(true);
CREATE POLICY r57_clock_root ON company_private.r55_setup_root_enrollments FOR SELECT TO company_clock_policy_owner_r57 USING(true);
CREATE POLICY r57_clock_human ON company.principals FOR SELECT TO company_clock_policy_owner_r57 USING(kind='HUMAN');
GRANT SELECT,INSERT ON company.audit_events TO company_clock_policy_owner_r57;
GRANT USAGE ON SEQUENCE company.audit_events_id_seq TO company_clock_policy_owner_r57;
CREATE POLICY r57_clock_audit ON company.audit_events TO company_clock_policy_owner_r57
 USING(EXISTS(SELECT 1 FROM company_private.r57_clock_policy_authority a WHERE a.tenant_id=audit_events.tenant_id AND a.human_id=audit_events.actor_id))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.r57_clock_policy_authority a WHERE a.tenant_id=audit_events.tenant_id AND a.human_id=audit_events.actor_id));
GRANT EXECUTE ON FUNCTION company_private.r56_root_bounds(uuid),company_private.r55_cp_hmac_sha256(bytea,bytea),
 company_private.r55_cp_tag_equal(bytea,bytea) TO company_clock_policy_owner_r57;

CREATE FUNCTION company_private.r57_clock_policy_write(p_consent uuid,p_raw bytea,p_tag bytea,p_key bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a company_private.r57_clock_policy_authority%ROWTYPE;
 c company_private.r57_clock_policy_consents%ROWTYPE;e company_private.r55_setup_root_enrollments%ROWTYPE;
 ctl company_private.installation_bootstrap_control%ROWTYPE;r company_private.r57_clock_policy_receipts%ROWTYPE;
 op company_private.operation_permissions%ROWTYPE;j jsonb;s jsonb;v jsonb;bounds jsonb;d text;pd text;rd text;aid bigint;
 msg bytea;item bytea;policy_key text;revision bigint;
BEGIN
 IF NOT pg_has_role(session_user,'company_clock_policy_transport_r57','MEMBER') THEN RAISE EXCEPTION 'CLOCK_POLICY_TRANSPORT_REQUIRED'; END IF;
 IF p_consent IS NULL OR p_raw IS NULL OR octet_length(p_raw) NOT BETWEEN 1 AND 65536
 OR p_tag IS NULL OR octet_length(p_tag)<>32 OR p_key IS NULL OR octet_length(p_key)<>32 THEN RAISE EXCEPTION 'INVALID_CLOCK_POLICY_WIRE'; END IF;
 SELECT * INTO STRICT a FROM company_private.r57_clock_policy_authority WHERE singleton;
 SELECT * INTO STRICT ctl FROM company_private.installation_bootstrap_control WHERE installation_id=a.installation_id;
 -- Same installation lock as bootstrap. All policy writers take this first,
 -- then consent, then registry. Root rows stay SHARE-locked through COMMIT.
 PERFORM pg_advisory_xact_lock(ctl.lock_id);
 SELECT * INTO STRICT c FROM company_private.r57_clock_policy_consents WHERE consent_id=p_consent FOR SHARE;
 SELECT * INTO STRICT e FROM company_private.r55_setup_root_enrollments WHERE installation_id=a.installation_id AND generation=c.root_generation FOR SHARE;
 IF c.installation_id IS DISTINCT FROM a.installation_id OR c.root_generation IS DISTINCT FROM ctl.generation
 OR ctl.state IS DISTINCT FROM 'CONSUMED' OR a.human_id IS DISTINCT FROM ctl.expected_human_id
 OR a.tenant_id IS DISTINCT FROM ctl.expected_tenant_id OR e.actual_human_id IS DISTINCT FROM a.human_id
 OR c.revoked_at IS NOT NULL OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=a.tenant_id AND id=a.human_id AND kind='HUMAN')
 OR e.key_fingerprint IS DISTINCT FROM encode(sha256(p_key),'hex') THEN RAISE EXCEPTION 'CLOCK_POLICY_HUMAN_ENROLLMENT_REQUIRED'; END IF;
 bounds=company_private.r56_root_bounds(a.installation_id);
 IF NOT ((c.valid_from<=(bounds->>'utc_lower')::timestamptz AND (bounds->>'utc_upper')::timestamptz<c.valid_until) IS TRUE)
 THEN RAISE EXCEPTION 'CLOCK_POLICY_CONSENT_EXPIRED_OR_AMBIGUOUS'; END IF;
 j=convert_from(p_raw,'UTF8')::jsonb;
 IF jsonb_typeof(j) IS DISTINCT FROM 'object'
 OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1)
 OR NOT ((j ?& ARRAY['statement','backend_pid','transaction_id','db_login']) IS TRUE)
 OR (SELECT count(*) FROM jsonb_object_keys(j))<>4
 OR jsonb_typeof(j->'backend_pid') IS DISTINCT FROM 'number'
 OR j->>'backend_pid' !~ '^[1-9][0-9]*$'
 OR jsonb_typeof(j->'transaction_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(j->'db_login') IS DISTINCT FROM 'string'
 OR j->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text OR j->>'transaction_id' IS DISTINCT FROM pg_current_xact_id()::text
 OR j->>'db_login' IS DISTINCT FROM session_user::text THEN RAISE EXCEPTION 'CLOCK_POLICY_CONTEXT_MISMATCH'; END IF;
 s=j->'statement';
 IF jsonb_typeof(s) IS DISTINCT FROM 'object' OR NOT ((s ?& ARRAY['consent_id','installation_id','action','expected_revision','policy']) IS TRUE)
 OR (SELECT count(*) FROM jsonb_object_keys(s))<>5
 OR jsonb_typeof(s->'expected_revision') IS DISTINCT FROM 'number' OR s->>'expected_revision' !~ '^(0|[1-9][0-9]*)$'
 OR EXISTS(SELECT 1 FROM jsonb_each(s) z WHERE z.key IN ('consent_id','installation_id','action') AND jsonb_typeof(z.value) IS DISTINCT FROM 'string')
 THEN RAISE EXCEPTION 'CLOCK_POLICY_STATEMENT_SHAPE'; END IF;
 -- PG JSONB bytes, not a caller-supplied digest or Python JSON hash.
 d=encode(sha256(convert_to(s::text,'UTF8')),'hex');
 IF d IS DISTINCT FROM c.approved_statement_digest OR s->>'consent_id' IS DISTINCT FROM c.consent_id::text
 OR s->>'installation_id' IS DISTINCT FROM a.installation_id::text OR s->>'action' IS DISTINCT FROM c.action
 OR s->>'expected_revision' IS DISTINCT FROM c.expected_revision::text
 THEN RAISE EXCEPTION 'EXACT_HUMAN_POLICY_CONSENT_REQUIRED'; END IF;
 msg=convert_to('R57-CLOCK-POLICY-v1','UTF8')||decode('00','hex');
 FOREACH item IN ARRAY ARRAY[convert_to(c.consent_id::text,'UTF8'),convert_to(e.issuer_id::text,'UTF8'),convert_to(e.key_id::text,'UTF8'),convert_to(e.enrollment_revision::text,'UTF8'),p_raw] LOOP
  msg=msg||convert_to(octet_length(item)::text||':','UTF8')||item;
 END LOOP;
 IF company_private.r55_cp_tag_equal(company_private.r55_cp_hmac_sha256(p_key,msg),p_tag) IS NOT TRUE THEN RAISE EXCEPTION 'INVALID_CLOCK_POLICY_HMAC'; END IF;
 v=s->'policy';
 IF c.action='ACTIVATE' THEN
  IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR NOT ((v ?& ARRAY['bounded_handoff_duration_ms','max_uncertainty_ms','max_sample_age_ms','max_clock_jump_ms','first_alert_ms','owner_ack_ms','manual_reconcile_ms','poll_ms','max_drift_ms']) IS TRUE)
  OR (SELECT count(*) FROM jsonb_object_keys(v))<>9 THEN RAISE EXCEPTION 'NINE_EXPLICIT_CLOCK_DECISIONS_REQUIRED'; END IF;
  FOR policy_key IN SELECT jsonb_object_keys(v) LOOP
   IF jsonb_typeof(v->policy_key) IS DISTINCT FROM 'number' OR v->>policy_key !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'POSITIVE_INTEGER_CLOCK_DECISION_REQUIRED'; END IF;
   PERFORM (v->>policy_key)::bigint;
  END LOOP;
  IF (v->>'first_alert_ms')::bigint>(v->>'owner_ack_ms')::bigint OR (v->>'owner_ack_ms')::bigint>(v->>'manual_reconcile_ms')::bigint
  THEN RAISE EXCEPTION 'CLOCK_ESCALATION_ORDER'; END IF;
  pd=encode(sha256(convert_to(v::text,'UTF8')),'hex');
 ELSE
  IF v IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'REVOKE_POLICY_MUST_BE_NULL'; END IF;
  pd=NULL;v=NULL;
 END IF;
 SELECT * INTO STRICT op FROM company_private.operation_permissions WHERE operation_id='clock.policy.activate' FOR UPDATE;
 -- Recheck after registry lock wait, including the replay path.
 bounds=company_private.r56_root_bounds(a.installation_id);
 IF NOT ((c.valid_from<=(bounds->>'utc_lower')::timestamptz AND (bounds->>'utc_upper')::timestamptz<c.valid_until) IS TRUE)
 THEN RAISE EXCEPTION 'CLOCK_POLICY_FINAL_CONSENT_EXPIRED'; END IF;
 SELECT * INTO r FROM company_private.r57_clock_policy_receipts WHERE consent_id=c.consent_id;
 IF FOUND THEN
  IF r.statement_digest IS DISTINCT FROM d OR r.revision IS DISTINCT FROM op.policy_revision OR r.policy_digest IS DISTINCT FROM op.approved_policy_digest
  OR r.action IS DISTINCT FROM c.action
  OR r.receipt_digest IS DISTINCT FROM encode(sha256(convert_to(jsonb_build_array(r.consent_id,r.installation_id,r.human_id,r.revision,r.action,r.statement_digest,r.policy_digest,r.final_proof)::text,'UTF8')),'hex')
  OR NOT EXISTS(SELECT 1 FROM company.audit_events z WHERE z.tenant_id=r.tenant_id AND z.id=r.audit_id AND z.actor_id=r.human_id AND z.correlation_id=r.consent_id AND z.kind='ClockPolicy'||initcap(lower(r.action)))
  THEN RAISE EXCEPTION 'CLOCK_POLICY_REPLAY_STALE_OR_WITNESS_MISSING'; END IF;
  RETURN jsonb_build_object('consent_id',r.consent_id,'revision',r.revision,'receipt_digest',r.receipt_digest,'outcome','REPLAY_NO_NEW_REVISION');
 END IF;
 IF op.policy_revision IS DISTINCT FROM c.expected_revision THEN RAISE EXCEPTION 'CLOCK_POLICY_REVISION_CONFLICT'; END IF;
 revision=op.policy_revision+1;
 bounds=company_private.r56_root_bounds(a.installation_id);
 IF NOT ((c.valid_from<=(bounds->>'utc_lower')::timestamptz AND (bounds->>'utc_upper')::timestamptz<c.valid_until) IS TRUE)
 THEN RAISE EXCEPTION 'CLOCK_POLICY_FINAL_CONSENT_EXPIRED'; END IF;
 rd=encode(sha256(convert_to(jsonb_build_array(c.consent_id,a.installation_id,a.human_id,revision,c.action,d,pd,bounds)::text,'UTF8')),'hex');
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(a.tenant_id,c.consent_id,a.human_id,'ClockPolicy'||initcap(lower(c.action))) RETURNING id INTO aid;
 INSERT INTO company_private.r57_clock_policy_receipts(consent_id,installation_id,tenant_id,human_id,revision,action,statement_digest,policy_digest,policy,final_proof,receipt_digest,audit_id)
 VALUES(c.consent_id,a.installation_id,a.tenant_id,a.human_id,revision,c.action,d,pd,v,bounds,rd,aid);
 -- Registry lock precedes epoch locks in writer and every selected consumer.
 -- Retire current epochs atomically, freeing the one-current-epoch unique key.
 UPDATE company.clock_epochs SET invalidated_at=(bounds->>'utc_upper')::timestamptz
 WHERE tenant_id=a.tenant_id AND invalidated_at IS NULL;
 UPDATE company_private.operation_permissions SET policy_revision=revision,approved_policy_digest=pd
 WHERE operation_id='clock.policy.activate' AND policy_revision=c.expected_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'CLOCK_POLICY_CAS_CONFLICT'; END IF;
 -- Immutable epoch identity is preserved; only one-way invalidation changes.
 RETURN jsonb_build_object('consent_id',c.consent_id,'revision',revision,'receipt_digest',rd,'outcome',c.action);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'CLOCK_POLICY_NOT_ENROLLED';
END $$;
ALTER FUNCTION company_private.r57_clock_policy_write(uuid,bytea,bytea,bytea) OWNER TO company_clock_policy_owner_r57;
REVOKE ALL ON FUNCTION company_private.r57_clock_policy_write(uuid,bytea,bytea,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r57_clock_policy_write(uuid,bytea,bytea,bytea) TO company_clock_policy_transport_r57;
ROLLBACK;
