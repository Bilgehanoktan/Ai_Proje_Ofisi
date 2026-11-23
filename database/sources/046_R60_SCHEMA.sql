-- Reviewed source candidate, not an authorized migration.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE TABLE company_private.r60_ready_bindings (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,task_id uuid NOT NULL,
 task_revision bigint NOT NULL,plan_revision bigint NOT NULL,head_digest text NOT NULL,
 binding jsonb NOT NULL,binding_digest text NOT NULL CHECK(binding_digest=encode(sha256(convert_to(binding::text,'UTF8')),'hex')),
 command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,task_id,task_revision),
 FOREIGN KEY(tenant_id,project_id,task_id) REFERENCES company.tasks(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
CREATE TABLE company_private.r60_engine_streams (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,engine_session_id uuid NOT NULL,
 task_id uuid NOT NULL,attempt_id uuid NOT NULL,fence bigint NOT NULL,process_id uuid NOT NULL,
 manifest_digest text NOT NULL,task_revision bigint NOT NULL,next_sequence bigint NOT NULL DEFAULT 1 CHECK(next_sequence>0),
 PRIMARY KEY(tenant_id,project_id,engine_session_id),UNIQUE(tenant_id,project_id,process_id),
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES company.attempts(tenant_id,project_id,task_id,id),
 FOREIGN KEY(tenant_id,project_id,process_id) REFERENCES company.process_runs(tenant_id,project_id,id)
);
CREATE TABLE company_private.r60_tool_manifests (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,manifest_digest text NOT NULL,
 manifest jsonb NOT NULL,approved_by uuid NOT NULL,enabled boolean NOT NULL DEFAULT false,
 PRIMARY KEY(tenant_id,project_id,manifest_digest),
 CHECK(manifest_digest=encode(sha256(convert_to(manifest::text,'UTF8')),'hex')),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id)
);
CREATE TABLE company_private.r60_tool_consumptions (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,id uuid NOT NULL,engine_session_id uuid NOT NULL,
 engine_request_id uuid NOT NULL,kernel_request_id uuid NOT NULL,sequence bigint NOT NULL,
 process_id uuid NOT NULL,frame_digest text NOT NULL,frame_bytes bytea NOT NULL,
 state text NOT NULL CHECK(state IN ('CONSUMED','SUCCEEDED','UNKNOWN')),
 effect_attestation_id uuid,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id),
 UNIQUE(tenant_id,project_id,kernel_request_id),UNIQUE(tenant_id,project_id,engine_session_id,sequence),
 UNIQUE(tenant_id,project_id,engine_session_id,engine_request_id),
 CHECK(frame_digest=encode(sha256(frame_bytes),'hex')),
 CHECK(octet_length(frame_bytes) BETWEEN 1 AND 65536),
 CHECK((state='SUCCEEDED')=(effect_attestation_id IS NOT NULL)),
 FOREIGN KEY(tenant_id,project_id,engine_session_id) REFERENCES company_private.r60_engine_streams(tenant_id,project_id,engine_session_id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id),
 FOREIGN KEY(tenant_id,project_id,effect_attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id)
);
CREATE TABLE company_private.r60_lease_extensions (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,id uuid NOT NULL,process_id uuid NOT NULL,
 old_deadline_ns bigint NOT NULL,new_deadline_ns bigint NOT NULL,old_expires_at timestamptz NOT NULL,new_expires_at timestamptz NOT NULL,
 identity jsonb NOT NULL,proposal_digest text NOT NULL,policy_revision bigint NOT NULL,
 state text NOT NULL CHECK(state IN ('PREPARED','COMMITTED','ACTIVE','ABORTED')),
 prepared_attestation_id uuid,active_attestation_id uuid,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id),CHECK(new_deadline_ns>old_deadline_ns AND old_deadline_ns>0),
 CHECK(isfinite(new_expires_at) AND new_expires_at>old_expires_at),
 FOREIGN KEY(tenant_id,project_id,process_id) REFERENCES company.process_runs(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
CREATE UNIQUE INDEX r60_one_pending_extension ON company_private.r60_lease_extensions(tenant_id,project_id,process_id) WHERE state IN ('PREPARED','COMMITTED');
ALTER TABLE company_private.r60_engine_streams ADD FOREIGN KEY(tenant_id,project_id,manifest_digest) REFERENCES company_private.r60_tool_manifests(tenant_id,project_id,manifest_digest);
ALTER TABLE company_private.r60_lease_extensions ADD FOREIGN KEY(tenant_id,project_id,prepared_attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id);
ALTER TABLE company_private.r60_lease_extensions ADD FOREIGN KEY(tenant_id,project_id,active_attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id);
CREATE TABLE company_private.r60_process_reconciliations (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,id uuid NOT NULL,process_id uuid NOT NULL,
 attestation_id uuid NOT NULL,outcome text NOT NULL CHECK(outcome IN ('RUNNING','EXITED','NOT_STARTED')),
 command_id uuid NOT NULL,PRIMARY KEY(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,project_id,process_id) REFERENCES company.process_runs(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,project_id,attestation_id) REFERENCES company_private.r58_attestations(tenant_id,project_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
ROLLBACK;
