-- Inert r58 extension of selected r53/r54/r55/r56/r57 ABI. Not a migration.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE ROLE company_execution_functions_r58 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE ROLE company_attestation_functions_r58 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE TRIGGER r58_acceptance_immutable BEFORE UPDATE OR DELETE ON company.acceptance_records FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();
-- No role membership, LOGIN, approval, policy duration or secret is enrolled.
GRANT USAGE ON SCHEMA company,company_private TO company_execution_functions_r58,company_attestation_functions_r58;
CREATE TABLE company_private.r58_key_material (
 key_id uuid PRIMARY KEY, purpose text NOT NULL CHECK(purpose IN ('EXECUTION_ATTESTATION','CLOCK_POLICY')),
 secret bytea NOT NULL CHECK(octet_length(secret)=32),
 fingerprint text NOT NULL CHECK(fingerprint=encode(sha256(secret),'hex')),
 revoked boolean NOT NULL DEFAULT false
);
REVOKE ALL ON company_private.r58_key_material FROM PUBLIC;
ALTER TABLE company_private.r58_key_material ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_private.r58_key_material FORCE ROW LEVEL SECURITY;
GRANT SELECT ON company_private.r58_key_material TO company_attestation_functions_r58;
CREATE POLICY r58_secret_verifier ON company_private.r58_key_material FOR SELECT TO company_attestation_functions_r58 USING(purpose='EXECUTION_ATTESTATION' AND NOT revoked);
GRANT UPDATE(revoked) ON company_private.r58_key_material TO company_attestation_functions_r58;
CREATE POLICY r58_secret_lock ON company_private.r58_key_material FOR UPDATE TO company_attestation_functions_r58 USING(purpose='EXECUTION_ATTESTATION') WITH CHECK(false);

CREATE TABLE company_private.r58_attestations (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,id uuid NOT NULL,
 issuer_id uuid NOT NULL,key_id uuid NOT NULL,enrollment_revision bigint NOT NULL,
 profile text NOT NULL,raw_digest text NOT NULL CHECK(raw_digest ~ '^[a-f0-9]{64}$'),
 raw_bytes bytea NOT NULL CHECK(octet_length(raw_bytes) BETWEEN 1 AND 65536 AND encode(sha256(raw_bytes),'hex')=raw_digest),
 auth_tag text NOT NULL CHECK(auth_tag ~ '^[a-f0-9]{64}$'),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 PRIMARY KEY(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,issuer_id) REFERENCES company.principals(tenant_id,id)
);
CREATE TABLE company_private.r58_lease_policies (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,revision bigint NOT NULL CHECK(revision>0),
 duration_ms bigint NOT NULL CHECK(duration_ms>0),enabled boolean NOT NULL DEFAULT false,
 allowed_tools text[] NOT NULL,controller_id uuid NOT NULL,
 executable_digest text NOT NULL CHECK(executable_digest ~ '^[a-f0-9]{64}$'),
 verification_profile_digest text NOT NULL CHECK(verification_profile_digest ~ '^[a-f0-9]{64}$'),
 approved_by uuid NOT NULL,consent_digest text NOT NULL CHECK(consent_digest ~ '^[a-f0-9]{64}$'),
 valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 PRIMARY KEY(tenant_id,project_id,revision),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id)
);
CREATE TABLE company_private.r58_controller_heads (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,controller_id uuid NOT NULL,generation bigint NOT NULL CHECK(generation>0),
 host_id uuid NOT NULL,host_revision bigint NOT NULL,host_generation bigint NOT NULL,host_boot_id uuid NOT NULL,
 approved_by uuid NOT NULL,enabled boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,project_id,controller_id,generation),
 FOREIGN KEY(tenant_id,project_id,host_id,host_revision,host_generation) REFERENCES company.host_registrations(tenant_id,project_id,id,revision,bound_generation),
 FOREIGN KEY(tenant_id,controller_id) REFERENCES company.principals(tenant_id,id),
 FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id)
);
CREATE UNIQUE INDEX r58_current_controller ON company_private.r58_controller_heads(tenant_id,project_id,controller_id) WHERE enabled;
CREATE UNIQUE INDEX r58_one_lease_policy ON company_private.r58_lease_policies(tenant_id,project_id) WHERE enabled;
CREATE TABLE company_private.r58_workspace_heads (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,workspace_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>=0),head_digest text NOT NULL CHECK(head_digest ~ '^[a-f0-9]{64}$'),
 attestation_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,workspace_id) REFERENCES company.workspaces(tenant_id,id),
 FOREIGN KEY(tenant_id,project_id,attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id)
);
ALTER TABLE company.attempts ADD COLUMN r58_binding_digest text CHECK(r58_binding_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE company.attempts ADD COLUMN r58_head_digest text CHECK(r58_head_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE company.attempts ADD COLUMN r58_policy_revision bigint CHECK(r58_policy_revision>0);
ALTER TABLE company.attempts ADD COLUMN r58_verification_profile_digest text CHECK(r58_verification_profile_digest ~ '^[a-f0-9]{64}$');
CREATE TABLE company_private.r58_launch_capabilities (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,id uuid NOT NULL,
 process_id uuid NOT NULL,tuple jsonb NOT NULL CHECK(jsonb_typeof(tuple)='object'),
 tuple_digest text NOT NULL CHECK(tuple_digest=encode(sha256(convert_to(tuple::text,'UTF8')),'hex')),
 state text NOT NULL CHECK(state IN ('RESERVED','CONSUMED','RUNNING','UNKNOWN_LOCAL')),
 consume_command_id uuid,callback_attestation_id uuid,
 PRIMARY KEY(tenant_id,project_id,id),UNIQUE(tenant_id,project_id,process_id),
 FOREIGN KEY(tenant_id,project_id,process_id) REFERENCES company.process_runs(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,consume_command_id) REFERENCES company.commands(tenant_id,id),
 FOREIGN KEY(tenant_id,project_id,callback_attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id)
);
CREATE TABLE company_private.r58_execution_receipts (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,command_id uuid NOT NULL,
 operation text NOT NULL,target_id uuid NOT NULL,payload jsonb NOT NULL,
 PRIMARY KEY(tenant_id,command_id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id)
);
-- Metadata supplements canonical owners; it never replaces Attempt/Process/Evidence.
CREATE TABLE company_private.r58_patch_receipts (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,task_id uuid NOT NULL,attempt_id uuid NOT NULL,id uuid NOT NULL,
 fence bigint NOT NULL,base_head text NOT NULL,result_head text NOT NULL,patch_digest text NOT NULL,
 tool_request_id uuid NOT NULL,attestation_id uuid NOT NULL,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES company.attempts(tenant_id,project_id,task_id,id),
 FOREIGN KEY(tenant_id,project_id,attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
CREATE TABLE company_private.r58_verification_seals (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,task_id uuid NOT NULL,attempt_id uuid NOT NULL,verification_id uuid NOT NULL,
 patch_id uuid NOT NULL,head_digest text NOT NULL,attestation_id uuid NOT NULL,seal_digest text NOT NULL,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,verification_id),
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,verification_id) REFERENCES company.verification_runs(tenant_id,project_id,task_id,attempt_id,id),
 FOREIGN KEY(tenant_id,project_id,patch_id) REFERENCES company_private.r58_patch_receipts(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,project_id,attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
-- The exact required oracle manifest is independently HUMAN-enrolled, not caller-selected.
CREATE TABLE company_private.r58_verification_profiles (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,profile_digest text NOT NULL,
 oracle_ids jsonb NOT NULL CHECK(jsonb_typeof(oracle_ids)='array' AND jsonb_array_length(oracle_ids)>0),
 approved_by uuid NOT NULL,enabled boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,project_id,profile_digest),
 FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id)
);
CREATE TABLE company_private.r58_evidence_provenance (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,task_id uuid NOT NULL,attempt_id uuid NOT NULL,evidence_id uuid NOT NULL,
 attestation_id uuid NOT NULL,head_digest text NOT NULL,seal_digest text NOT NULL,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,evidence_id),
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,evidence_id) REFERENCES company.evidence(tenant_id,project_id,task_id,attempt_id,id),
 FOREIGN KEY(tenant_id,project_id,attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
CREATE FUNCTION company_private.r58_metadata_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'R58_METADATA_HISTORY_IMMUTABLE'; END IF;
 IF TG_TABLE_NAME='r58_launch_capabilities' THEN
  IF (to_jsonb(OLD)-ARRAY['state','consume_command_id','callback_attestation_id']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['state','consume_command_id','callback_attestation_id'])
  OR NOT ((OLD.state='RESERVED' AND NEW.state='CONSUMED' AND OLD.consume_command_id IS NULL AND NEW.consume_command_id IS NOT NULL AND NEW.callback_attestation_id IS NULL)
  OR (OLD.state='CONSUMED' AND NEW.state IN ('RUNNING','UNKNOWN_LOCAL') AND NEW.consume_command_id=OLD.consume_command_id AND OLD.callback_attestation_id IS NULL AND NEW.callback_attestation_id IS NOT NULL)) THEN RAISE EXCEPTION 'R58_CAPABILITY_IDENTITY_OR_STATE_IMMUTABLE'; END IF;
 ELSIF TG_TABLE_NAME='r58_workspace_heads' THEN
  IF ROW(NEW.tenant_id,NEW.project_id,NEW.workspace_id) IS DISTINCT FROM ROW(OLD.tenant_id,OLD.project_id,OLD.workspace_id) OR NEW.revision<>OLD.revision+1 OR NEW.attestation_id=OLD.attestation_id THEN RAISE EXCEPTION 'R58_HEAD_REVISION_REQUIRED'; END IF;
 ELSE
  IF (to_jsonb(OLD)-'enabled') IS DISTINCT FROM (to_jsonb(NEW)-'enabled') OR OLD.enabled IS NOT TRUE OR NEW.enabled IS NOT FALSE THEN RAISE EXCEPTION 'R58_POLICY_DISABLE_ONLY_CREATE_NEW_REVISION'; END IF;
 END IF;
 RETURN NEW;
END $$;
DO $immutability$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['r58_launch_capabilities','r58_workspace_heads','r58_lease_policies','r58_controller_heads','r58_verification_profiles'] LOOP
  EXECUTE format('CREATE TRIGGER r58_metadata_immutable BEFORE UPDATE OR DELETE ON company_private.%I FOR EACH ROW EXECUTE FUNCTION company_private.r58_metadata_immutable()',t);
 END LOOP;
END $immutability$;
DO $security$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['r58_attestations','r58_lease_policies','r58_controller_heads','r58_workspace_heads','r58_launch_capabilities','r58_execution_receipts','r58_patch_receipts','r58_verification_seals','r58_verification_profiles','r58_evidence_provenance'] LOOP
  EXECUTE format('ALTER TABLE company_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE company_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON company_private.%I FROM PUBLIC',t);
  EXECUTE format('GRANT SELECT ON company_private.%I TO company_execution_functions_r58',t);
  EXECUTE format('CREATE POLICY r58_scope_read ON company_private.%I FOR SELECT TO company_execution_functions_r58 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.tenant_id=%I.tenant_id AND x.project_id=%I.project_id))',t,t,t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['r58_workspace_heads','r58_launch_capabilities','r58_execution_receipts','r58_patch_receipts','r58_verification_seals','r58_evidence_provenance'] LOOP
  EXECUTE format('GRANT INSERT ON company_private.%I TO company_execution_functions_r58',t);
  EXECUTE format('CREATE POLICY r58_scope_insert ON company_private.%I FOR INSERT TO company_execution_functions_r58 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.tenant_id=%I.tenant_id AND x.project_id=%I.project_id))',t,t,t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['r58_attestations','r58_execution_receipts','r58_patch_receipts','r58_verification_seals','r58_evidence_provenance'] LOOP
  EXECUTE format('CREATE TRIGGER r58_immutable BEFORE UPDATE OR DELETE ON company_private.%I FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation()',t);
 END LOOP;
END $security$;
GRANT SELECT ON company_private.request_contexts,company_private.operation_permissions TO company_execution_functions_r58,company_attestation_functions_r58;
CREATE POLICY r58_execution_context ON company_private.request_contexts FOR SELECT TO company_execution_functions_r58,company_attestation_functions_r58 USING(backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54);
CREATE POLICY r58_execution_registry ON company_private.operation_permissions FOR SELECT TO company_execution_functions_r58,company_attestation_functions_r58 USING(true);
GRANT SELECT ON company.principals,company.signer_enrollments TO company_attestation_functions_r58;
GRANT UPDATE(enrollment_revision) ON company.signer_enrollments TO company_attestation_functions_r58;
CREATE POLICY r58_attest_signer ON company.signer_enrollments FOR SELECT TO company_attestation_functions_r58 USING(purpose='TASK_VERIFICATION');
CREATE POLICY r58_attest_signer_lock ON company.signer_enrollments FOR UPDATE TO company_attestation_functions_r58 USING(purpose='TASK_VERIFICATION') WITH CHECK(false);
CREATE POLICY r58_attest_principal ON company.principals FOR SELECT TO company_attestation_functions_r58 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=principals.tenant_id));
GRANT SELECT,INSERT ON company_private.r58_attestations TO company_attestation_functions_r58;
CREATE POLICY r58_attest_scope ON company_private.r58_attestations TO company_attestation_functions_r58
 USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=r58_attestations.tenant_id AND x.project_id=r58_attestations.project_id))
 WITH CHECK(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.tenant_id=r58_attestations.tenant_id AND x.project_id=r58_attestations.project_id AND x.principal_id=r58_attestations.issuer_id));
ROLLBACK;
