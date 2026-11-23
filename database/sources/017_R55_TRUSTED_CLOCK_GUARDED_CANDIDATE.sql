-- Inert clock persistence/currentness candidate; NOT a daemon or migration.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE ROLE company_clock_runtime_r55 NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
GRANT USAGE ON SCHEMA company_private TO company_clock_runtime_r55;
-- Default name is a preflight dependency; if catalog differs this aborts.
ALTER TABLE company.signer_enrollments DROP CONSTRAINT signer_enrollments_purpose_check;
ALTER TABLE company.signer_enrollments ADD CONSTRAINT r55_signer_purpose CHECK(purpose IN ('TASK_VERIFICATION','EVALUATION','EGRESS_QUIESCENCE','CLOCK_OBSERVATION'));
ALTER TABLE company.signer_enrollments ADD COLUMN r55_project_id uuid;
ALTER TABLE company.signer_enrollments ADD COLUMN r55_host_id uuid;
ALTER TABLE company.signer_enrollments ADD COLUMN r55_host_revision bigint;
ALTER TABLE company.signer_enrollments ADD COLUMN r55_host_generation bigint;
ALTER TABLE company.signer_enrollments ADD COLUMN r55_host_boot_id uuid;
ALTER TABLE company.signer_enrollments ADD FOREIGN KEY(tenant_id,r55_project_id,r55_host_id,r55_host_revision,r55_host_generation)
 REFERENCES company.host_registrations(tenant_id,project_id,id,revision,bound_generation);

ALTER TABLE company.clock_epochs ADD COLUMN r55_project_id uuid;
ALTER TABLE company.clock_epochs ADD COLUMN r55_host_registration_id uuid;
ALTER TABLE company.clock_epochs ADD COLUMN r55_host_registration_revision bigint;
ALTER TABLE company.clock_epochs ADD COLUMN r55_host_generation bigint;
ALTER TABLE company.clock_epochs ADD COLUMN r55_policy jsonb;
ALTER TABLE company.clock_epochs ADD FOREIGN KEY(tenant_id,r55_project_id,r55_host_registration_id,r55_host_registration_revision,r55_host_generation)
 REFERENCES company.host_registrations(tenant_id,project_id,id,revision,bound_generation);
CREATE UNIQUE INDEX r55_one_current_clock_epoch ON company.clock_epochs(tenant_id,r55_project_id)
 WHERE r55_project_id IS NOT NULL AND invalidated_at IS NULL;
CREATE FUNCTION company_private.r55_cp_clock_epoch_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'CLOCK_EPOCH_HISTORY_IMMUTABLE'; END IF;
 IF (to_jsonb(NEW)-'invalidated_at') IS DISTINCT FROM (to_jsonb(OLD)-'invalidated_at')
 OR (OLD.invalidated_at IS NOT NULL AND NEW IS DISTINCT FROM OLD)
 THEN RAISE EXCEPTION 'CLOCK_EPOCH_IDENTITY_OR_INVALIDATION_IMMUTABLE'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_epoch_immutable() FROM PUBLIC;
CREATE TRIGGER r55_clock_epoch_immutable BEFORE UPDATE OR DELETE ON company.clock_epochs FOR EACH ROW EXECUTE FUNCTION company_private.r55_cp_clock_epoch_immutable();
ALTER TABLE company.clock_samples ADD COLUMN r55_raw_proof_digest text;
ALTER TABLE company.clock_samples ADD COLUMN r55_source_sequence bigint;
ALTER TABLE company.clock_samples ADD COLUMN r55_source_enrollment_revision bigint;
ALTER TABLE company.clock_samples ADD COLUMN r55_source_issuer uuid;
ALTER TABLE company.clock_samples ADD COLUMN r55_source_key uuid;
ALTER TABLE company.clock_samples ADD COLUMN r55_frequency_error_ppm_bound numeric;
ALTER TABLE company.clock_samples ADD COLUMN r55_sampling_error_margin_ns numeric(20,0);
CREATE UNIQUE INDEX r55_clock_source_sequence ON company.clock_samples(tenant_id,epoch_id,r55_source_sequence);

-- DB-local trusted observer source is r55_clock_observer.c. The library must
-- be compiled from the pinned source and independently enrolled before install.
-- No compile/load is performed in this task; unsupported platforms fail closed.
CREATE FUNCTION company_private.r55_cp_clock_observe_local()
RETURNS jsonb AS '$libdir/r55_clock_observer','r55_cp_clock_observe_local'
LANGUAGE C VOLATILE SECURITY INVOKER;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_observe_local() FROM PUBLIC;

-- Exact raw-byte HMAC verification, not caller-supplied verified=true. The
-- exclusive trusted verifier login receives the key from its enrolled adapter;
-- no runtime role membership/EXECUTE is installed here.
CREATE FUNCTION company_private.r55_cp_verify_clock_statement(
 p_issuer uuid,p_key_id uuid,p_revision bigint,p_raw bytea,p_tag bytea,p_secret bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j jsonb; e company.signer_enrollments%ROWTYPE; message bytea; item bytea;
 values bytea[]; tenant uuid;
BEGIN
 IF session_user<>'company_clock_runtime_r55' THEN RAISE EXCEPTION 'TRUSTED_CLOCK_VERIFIER_LOGIN_REQUIRED'; END IF;
 IF p_issuer IS NULL OR p_key_id IS NULL OR p_revision IS NULL OR p_revision<0
 OR p_raw IS NULL OR octet_length(p_raw)>65536 OR octet_length(p_raw)=0
 OR p_tag IS NULL OR octet_length(p_tag)<>32 OR p_secret IS NULL OR octet_length(p_secret)<>32
 THEN RAISE EXCEPTION 'INVALID_CLOCK_PROOF'; END IF;
 j=convert_from(p_raw,'UTF8')::jsonb;
 IF jsonb_typeof(j)<>'object' OR EXISTS(SELECT key FROM json_each(convert_from(p_raw,'UTF8')::json) GROUP BY key HAVING count(*)>1)
 THEN RAISE EXCEPTION 'AMBIGUOUS_CLOCK_JSON'; END IF;
 IF NOT ((j ?& ARRAY['tenant_id','project_id','epoch_id','sample_id','host_boot_id','backend_pid','transaction_id','db_login','phase','current_boottime_ns','valid_until_boottime_ns','utc_lower_bound','utc_upper_bound']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(j) z WHERE z.key IN ('tenant_id','project_id','epoch_id','sample_id','host_boot_id','transaction_id','db_login','phase','utc_lower_bound','utc_upper_bound')
  AND jsonb_typeof(z.value) IS DISTINCT FROM 'string')
 OR EXISTS(SELECT 1 FROM jsonb_each(j) z WHERE z.key IN ('backend_pid','current_boottime_ns','valid_until_boottime_ns')
  AND (jsonb_typeof(z.value) IS DISTINCT FROM 'number' OR z.value::text !~ '^[0-9]+$'))
 THEN RAISE EXCEPTION 'CLOCK_REQUIRED_TYPED_FIELDS'; END IF;
 tenant=(j->>'tenant_id')::uuid;
 SELECT * INTO STRICT e FROM company.signer_enrollments
 WHERE tenant_id=tenant AND issuer_id=p_issuer AND key_id=p_key_id
 AND purpose='CLOCK_OBSERVATION' AND enrollment_revision=p_revision FOR SHARE;
 IF e.profile_id IS DISTINCT FROM 'R55_CLOCK_V1_RAW_JSON'
 OR e.revoked_at IS NOT NULL OR e.compromised_since IS NOT NULL
 OR e.key_fingerprint IS DISTINCT FROM encode(sha256(p_secret),'hex')
 OR e.approved_by IS NULL OR e.approved_by=e.issuer_id
 OR NOT isfinite(e.valid_from) OR NOT isfinite(e.valid_until)
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=e.tenant_id AND id=e.approved_by AND kind='HUMAN')
 THEN RAISE EXCEPTION 'CLOCK_ENROLLMENT_NOT_TRUSTED'; END IF;
 IF NOT ((j ?& ARRAY['tenant_id','project_id','epoch_id','sample_id','host_boot_id','backend_pid','transaction_id','db_login','phase','current_boottime_ns','valid_until_boottime_ns','utc_lower_bound','utc_upper_bound']) IS TRUE)
 OR j->>'phase' IS DISTINCT FROM 'FINAL_AFTER_LOCKS'
 OR j->>'backend_pid' IS DISTINCT FROM pg_backend_pid()::text
 OR j->>'transaction_id' IS DISTINCT FROM pg_current_xact_id()::text
 OR j->>'db_login' IS DISTINCT FROM session_user::text
 OR e.r55_project_id IS NULL OR e.r55_host_id IS NULL OR e.r55_host_revision IS NULL OR e.r55_host_generation IS NULL OR e.r55_host_boot_id IS NULL
 OR j->>'project_id' IS DISTINCT FROM e.r55_project_id::text OR j->>'host_registration_id' IS DISTINCT FROM e.r55_host_id::text
 OR j->>'host_registration_revision' IS DISTINCT FROM e.r55_host_revision::text OR j->>'host_generation' IS DISTINCT FROM e.r55_host_generation::text
 OR j->>'host_boot_id' IS DISTINCT FROM e.r55_host_boot_id::text
 OR j->>'utc_lower_bound' IS NULL OR j->>'utc_upper_bound' IS NULL
 OR NOT ((isfinite((j->>'utc_lower_bound')::timestamptz) AND isfinite((j->>'utc_upper_bound')::timestamptz)
 AND e.valid_from<=(j->>'utc_lower_bound')::timestamptz
 AND (j->>'utc_lower_bound')::timestamptz<=(j->>'utc_upper_bound')::timestamptz
 AND (j->>'utc_upper_bound')::timestamptz<e.valid_until) IS TRUE)
 THEN RAISE EXCEPTION 'CLOCK_STATEMENT_NOT_CURRENT_BINDING'; END IF;
 message=convert_to('R55-CP-PROOF-v1','UTF8')||decode('00','hex');
 values=ARRAY[convert_to('CLOCK_OBSERVATION','UTF8'),convert_to(p_issuer::text,'UTF8'),convert_to(p_key_id::text,'UTF8'),convert_to(p_revision::text,'UTF8'),p_raw];
 FOREACH item IN ARRAY values LOOP message=message||convert_to(octet_length(item)::text||':','UTF8')||item; END LOOP;
 IF company_private.r55_cp_hmac_sha256(p_secret,message) IS DISTINCT FROM p_tag THEN RAISE EXCEPTION 'INVALID_CLOCK_HMAC'; END IF;
 RETURN j;
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'CLOCK_SIGNER_NOT_ENROLLED';
END $$;
ALTER FUNCTION company_private.r55_cp_verify_clock_statement(uuid,uuid,bigint,bytea,bytea,bytea) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_verify_clock_statement(uuid,uuid,bigint,bytea,bytea,bytea) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_clock_epoch_register(
 p_issuer uuid,p_key_id uuid,p_revision bigint,p_raw bytea,p_tag bytea,p_secret bytea,
 p_host uuid,p_host_revision bigint,p_host_generation bigint,p_policy jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j jsonb;obs jsonb;t uuid;project uuid;epoch uuid;d text;
BEGIN
 j=company_private.r55_cp_verify_clock_statement(p_issuer,p_key_id,p_revision,p_raw,p_tag,p_secret);
 t=(j->>'tenant_id')::uuid;project=(j->>'project_id')::uuid;epoch=(j->>'epoch_id')::uuid;
 IF p_host IS NULL OR p_host_revision IS NULL OR p_host_generation IS NULL OR p_policy IS NULL
 OR jsonb_typeof(p_policy)<>'object' OR NOT ((p_policy ?& ARRAY['max_sample_age_ms','max_uncertainty_ms','max_drift_ms','max_clock_jump_ms']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(p_policy) z WHERE z.key IN ('max_sample_age_ms','max_uncertainty_ms','max_drift_ms','max_clock_jump_ms')
 AND (jsonb_typeof(z.value)<>'number' OR z.value::text !~ '^[0-9]+$')) THEN RAISE EXCEPTION 'INVALID_CLOCK_EPOCH_PROFILE'; END IF;
 d=encode(sha256(convert_to(p_policy::text,'UTF8')),'hex');
 IF j->>'host_registration_id' IS DISTINCT FROM p_host::text OR j->>'host_registration_revision' IS DISTINCT FROM p_host_revision::text
 OR j->>'host_generation' IS DISTINCT FROM p_host_generation::text OR j->>'policy_digest' IS DISTINCT FROM d
 THEN RAISE EXCEPTION 'CLOCK_SIGNED_HOST_POLICY_MISMATCH'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.operation_permissions WHERE operation_id='clock.policy.activate' AND approved_policy_digest=d)
 THEN RAISE EXCEPTION 'CLOCK_POLICY_NOT_APPROVED'; END IF;
 PERFORM 1 FROM company.host_registrations h JOIN company.projects p ON p.tenant_id=h.tenant_id AND p.id=h.project_id
 WHERE h.tenant_id=t AND h.project_id=project AND h.id=p_host AND h.revision=p_host_revision AND h.bound_generation=p_host_generation
 AND h.state='BOUND_NOT_LEASED' AND p.host_registration_id=h.id AND p.host_registration_revision=h.revision AND p.instance_generation=h.bound_generation;
 IF NOT FOUND THEN RAISE EXCEPTION 'CLOCK_HOST_GENERATION_STALE'; END IF;
 obs=company_private.r55_cp_clock_observe_local();
 IF obs->>'source_sync_state' IS DISTINCT FROM 'SYNC' OR obs->>'host_boot_id' IS DISTINCT FROM j->>'host_boot_id'
 THEN RAISE EXCEPTION 'BLOCKED_DB_LOCAL_CLOCK_SOURCE'; END IF;
 INSERT INTO company.clock_epochs(tenant_id,epoch_id,supervisor_id,host_boot_id,writer_generation,policy_digest,registered_at,
 r55_project_id,r55_host_registration_id,r55_host_registration_revision,r55_host_generation,r55_policy)
 VALUES(t,epoch,p_issuer,(j->>'host_boot_id')::uuid,54,d,clock_timestamp(),project,p_host,p_host_revision,p_host_generation,p_policy);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(t,epoch,p_issuer,'ClockEpochRegistered');
 RETURN epoch;
END $$;
ALTER FUNCTION company_private.r55_cp_clock_epoch_register(uuid,uuid,bigint,bytea,bytea,bytea,uuid,bigint,bigint,jsonb) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_epoch_register(uuid,uuid,bigint,bytea,bytea,bytea,uuid,bigint,bigint,jsonb) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_clock_sample_persist(
 p_issuer uuid,p_key_id uuid,p_revision bigint,p_raw bytea,p_tag bytea,p_secret bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE j jsonb;e company.clock_epochs%ROWTYPE;s company.clock_samples%ROWTYPE;
 t uuid;project uuid;epoch uuid;sample uuid;seq bigint;bt numeric;age_ns numeric;d text;reason text;
 lo timestamptz;hi timestamptz;u bigint;freq numeric;margin numeric;
BEGIN
 j=company_private.r55_cp_verify_clock_statement(p_issuer,p_key_id,p_revision,p_raw,p_tag,p_secret);
 IF NOT ((j ?& ARRAY['cut_nonce','source_sequence','sampled_at','utc_lower_bound','utc_upper_bound','sample_boottime_ns','sample_uncertainty_ms','frequency_error_ppm_bound','sampling_error_margin_ns','source_sync_state']) IS TRUE)
 THEN RAISE EXCEPTION 'CLOCK_SAMPLE_FIELDS_REQUIRED'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each(j) z WHERE z.key IN ('source_sequence','sample_boottime_ns','sample_uncertainty_ms','frequency_error_ppm_bound','sampling_error_margin_ns','current_boottime_ns','valid_until_boottime_ns')
 AND (jsonb_typeof(z.value)<>'number' OR z.value::text !~ '^[0-9]+$')) THEN RAISE EXCEPTION 'CLOCK_INTEGER_REQUIRED'; END IF;
 t=(j->>'tenant_id')::uuid;project=(j->>'project_id')::uuid;epoch=(j->>'epoch_id')::uuid;sample=(j->>'sample_id')::uuid;
 seq=(j->>'source_sequence')::bigint;bt=(j->>'sample_boottime_ns')::numeric;
 lo=(j->>'utc_lower_bound')::timestamptz;hi=(j->>'utc_upper_bound')::timestamptz;
 u=(j->>'sample_uncertainty_ms')::bigint;freq=(j->>'frequency_error_ppm_bound')::numeric;margin=(j->>'sampling_error_margin_ns')::numeric;
 IF seq<1 OR hi<lo OR u<0 OR bt<0 OR freq<0 OR margin<0
 OR extract(epoch FROM (hi-lo))*1000000000>2*u::numeric*1000000
 OR (j->>'sampled_at')::timestamptz<lo OR (j->>'sampled_at')::timestamptz>hi
 OR (j->>'current_boottime_ns')::numeric<bt
 OR (j->>'valid_until_boottime_ns')::numeric<=(j->>'current_boottime_ns')::numeric
 THEN RAISE EXCEPTION 'INVALID_CLOCK_SAMPLE_BOUNDS'; END IF;
 SELECT * INTO STRICT e FROM company.clock_epochs WHERE tenant_id=t AND epoch_id=epoch FOR UPDATE;
 IF e.invalidated_at IS NOT NULL OR e.supervisor_id IS DISTINCT FROM p_issuer OR e.writer_generation IS DISTINCT FROM 54
 OR e.r55_project_id IS DISTINCT FROM project OR e.host_boot_id IS DISTINCT FROM (j->>'host_boot_id')::uuid
 OR e.r55_policy IS NULL OR e.r55_host_registration_id IS NULL OR e.r55_host_generation IS NULL
 THEN RAISE EXCEPTION 'CLOCK_EPOCH_BINDING_MISMATCH'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.host_registrations h JOIN company.projects p ON p.tenant_id=h.tenant_id AND p.id=h.project_id
 WHERE h.tenant_id=t AND h.project_id=project AND h.id=e.r55_host_registration_id AND h.revision=e.r55_host_registration_revision
 AND h.bound_generation=e.r55_host_generation AND h.state='BOUND_NOT_LEASED'
 AND p.host_registration_id=h.id AND p.host_registration_revision=h.revision AND p.instance_generation=h.bound_generation)
 THEN RAISE EXCEPTION 'CLOCK_HOST_GENERATION_STALE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.operation_permissions op WHERE op.operation_id='clock.policy.activate'
 AND op.approved_policy_digest=e.policy_digest AND op.approved_policy_digest=encode(sha256(convert_to(e.r55_policy::text,'UTF8')),'hex'))
 THEN RAISE EXCEPTION 'CLOCK_POLICY_NOT_APPROVED'; END IF;
 IF NOT ((e.r55_policy ?& ARRAY['max_clock_jump_ms','max_uncertainty_ms','max_drift_ms','max_sample_age_ms']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(e.r55_policy) z WHERE z.key IN ('max_clock_jump_ms','max_uncertainty_ms','max_drift_ms','max_sample_age_ms')
 AND (jsonb_typeof(z.value)<>'number' OR z.value::text !~ '^[0-9]+$')) THEN RAISE EXCEPTION 'CLOCK_POLICY_INVALID'; END IF;
 d=encode(sha256(p_raw),'hex');
 SELECT * INTO s FROM company.clock_samples WHERE tenant_id=t AND epoch_id=epoch AND sample_id=sample;
 IF FOUND THEN
  IF s.r55_raw_proof_digest IS DISTINCT FROM d THEN RAISE EXCEPTION 'CLOCK_SAMPLE_DIGEST_CONFLICT'; END IF;
  RETURN jsonb_build_object('status','REPLAY_NO_NEW_CUT','sample_id',sample);
 END IF;
 SELECT * INTO s FROM company.clock_samples WHERE tenant_id=t AND epoch_id=epoch ORDER BY boottime_ns DESC,sample_id DESC LIMIT 1;
 IF FOUND THEN
  IF s.r55_source_sequence IS NULL OR seq<=s.r55_source_sequence OR bt<=s.boottime_ns THEN RAISE EXCEPTION 'CLOCK_REPLAY_OR_REORDER'; END IF;
  age_ns=bt-s.boottime_ns;
  IF greatest(abs(extract(epoch FROM (lo-s.utc_upper_bound))*1000000000-age_ns),abs(extract(epoch FROM (hi-s.utc_lower_bound))*1000000000-age_ns))
  >(e.r55_policy->>'max_clock_jump_ms')::numeric*1000000 THEN reason='CLOCK_JUMP'; END IF;
 ELSIF seq<>1 THEN RAISE EXCEPTION 'CLOCK_FIRST_SEQUENCE_REQUIRED'; END IF;
 IF j->>'source_sync_state' IS DISTINCT FROM 'SYNC' THEN reason='CLOCK_SOURCE_UNSYNCHRONIZED'; END IF;
 IF reason IS NOT NULL THEN
  UPDATE company.clock_epochs SET invalidated_at=clock_timestamp() WHERE tenant_id=t AND epoch_id=epoch AND invalidated_at IS NULL;
  INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(t,(j->>'cut_nonce')::uuid,p_issuer,reason);
  -- Commit this BLOCKED result to preserve invalidation. A caller must not turn
  -- it into a success exception handler or silently rollback and reuse the epoch.
  RETURN jsonb_build_object('status','BLOCKED','reason',reason,'epoch_invalidated',true);
 END IF;
 INSERT INTO company.clock_samples(tenant_id,epoch_id,sample_id,sampled_at,utc_lower_bound,utc_upper_bound,boottime_ns,uncertainty_ms,sample_digest,
 r55_raw_proof_digest,r55_source_sequence,r55_source_enrollment_revision,r55_source_issuer,r55_source_key,r55_frequency_error_ppm_bound,r55_sampling_error_margin_ns)
 VALUES(t,epoch,sample,(j->>'sampled_at')::timestamptz,lo,hi,bt,u,d,d,seq,p_revision,p_issuer,p_key_id,freq,margin);
 INSERT INTO company.audit_events(tenant_id,correlation_id,actor_id,kind) VALUES(t,(j->>'cut_nonce')::uuid,p_issuer,'ClockObservationPersisted');
 -- Cut persistence is intentionally separate from sample persistence until the
 -- live after-lock BOOTTIME adapter is implemented. No durable sample is HEALTHY.
 RETURN jsonb_build_object('status','SAMPLE_PERSISTED_NO_LIVE_CUT','sample_id',sample,'source_sequence',seq);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'CLOCK_SOURCE_UNRESOLVED';
END $$;
ALTER FUNCTION company_private.r55_cp_clock_sample_persist(uuid,uuid,bigint,bytea,bytea,bytea) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_sample_persist(uuid,uuid,bigint,bytea,bytea,bytea) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_clock_current_bounds_at(p_tenant uuid,p_project uuid,p_epoch uuid,p_sample uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e company.clock_epochs%ROWTYPE;s company.clock_samples%ROWTYPE;
 obs jsonb;age_ns numeric;age_lower_ns numeric;drift_ns numeric;uncertainty_ns numeric;
 utc_lo timestamptz;utc_hi timestamptz;capture_ns numeric;
BEGIN
 IF p_tenant IS NULL OR p_project IS NULL OR p_epoch IS NULL OR p_sample IS NULL THEN RAISE EXCEPTION 'BLOCKED_TIME_DEPENDENCY'; END IF;
 SELECT * INTO STRICT e FROM company.clock_epochs WHERE tenant_id=p_tenant AND epoch_id=p_epoch FOR SHARE;
 SELECT * INTO STRICT s FROM company.clock_samples WHERE tenant_id=p_tenant AND epoch_id=p_epoch AND sample_id=p_sample;
 IF e.invalidated_at IS NOT NULL OR e.writer_generation IS DISTINCT FROM 54 OR e.r55_project_id IS DISTINCT FROM p_project
 OR e.r55_host_registration_id IS NULL OR e.r55_host_registration_revision IS NULL OR e.r55_host_generation IS NULL
 OR e.r55_policy IS NULL OR s.r55_raw_proof_digest IS NULL OR s.r55_source_sequence IS NULL OR s.r55_source_sequence<2
 OR s.r55_source_issuer IS DISTINCT FROM e.supervisor_id OR s.r55_source_key IS NULL OR s.r55_source_enrollment_revision IS NULL
 OR s.r55_frequency_error_ppm_bound IS NULL OR s.r55_frequency_error_ppm_bound<0
 OR s.r55_sampling_error_margin_ns IS NULL OR s.r55_sampling_error_margin_ns<0
 THEN RAISE EXCEPTION 'CLOCK_EPOCH_SAMPLE_NOT_CURRENT'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.host_registrations h JOIN company.projects p ON p.tenant_id=h.tenant_id AND p.id=h.project_id
 WHERE h.tenant_id=p_tenant AND h.project_id=p_project AND h.id=e.r55_host_registration_id AND h.revision=e.r55_host_registration_revision
 AND h.bound_generation=e.r55_host_generation AND h.state='BOUND_NOT_LEASED'
 AND p.host_registration_id=h.id AND p.host_registration_revision=h.revision AND p.instance_generation=h.bound_generation)
 THEN RAISE EXCEPTION 'CLOCK_HOST_GENERATION_STALE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.operation_permissions op WHERE op.operation_id='clock.policy.activate'
 AND op.approved_policy_digest=e.policy_digest AND op.approved_policy_digest=encode(sha256(convert_to(e.r55_policy::text,'UTF8')),'hex'))
 THEN RAISE EXCEPTION 'CLOCK_POLICY_NOT_APPROVED'; END IF;
 IF NOT ((jsonb_typeof(e.r55_policy)='object' AND e.r55_policy ?& ARRAY['max_sample_age_ms','max_uncertainty_ms','max_drift_ms','max_clock_jump_ms']) IS TRUE)
 OR EXISTS(SELECT 1 FROM jsonb_each(e.r55_policy) z WHERE z.key IN ('max_sample_age_ms','max_uncertainty_ms','max_drift_ms','max_clock_jump_ms')
 AND (jsonb_typeof(z.value)<>'number' OR z.value::text !~ '^[0-9]+$')) THEN RAISE EXCEPTION 'CLOCK_POLICY_INVALID'; END IF;
 -- Fresh native BOOTTIME read occurs AFTER SQL row locks, every guard call.
 -- A remote producer whose boot/host differs cannot authorize this DB-local path.
 obs=company_private.r55_cp_clock_observe_local();
 IF obs->>'profile' IS DISTINCT FROM 'LINUX_ADJTIMEX_DB_LOCAL_V1' OR obs->>'source_sync_state' IS DISTINCT FROM 'SYNC'
 OR (obs->>'host_boot_id')::uuid IS DISTINCT FROM e.host_boot_id OR (obs->>'backend_pid')::integer IS DISTINCT FROM pg_backend_pid()
 THEN RAISE EXCEPTION 'BLOCKED_LOCAL_CLOCK_SOURCE'; END IF;
 age_ns=(obs->>'boottime_after_ns')::numeric-s.boottime_ns;
 age_lower_ns=(obs->>'boottime_before_ns')::numeric-s.boottime_ns;
 capture_ns=(obs->>'boottime_after_ns')::numeric-(obs->>'boottime_before_ns')::numeric;
 IF age_lower_ns<0 OR capture_ns<0 OR age_ns>(e.r55_policy->>'max_sample_age_ms')::numeric*1000000 THEN RAISE EXCEPTION 'CLOCK_SAMPLE_STALE'; END IF;
 drift_ns=ceil(age_ns*s.r55_frequency_error_ppm_bound/1000000)+s.r55_sampling_error_margin_ns;
 IF drift_ns>(e.r55_policy->>'max_drift_ms')::numeric*1000000 THEN RAISE EXCEPTION 'CLOCK_DRIFT_EXCEEDED'; END IF;
 uncertainty_ns=greatest(s.uncertainty_ms::numeric*1000000+drift_ns+capture_ns,(obs->>'maxerror_us')::numeric*1000,(obs->>'esterror_us')::numeric*1000);
 IF uncertainty_ns>(e.r55_policy->>'max_uncertainty_ms')::numeric*1000000 THEN RAISE EXCEPTION 'CLOCK_UNCERTAINTY_EXCEEDED'; END IF;
 IF greatest(abs((obs->>'utc_ns')::numeric-extract(epoch FROM s.utc_lower_bound)*1000000000-age_ns),
             abs((obs->>'utc_ns')::numeric-extract(epoch FROM s.utc_upper_bound)*1000000000-age_lower_ns))
 >(e.r55_policy->>'max_clock_jump_ms')::numeric*1000000 THEN RAISE EXCEPTION 'CLOCK_JUMP'; END IF;
 -- Trusted current UTC is projected from the signed source interval and fresh
 -- BOOTTIME; local realtime is only a jump rejection, not an expiry authority.
 utc_lo=s.utc_lower_bound+floor((age_lower_ns-drift_ns)/1000)*interval '1 microsecond';
 utc_hi=s.utc_upper_bound+ceil((age_ns+drift_ns)/1000)*interval '1 microsecond';
 IF NOT EXISTS(SELECT 1 FROM company.signer_enrollments k WHERE k.tenant_id=p_tenant AND k.issuer_id=s.r55_source_issuer
 AND k.key_id=s.r55_source_key AND k.enrollment_revision=s.r55_source_enrollment_revision AND k.purpose='CLOCK_OBSERVATION'
 AND k.profile_id='R55_CLOCK_V1_RAW_JSON' AND k.revoked_at IS NULL AND k.compromised_since IS NULL
 AND k.r55_project_id=p_project AND k.r55_host_id=e.r55_host_registration_id AND k.r55_host_revision=e.r55_host_registration_revision
 AND k.r55_host_generation=e.r55_host_generation AND k.r55_host_boot_id=e.host_boot_id
 AND k.valid_from<=utc_lo AND k.valid_until>utc_hi)
 THEN RAISE EXCEPTION 'CLOCK_SAMPLE_ENROLLMENT_REVOKED_OR_AMBIGUOUS'; END IF;
 RETURN jsonb_build_object('utc_lower_bound',utc_lo,'utc_upper_bound',utc_hi,'epoch_id',p_epoch,'sample_id',p_sample,
 'host_boot_id',e.host_boot_id,'host_registration_id',e.r55_host_registration_id,'host_registration_revision',e.r55_host_registration_revision,
 'host_generation',e.r55_host_generation,'writer_generation',e.writer_generation,'boottime_after_ns',obs->'boottime_after_ns');
END $$;
ALTER FUNCTION company_private.r55_cp_clock_current_bounds_at(uuid,uuid,uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_current_bounds_at(uuid,uuid,uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_clock_assert_current(p_tenant uuid,p_project uuid,p_epoch uuid,p_sample uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN PERFORM company_private.r55_cp_clock_current_bounds_at(p_tenant,p_project,p_epoch,p_sample); END $$;
ALTER FUNCTION company_private.r55_cp_clock_assert_current(uuid,uuid,uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_assert_current(uuid,uuid,uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_require_clock_health(p_tenant uuid,p_project uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e uuid;s uuid;
BEGIN
 SELECT ce.epoch_id,cs.sample_id INTO STRICT e,s FROM company.clock_epochs ce JOIN company.clock_samples cs
 ON cs.tenant_id=ce.tenant_id AND cs.epoch_id=ce.epoch_id
 WHERE ce.tenant_id=p_tenant AND ce.r55_project_id=p_project AND ce.invalidated_at IS NULL
 ORDER BY ce.registered_at DESC,ce.epoch_id DESC,cs.boottime_ns DESC,cs.sample_id DESC LIMIT 1;
 PERFORM company_private.r55_cp_clock_assert_current(p_tenant,p_project,e,s);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'BLOCKED_TIME_DEPENDENCY';
END $$;
ALTER FUNCTION company_private.r55_cp_require_clock_health(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_require_clock_health(uuid,uuid) FROM PUBLIC;
CREATE FUNCTION company_private.r55_cp_clock_current_bounds(p_tenant uuid,p_project uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE e uuid;s uuid;
BEGIN
 SELECT ce.epoch_id,cs.sample_id INTO STRICT e,s FROM company.clock_epochs ce JOIN company.clock_samples cs
 ON cs.tenant_id=ce.tenant_id AND cs.epoch_id=ce.epoch_id
 WHERE ce.tenant_id=p_tenant AND ce.r55_project_id=p_project AND ce.invalidated_at IS NULL
 ORDER BY ce.registered_at DESC,ce.epoch_id DESC,cs.boottime_ns DESC,cs.sample_id DESC LIMIT 1;
 RETURN company_private.r55_cp_clock_current_bounds_at(p_tenant,p_project,e,s);
EXCEPTION WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN RAISE EXCEPTION 'BLOCKED_TIME_DEPENDENCY';
END $$;
ALTER FUNCTION company_private.r55_cp_clock_current_bounds(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_clock_current_bounds(uuid,uuid) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_time_window_current(p_tenant uuid,p_project uuid,p_valid_from timestamptz,p_valid_until timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE b jsonb;
BEGIN
 IF p_valid_from IS NULL OR p_valid_until IS NULL OR p_valid_until<=p_valid_from THEN RETURN false; END IF;
 b=company_private.r55_cp_clock_current_bounds(p_tenant,p_project);
 RETURN ((p_valid_from<=(b->>'utc_lower_bound')::timestamptz AND (b->>'utc_upper_bound')::timestamptz<p_valid_until) IS TRUE);
END $$;
ALTER FUNCTION company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz) FROM PUBLIC;

CREATE FUNCTION company_private.r55_cp_require_not_expired(p_tenant uuid,p_project uuid,p_expiry timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE b jsonb;
BEGIN
 IF p_expiry IS NULL THEN RAISE EXCEPTION 'TIME_EXPIRY_REQUIRED'; END IF;
 b=company_private.r55_cp_clock_current_bounds(p_tenant,p_project);
 IF NOT (((b->>'utc_upper_bound')::timestamptz<p_expiry) IS TRUE) THEN RAISE EXCEPTION 'TIME_EXPIRED_OR_AMBIGUOUS'; END IF;
END $$;
ALTER FUNCTION company_private.r55_cp_require_not_expired(uuid,uuid,timestamptz) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r55_cp_require_not_expired(uuid,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_time_window_current(uuid,uuid,timestamptz,timestamptz),company_private.r55_cp_require_not_expired(uuid,uuid,timestamptz),company_private.r55_cp_clock_current_bounds(uuid,uuid) TO company_first_run_functions_r53,company_revoke_functions_r53;

-- Source-exact replacement of the historical unconditional stub. CREATE OR
-- REPLACE keeps its signature and existing object grants; no new transport role.
CREATE OR REPLACE FUNCTION company_private.r54_require_clock_health(p_tenant uuid,p_project uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM company_private.r55_cp_require_clock_health(p_tenant,p_project);
END $$;
ALTER FUNCTION company_private.r54_require_clock_health(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r54_require_clock_health(uuid,uuid) FROM PUBLIC;
-- Finite owner metadata reads; normal roles get no table DML or source key.
GRANT SELECT ON company.clock_epochs,company.clock_samples,company.signer_enrollments,company.host_registrations,company.projects,company.principals,company_private.operation_permissions TO company_context_owner;
GRANT INSERT ON company.clock_epochs,company.clock_samples,company.audit_events TO company_context_owner;
GRANT UPDATE(invalidated_at) ON company.clock_epochs TO company_context_owner;
GRANT UPDATE(revoked_at) ON company.signer_enrollments TO company_context_owner;
GRANT USAGE ON SEQUENCE company.audit_events_id_seq TO company_context_owner;
CREATE POLICY r55_clock_epoch_read ON company.clock_epochs FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r55_clock_epoch_insert ON company.clock_epochs FOR INSERT TO company_context_owner WITH CHECK(session_user='company_clock_runtime_r55');
CREATE POLICY r55_clock_epoch_lock ON company.clock_epochs FOR UPDATE TO company_context_owner USING(true) WITH CHECK(true);
CREATE POLICY r55_clock_sample_read ON company.clock_samples FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r55_clock_sample_insert ON company.clock_samples FOR INSERT TO company_context_owner WITH CHECK(session_user='company_clock_runtime_r55');
CREATE POLICY r55_clock_signer_read ON company.signer_enrollments FOR SELECT TO company_context_owner USING(purpose='CLOCK_OBSERVATION');
CREATE POLICY r55_clock_signer_lock ON company.signer_enrollments FOR UPDATE TO company_context_owner USING(purpose='CLOCK_OBSERVATION') WITH CHECK(false);
CREATE POLICY r55_clock_host_read ON company.host_registrations FOR SELECT TO company_context_owner USING(true);
CREATE POLICY r55_clock_audit ON company.audit_events FOR INSERT TO company_context_owner WITH CHECK(session_user='company_clock_runtime_r55');
GRANT EXECUTE ON FUNCTION company_private.r55_cp_hmac_sha256(bytea,bytea),company_private.r55_cp_clock_observe_local() TO company_context_owner;
GRANT EXECUTE ON FUNCTION company_private.r55_cp_verify_clock_statement(uuid,uuid,bigint,bytea,bytea,bytea),company_private.r55_cp_clock_sample_persist(uuid,uuid,bigint,bytea,bytea,bytea),company_private.r55_cp_clock_epoch_register(uuid,uuid,bigint,bytea,bytea,bytea,uuid,bigint,bigint,jsonb) TO company_clock_runtime_r55;
-- NO caller EXECUTE before exact verifier login/DB-local host/profile/compiled
-- source enrollment; actual identity/policy rows are not generated here.
ROLLBACK;
