-- r53 FIRST-RUN dependency closure; inert fresh catalog candidate, upgrade değildir.

BEGIN;

DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

CREATE SCHEMA company;

CREATE SCHEMA company_private;

SET LOCAL search_path=pg_catalog,company;

CREATE TABLE company.tenants (
 id uuid PRIMARY KEY,
 name text NOT NULL CHECK(length(name) BETWEEN 3 AND 200),
 created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE company.principals (
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 id uuid NOT NULL,
 name text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('HUMAN','AGENT','VERIFIER','WORKER')),
 PRIMARY KEY(tenant_id,id)
);

CREATE TABLE company.memberships (
 tenant_id uuid NOT NULL,
 principal_id uuid NOT NULL,
 role text NOT NULL CHECK(role IN ('OWNER','OPERATOR','VIEWER','WORKER','VERIFIER')),
 PRIMARY KEY(tenant_id,principal_id)
);

CREATE TABLE company.sessions (
 tenant_id uuid NOT NULL,
 id uuid NOT NULL,
 principal_id uuid NOT NULL,
 token_hash text NOT NULL UNIQUE CHECK(token_hash ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 PRIMARY KEY(tenant_id,id)
);

CREATE TABLE company.workspaces (
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 id uuid NOT NULL,
 root_ref text NOT NULL,
 trust_class text NOT NULL CHECK(trust_class IN ('DISPOSABLE_TEST','TRUSTED_LOCAL','UNTRUSTED')),
 PRIMARY KEY(tenant_id,id),
 UNIQUE(tenant_id,root_ref)
);

CREATE TABLE company.projects (
 tenant_id uuid NOT NULL,
 id uuid NOT NULL,
 workspace_id uuid NOT NULL,
 name text NOT NULL CHECK(length(name) BETWEEN 3 AND 200),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 PRIMARY KEY(tenant_id,id)
);

CREATE TABLE company.objectives (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 goal text NOT NULL,
 constraints jsonb NOT NULL CHECK(jsonb_typeof(constraints)='array'),
 expected_outputs jsonb NOT NULL CHECK(jsonb_typeof(expected_outputs)='array'),
 PRIMARY KEY(tenant_id,project_id,id)
);

CREATE TABLE company.plans (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 objective_id uuid NOT NULL,
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 assumptions jsonb NOT NULL DEFAULT '[]',
 acceptance_criteria jsonb NOT NULL CHECK(jsonb_typeof(acceptance_criteria)='array' AND jsonb_array_length(acceptance_criteria)>0),
 PRIMARY KEY(tenant_id,project_id,id)
);

CREATE TABLE company.tasks (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 plan_id uuid NOT NULL,
 title text NOT NULL CHECK(length(title) BETWEEN 3 AND 200),
 role_id text NOT NULL,
 state text NOT NULL DEFAULT 'DRAFT' CHECK(state IN ('DRAFT','READY','RUNNING','WAITING_APPROVAL','VERIFYING','CHANGES_REQUIRED','BLOCKED','ACCEPTED','FAILED','CANCELLED')),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 fencing_epoch bigint NOT NULL DEFAULT 0 CHECK(fencing_epoch>=0),
 active_attempt_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 acceptance_criteria jsonb NOT NULL CHECK(jsonb_typeof(acceptance_criteria)='array' AND jsonb_array_length(acceptance_criteria)>0),
 PRIMARY KEY(tenant_id,project_id,id)
);

CREATE TABLE company.task_dependencies (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 depends_on_task_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,task_id,depends_on_task_id),
 CHECK(task_id<>depends_on_task_id)
);

CREATE TABLE company.attempts (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 id uuid NOT NULL,
 attempt_no integer NOT NULL CHECK(attempt_no>0),
 fencing_epoch bigint NOT NULL CHECK(fencing_epoch>0),
 worker_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN ('CLAIMED','RUNNING','CANCEL_REQUESTED','STOPPED','FAILED','PRODUCED','UNKNOWN_RECOVERY')),
 lease_expires_at timestamptz NOT NULL,
 ended_at timestamptz,
 PRIMARY KEY(tenant_id,project_id,task_id,id),
 UNIQUE(tenant_id,project_id,task_id,attempt_no)
);

CREATE TABLE company.commands (
 tenant_id uuid NOT NULL,
 id uuid NOT NULL,
 principal_id uuid NOT NULL,
 operation text NOT NULL,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 16 AND 128),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{64}$'),
 correlation_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
 result_ref uuid,
 PRIMARY KEY(tenant_id,id),
 UNIQUE(tenant_id,principal_id,operation,idempotency_key)
);

CREATE TABLE company.artifacts (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 id uuid NOT NULL,
 storage_key uuid NOT NULL UNIQUE,
 sha256 text NOT NULL CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 size_bytes bigint NOT NULL CHECK(size_bytes BETWEEN 0 AND 52428800),
 state text NOT NULL CHECK(state IN ('STAGING','AVAILABLE','QUARANTINED')),
 PRIMARY KEY(tenant_id,project_id,task_id,attempt_id,id)
);

CREATE TABLE company.verification_runs (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 id uuid NOT NULL,
 producer_id uuid NOT NULL,
 verifier_id uuid NOT NULL,
 profile_version text NOT NULL,
 build_digest text NOT NULL CHECK(build_digest ~ '^[a-f0-9]{64}$'),
 dirty_digest text NOT NULL CHECK(dirty_digest ~ '^[a-f0-9]{64}$'),
 result text NOT NULL CHECK(result IN ('NOT_RUN','RUNNING','PASS','FAIL','BLOCKED')),
 exit_code integer,
 PRIMARY KEY(tenant_id,project_id,task_id,attempt_id,id),
 CHECK(producer_id<>verifier_id),
 CHECK(result<>'PASS' OR (exit_code IS NOT NULL AND exit_code=0))
);

CREATE TABLE company.evidence (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 id uuid NOT NULL,
 verification_run_id uuid NOT NULL,
 artifact_id uuid NOT NULL,
 command_receipt uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,task_id,attempt_id,id)
);

CREATE TABLE company.acceptance_records (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 id uuid NOT NULL,
 verification_run_id uuid NOT NULL,
 evidence_id uuid NOT NULL,
 accepted_by uuid NOT NULL,
 build_digest text NOT NULL CHECK(build_digest ~ '^[a-f0-9]{64}$'),
 dirty_digest text NOT NULL CHECK(dirty_digest ~ '^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,project_id,task_id,id)
);

CREATE TABLE company.resource_slots (
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 id uuid NOT NULL,
 kind text NOT NULL,
 capacity integer NOT NULL CHECK(capacity>0),
 reserved integer NOT NULL DEFAULT 0 CHECK(reserved>=0 AND reserved<=capacity),
 PRIMARY KEY(tenant_id,id)
);

CREATE TABLE company.outbox (
 event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 aggregate_id uuid NOT NULL,
 aggregate_revision bigint NOT NULL CHECK(aggregate_revision>=0),
 kind text NOT NULL,
 payload jsonb NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz
);

CREATE TABLE company.audit_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 correlation_id uuid NOT NULL,
 actor_id uuid NOT NULL,
 kind text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE company.workflow_instances (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 plan_id uuid NOT NULL,
 logical_run_id uuid NOT NULL,
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{64}$'),
 template_digest text NOT NULL,
 input_digest text NOT NULL,
 policy_digest text NOT NULL,
 state text NOT NULL DEFAULT 'COMPILED' CHECK(state IN ('COMPILED','RUNNING','COMPLETED','FAILED','CANCELLED')),
 PRIMARY KEY(tenant_id,project_id,id),
 UNIQUE(tenant_id,project_id,logical_run_id)
);

CREATE TABLE company.workflow_stage_bindings (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 stage_id text NOT NULL,
 task_id uuid NOT NULL,
 stage_metadata jsonb NOT NULL,
 PRIMARY KEY(tenant_id,project_id,instance_id,stage_id),
 UNIQUE(tenant_id,project_id,task_id)
);

CREATE TABLE company.workflow_compile_requests (
 tenant_id uuid NOT NULL,
 principal_id uuid NOT NULL,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 16 AND 128),
 project_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 payload_digest text NOT NULL,
 PRIMARY KEY(tenant_id,principal_id,idempotency_key)
);

CREATE TABLE company.evaluation_runs (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 authorization_id uuid NOT NULL,
 role_id text NOT NULL,
 fixture_digest text NOT NULL,
 model_digest text NOT NULL,
 source_kind text NOT NULL CHECK(source_kind='DISPOSABLE_TEST'),
 customer_order_id uuid CHECK(customer_order_id IS NULL),
 state text NOT NULL CHECK(state IN ('REQUESTED','AUTHORIZED','RUNNING','MEASURED','REVIEWED','REJECTED')),
 PRIMARY KEY(tenant_id,project_id,id)
);

CREATE TABLE company.agent_qualifications (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 evaluation_run_id uuid NOT NULL,
 role_id text NOT NULL,
 version_binding jsonb NOT NULL,
 approved_by uuid NOT NULL,
 valid_until timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id)
);

CREATE TABLE company.tool_requests (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 request_id uuid NOT NULL,
 payload_digest text NOT NULL,
 receipt_id uuid,
 PRIMARY KEY(tenant_id,attempt_id,request_id)
);

CREATE TABLE company.verifier_receipts (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('TASK_VERIFICATION','EVALUATION')),
 signer_id uuid NOT NULL,
 key_id uuid NOT NULL,
 receipt_digest text NOT NULL,
 signature text NOT NULL,
 PRIMARY KEY(tenant_id,project_id,task_id,attempt_id,id)
);

CREATE TABLE company_private.scope_lock_registry (
 lock_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 rank smallint NOT NULL CHECK(rank BETWEEN 0 AND 5),
 identity_key jsonb NOT NULL UNIQUE CHECK(jsonb_typeof(identity_key)='object'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE company.authority_scope_heads (
 tenant_id uuid NOT NULL REFERENCES company.tenants(id),
 scope_kind text NOT NULL CHECK(scope_kind IN ('TENANT','PROJECT','SESSION')),
 scope_ref uuid NOT NULL,
 project_id uuid,
 session_id uuid,
 epoch bigint NOT NULL DEFAULT 0 CHECK(epoch>=0),
 lock_id bigint NOT NULL UNIQUE REFERENCES company_private.scope_lock_registry(lock_id),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 PRIMARY KEY(tenant_id,scope_kind,scope_ref),
 CHECK((scope_kind='TENANT' AND scope_ref=tenant_id AND project_id IS NULL AND session_id IS NULL)
 OR (scope_kind='PROJECT' AND project_id IS NOT NULL AND scope_ref=project_id AND session_id IS NULL)
 OR (scope_kind='SESSION' AND session_id IS NOT NULL AND scope_ref=session_id AND project_id IS NULL))
);

CREATE TABLE company.project_grants (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 principal_id uuid NOT NULL,
 permission text NOT NULL CHECK(length(permission) BETWEEN 1 AND 160),
 revision bigint NOT NULL DEFAULT 0 CHECK(revision>=0),
 valid_from timestamptz NOT NULL,
 valid_until timestamptz NOT NULL,
 revoked_at timestamptz,
 granted_by uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,principal_id,permission),
 CHECK(valid_until>valid_from)
);

CREATE TABLE company_private.operation_permissions (
 operation_id text PRIMARY KEY,
 permission text NOT NULL,
 scope_kind text NOT NULL CHECK(scope_kind IN ('TENANT','PROJECT','SELF_SESSION','SPECIAL')),
 execution_class text NOT NULL CHECK(execution_class IN ('QUERY','COMMAND','STREAM','INTERNAL','SPECIAL')),
 policy_revision bigint NOT NULL CHECK(policy_revision>=0),
 approved_policy_digest text CHECK(approved_policy_digest ~ '^[a-f0-9]{64}$')
);

CREATE TABLE company_private.request_contexts (
 backend_pid integer NOT NULL,
 transaction_id xid8 NOT NULL,
 request_nonce uuid NOT NULL,
 db_login name NOT NULL,
 tenant_id uuid NOT NULL,
 project_id uuid,
 principal_id uuid NOT NULL,
 session_id uuid NOT NULL,
 operation_id text NOT NULL,
 tenant_epoch bigint NOT NULL CHECK(tenant_epoch>=0),
 project_epoch bigint CHECK(project_epoch>=0),
 session_epoch bigint NOT NULL CHECK(session_epoch>=0),
 writer_generation bigint NOT NULL CHECK(writer_generation>=0),
 authenticated_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 PRIMARY KEY(backend_pid,transaction_id),
 UNIQUE(request_nonce),
 CHECK(expires_at>authenticated_at)
);

CREATE TABLE company.clock_epochs (
 tenant_id uuid NOT NULL REFERENCES company.tenants(id),
 epoch_id uuid NOT NULL,
 supervisor_id uuid NOT NULL,
 host_boot_id uuid NOT NULL,
 writer_generation bigint NOT NULL CHECK(writer_generation>=0),
 policy_digest text NOT NULL CHECK(policy_digest ~ '^[a-f0-9]{64}$'),
 registered_at timestamptz NOT NULL,
 invalidated_at timestamptz,
 PRIMARY KEY(tenant_id,epoch_id)
);

CREATE TABLE company.clock_samples (
 tenant_id uuid NOT NULL,
 epoch_id uuid NOT NULL,
 sample_id uuid NOT NULL,
 sampled_at timestamptz NOT NULL,
 utc_lower_bound timestamptz NOT NULL,
 utc_upper_bound timestamptz NOT NULL,
 boottime_ns numeric(20,0) NOT NULL CHECK(boottime_ns>=0),
 uncertainty_ms bigint NOT NULL CHECK(uncertainty_ms>=0),
 sample_digest text NOT NULL CHECK(sample_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(tenant_id,epoch_id,sample_id),
 CHECK(utc_upper_bound>=utc_lower_bound)
);

CREATE TABLE company.secret_references (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>=0),
 backend_locator text NOT NULL CHECK(length(backend_locator) BETWEEN 1 AND 256),
 backend_version text NOT NULL,
 metadata_digest text NOT NULL CHECK(metadata_digest ~ '^[a-f0-9]{64}$'),
 state text NOT NULL CHECK(state IN ('REGISTERED_METADATA','REVOKED')),
 command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id,revision)
);

CREATE TABLE company.policy_decisions (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('DELIVERY_GATE','MEMORY_WRITE')),
 operation_id text NOT NULL,
 registry_digest text NOT NULL CHECK(registry_digest ~ '^[a-f0-9]{64}$'),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{64}$'),
 binding_digest text NOT NULL CHECK(binding_digest ~ '^[a-f0-9]{64}$'),
 source_refs jsonb NOT NULL CHECK(jsonb_typeof(source_refs)='array'),
 policy_digest text NOT NULL,
 authority_epoch bigint NOT NULL CHECK(authority_epoch>=0),
 revoked_at timestamptz,
 revoked_by uuid,
 result text NOT NULL CHECK(result IN ('ALLOW','DENY','BLOCKED')),
 issued_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL CHECK(expires_at>issued_at),
 source_task_id uuid,
 source_attempt_id uuid,
 source_artifact_id uuid,
 command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id),
 CHECK((source_task_id IS NULL AND source_attempt_id IS NULL AND source_artifact_id IS NULL) OR (source_task_id IS NOT NULL AND source_attempt_id IS NOT NULL AND source_artifact_id IS NOT NULL)),
 CHECK(purpose<>'MEMORY_WRITE' OR source_artifact_id IS NOT NULL),
 CHECK((revoked_at IS NULL)=(revoked_by IS NULL))
);

CREATE TABLE company.license_records (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>=0),
 component_identity text NOT NULL,
 source_commit text NOT NULL,
 license_text_digest text NOT NULL CHECK(license_text_digest ~ '^[a-f0-9]{64}$'),
 decision text NOT NULL CHECK(decision IN ('UNKNOWN','PILOT_ALLOWED','DENIED')),
 reviewed_by uuid,
 command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,id,revision),
 UNIQUE(tenant_id,project_id,component_identity,source_commit,revision),
 CHECK(decision='UNKNOWN' OR reviewed_by IS NOT NULL)
);

CREATE TABLE company.host_registrations (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>=0),
 host_identity_digest text NOT NULL CHECK(host_identity_digest ~ '^[a-f0-9]{64}$'),
 attestation_digest text NOT NULL CHECK(attestation_digest ~ '^[a-f0-9]{64}$'),
 state text NOT NULL CHECK(state IN ('REGISTERED_NOT_ACTIVE','BOUND_NOT_LEASED','REVOKED')),
 command_id uuid NOT NULL,
 bound_generation bigint,
 binding_command_id uuid,
 CHECK((state='BOUND_NOT_LEASED' AND bound_generation IS NOT NULL AND bound_generation>0 AND binding_command_id IS NOT NULL)
 OR (state='REGISTERED_NOT_ACTIVE' AND bound_generation IS NULL AND binding_command_id IS NULL)
 OR (state='REVOKED' AND bound_generation IS NULL AND binding_command_id IS NULL)),
 PRIMARY KEY(tenant_id,project_id,id,revision),
 UNIQUE(tenant_id,project_id,id,revision,bound_generation),
 UNIQUE(tenant_id,project_id,bound_generation),
 UNIQUE(tenant_id,binding_command_id)
);

CREATE TABLE company_private.installation_bootstrap_control (
 installation_id uuid PRIMARY KEY,
 generation bigint NOT NULL CHECK(generation>0),
 state text NOT NULL CHECK(state IN ('ARMED','CONSUMED','CANCELLED')),
 expected_tenant_id uuid NOT NULL UNIQUE,
 expected_project_id uuid NOT NULL,
 expected_workspace_id uuid NOT NULL,
 expected_human_id uuid NOT NULL,
 nonce_hash text NOT NULL UNIQUE CHECK(nonce_hash ~ '^[a-f0-9]{64}$'),
 payload_digest text NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{64}$'),
 setup_manifest_digest text NOT NULL CHECK(setup_manifest_digest ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,
 consumed_command_id uuid,
 lock_id bigint NOT NULL UNIQUE REFERENCES company_private.scope_lock_registry(lock_id),
 CHECK((state='CONSUMED')=(consumed_command_id IS NOT NULL))
);

CREATE TABLE company_private.bootstrap_receipts (
 installation_id uuid PRIMARY KEY REFERENCES company_private.installation_bootstrap_control(installation_id),
 generation bigint NOT NULL,
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 command_id uuid NOT NULL,
 payload_digest text NOT NULL,
 setup_manifest_digest text NOT NULL,
 initial_grants_digest text NOT NULL,
 accepted_human_id uuid NOT NULL
);

CREATE TABLE company_private.bootstrap_request_contexts (
 backend_pid integer NOT NULL,
 transaction_id xid8 NOT NULL,
 db_login name NOT NULL,
 context_nonce uuid NOT NULL UNIQUE,
 installation_id uuid NOT NULL,
 generation bigint NOT NULL,
 manifest_digest text NOT NULL,
 human_proof_digest text NOT NULL,
 expires_at timestamptz NOT NULL,
 PRIMARY KEY(backend_pid,transaction_id)
);

CREATE TABLE company.governance_decision_heads (
 tenant_id uuid NOT NULL,
 scope_kind text NOT NULL CHECK(scope_kind IN ('TENANT','PROJECT')),
 scope_ref uuid NOT NULL,
 target_project_id uuid,
 decision_kind text NOT NULL,
 operation text NOT NULL,
 logical_target_digest text NOT NULL CHECK(logical_target_digest ~ '^[a-f0-9]{64}$'),
 revision bigint NOT NULL CHECK(revision>0),
 decision_state text NOT NULL CHECK(decision_state IN ('APPROVED','REJECTED','REVOKED')),
 decision_project_id uuid NOT NULL,
 decision_task_id uuid NOT NULL,
 decision_attempt_id uuid NOT NULL,
 decision_artifact_id uuid NOT NULL,
 command_id uuid NOT NULL,
 decision_digest text NOT NULL CHECK(decision_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY(tenant_id,scope_kind,scope_ref,decision_kind,operation,logical_target_digest),
 CHECK((scope_kind='TENANT' AND scope_ref=tenant_id AND target_project_id IS NULL)
 OR (scope_kind='PROJECT' AND scope_ref=target_project_id AND target_project_id IS NOT NULL))
);

CREATE TABLE company.budget_versions (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 budget_id uuid NOT NULL,
 revision bigint NOT NULL CHECK(revision>0),
 id uuid NOT NULL,
 limit_minor bigint NOT NULL CHECK(limit_minor BETWEEN 0 AND 9007199254740991),
 currency text NOT NULL CHECK(currency='TRY'),
 environment_policy_digest text NOT NULL,
 source_task_id uuid NOT NULL,
 source_attempt_id uuid NOT NULL,
 approval_artifact_id uuid NOT NULL,
 approved_by uuid NOT NULL,
 command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,budget_id,revision),
 UNIQUE(tenant_id,project_id,id),
 UNIQUE(tenant_id,approval_artifact_id)
);

CREATE TABLE company.budget_reservations (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 budget_id uuid NOT NULL,
 budget_revision bigint NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 attempt_fencing_epoch bigint NOT NULL,
 semantic_key text NOT NULL,
 payload_digest text NOT NULL,
 admission_artifact_id uuid NOT NULL,
 amount_minor bigint NOT NULL CHECK(amount_minor BETWEEN 0 AND 9007199254740991),
 settled_minor bigint NOT NULL DEFAULT 0 CHECK(settled_minor BETWEEN 0 AND 9007199254740991),
 released_minor bigint NOT NULL DEFAULT 0 CHECK(released_minor BETWEEN 0 AND amount_minor),
 state text NOT NULL CHECK(state IN ('RESERVED','SETTLED','RELEASED','OVERDRAWN','UNKNOWN_USAGE')),
 revision bigint NOT NULL DEFAULT 0,
 command_id uuid NOT NULL,
 settlement_command_id uuid,
 release_command_id uuid,
 release_op_id uuid,
 PRIMARY KEY(tenant_id,project_id,id),
 UNIQUE(tenant_id,project_id,budget_id,semantic_key),
 UNIQUE(tenant_id,project_id,admission_artifact_id),
 UNIQUE(tenant_id,project_id,id,task_id,attempt_id,attempt_fencing_epoch),
 UNIQUE(tenant_id,release_op_id),
 CHECK((release_command_id IS NULL)=(release_op_id IS NULL)),
 CHECK((state IN ('SETTLED','RELEASED','OVERDRAWN'))=(settlement_command_id IS NOT NULL)),
 CHECK((state='RELEASED')=(release_command_id IS NOT NULL)),
 CHECK(state NOT IN ('RESERVED','UNKNOWN_USAGE') OR (settled_minor=0 AND released_minor=0)),
 CHECK(state<>'RELEASED' OR released_minor=amount_minor-settled_minor),
 CHECK((state='OVERDRAWN' AND settled_minor>amount_minor AND released_minor=0)
 OR (state<>'OVERDRAWN' AND settled_minor<=amount_minor AND released_minor<=amount_minor-settled_minor))
);

CREATE TABLE company.process_runs (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 id uuid NOT NULL,
 task_id uuid NOT NULL,
 attempt_id uuid NOT NULL,
 attempt_fencing_epoch bigint NOT NULL,
 worker_lease_id uuid NOT NULL,
 worker_id uuid NOT NULL,
 qualification_id uuid NOT NULL,
 lease_expires_at timestamptz NOT NULL,
 workspace_id uuid NOT NULL,
 host_registration_id uuid NOT NULL,
 host_registration_revision bigint NOT NULL,
 host_generation bigint NOT NULL CHECK(host_generation>0),
 controller_id uuid NOT NULL,
 controller_generation bigint NOT NULL CHECK(controller_generation>0),
 kind text NOT NULL CHECK(kind IN ('CHECK_SUITE','MUTANT_SUITE','RESTORE_TEST','TASK_EXECUTION')),
 state text NOT NULL CHECK(state IN ('LEASED','REQUESTED','STARTING','RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','UNKNOWN_LOCAL','FAILED_NOT_STARTED')),
 reservation_id uuid NOT NULL,
 verification_run_id uuid,
 manifest_artifact_id uuid NOT NULL,
 manifest_digest text NOT NULL,
 semantic_run_digest text NOT NULL CHECK(semantic_run_digest ~ '^[a-f0-9]{64}$'),
 start_command_id uuid NOT NULL,
 stop_command_id uuid,
 stop_artifact_id uuid,
 release_command_id uuid,
 revision bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,project_id,id),
 UNIQUE(tenant_id,project_id,worker_lease_id),
 UNIQUE(tenant_id,project_id,kind,semantic_run_digest),
 UNIQUE(tenant_id,project_id,reservation_id),
 UNIQUE(tenant_id,project_id,verification_run_id),
 UNIQUE(tenant_id,project_id,id,task_id,attempt_id,attempt_fencing_epoch,controller_generation)
);

CREATE TABLE company.resource_claims (
 tenant_id uuid NOT NULL,
 project_id uuid NOT NULL,
 process_run_id uuid NOT NULL,
 slot_id uuid NOT NULL,
 units integer NOT NULL CHECK(units>0),
 state text NOT NULL CHECK(state IN ('HELD','RELEASED')),
 revision bigint NOT NULL DEFAULT 0,
 release_command_id uuid,
 PRIMARY KEY(tenant_id,project_id,process_run_id,slot_id),
 CHECK((state='RELEASED')=(release_command_id IS NOT NULL))
);

ALTER TABLE company.attempts ADD CONSTRAINT attempt_fencing_binding_unique
 UNIQUE(tenant_id,project_id,task_id,id,fencing_epoch);

ALTER TABLE company.attempts ADD COLUMN admission_qualification_id uuid;

ALTER TABLE company.tool_requests ADD COLUMN request_fencing_epoch bigint
 CHECK(request_fencing_epoch>0);

ALTER TABLE company.objectives ADD COLUMN created_by uuid;

ALTER TABLE company.plans ADD COLUMN objective_review_command_id uuid;

ALTER TABLE company.attempts ADD COLUMN handoff_source_attempt_id uuid;

ALTER TABLE company.attempts ADD COLUMN handoff_artifact_id uuid;

ALTER TABLE company.attempts ADD COLUMN handoff_digest text;

ALTER TABLE company.attempts ADD CONSTRAINT r50_handoff_columns CHECK
 ((handoff_source_attempt_id IS NULL AND handoff_artifact_id IS NULL AND handoff_digest IS NULL)
 OR (handoff_source_attempt_id IS NOT NULL AND handoff_artifact_id IS NOT NULL AND handoff_digest IS NOT NULL AND handoff_digest ~ '^[a-f0-9]{64}$'));

ALTER TABLE company.projects ADD COLUMN host_registration_id uuid;

ALTER TABLE company.projects ADD COLUMN host_registration_revision bigint;

ALTER TABLE company.projects ADD COLUMN instance_generation bigint NOT NULL DEFAULT 0 CHECK(instance_generation>=0);

ALTER TABLE company.projects ADD CONSTRAINT r50_host_columns CHECK
 ((host_registration_id IS NULL AND host_registration_revision IS NULL)
 OR (host_registration_id IS NOT NULL AND host_registration_revision IS NOT NULL AND instance_generation>0));

ALTER TABLE company.project_grants ADD COLUMN secret_reference_id uuid;

ALTER TABLE company.project_grants ADD COLUMN secret_reference_revision bigint;

ALTER TABLE company.verification_runs ADD COLUMN source_report_artifact_id uuid;

ALTER TABLE company.verification_runs ADD COLUMN admission_manifest_artifact_id uuid;

ALTER TABLE company.agent_qualifications ADD COLUMN evaluation_task_id uuid;

ALTER TABLE company.agent_qualifications ADD COLUMN evaluation_attempt_id uuid;

ALTER TABLE company.agent_qualifications ADD COLUMN evaluation_evidence_id uuid;

ALTER TABLE company.agent_qualifications ADD CONSTRAINT r50_qualification_evidence_columns CHECK
 ((evaluation_task_id IS NULL AND evaluation_attempt_id IS NULL AND evaluation_evidence_id IS NULL)
 OR (evaluation_task_id IS NOT NULL AND evaluation_attempt_id IS NOT NULL AND evaluation_evidence_id IS NOT NULL));

ALTER TABLE company.project_grants ADD COLUMN grant_id uuid;

ALTER TABLE company.project_grants ADD COLUMN parent_grant_id uuid;

ALTER TABLE company.project_grants ADD COLUMN task_scope_id uuid;

ALTER TABLE company.project_grants ADD COLUMN base_permission text;

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_identity UNIQUE(tenant_id,project_id,grant_id);

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_codec CHECK
 ((task_scope_id IS NULL AND (base_permission IS NULL OR base_permission=permission))
 OR (task_scope_id IS NOT NULL AND grant_id IS NOT NULL AND base_permission IS NOT NULL
 AND base_permission NOT LIKE 'task:%' AND base_permission NOT LIKE '%*%'
 AND permission='task:'||task_scope_id::text||':'||base_permission));

ALTER TABLE company.project_grants ADD CONSTRAINT r50_secret_grant_columns CHECK
 ((secret_reference_id IS NULL AND secret_reference_revision IS NULL
 AND COALESCE(base_permission,permission) NOT LIKE 'secret.read:%')
 OR (secret_reference_id IS NOT NULL AND secret_reference_revision IS NOT NULL
 AND COALESCE(base_permission,permission)='secret.read:'||secret_reference_id::text||':'||secret_reference_revision::text));

ALTER TABLE company.project_grants ADD COLUMN grant_authorization_artifact_id uuid;

ALTER TABLE company.project_grants ADD COLUMN authorization_task_id uuid;

ALTER TABLE company.project_grants ADD COLUMN authorization_attempt_id uuid;

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_mandate_once UNIQUE(tenant_id,grant_authorization_artifact_id);

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_mandate_tuple CHECK
 ((grant_authorization_artifact_id IS NULL AND authorization_task_id IS NULL AND authorization_attempt_id IS NULL)
 OR (grant_authorization_artifact_id IS NOT NULL AND authorization_task_id IS NOT NULL AND authorization_attempt_id IS NOT NULL));

ALTER TABLE company.evaluation_runs ADD COLUMN subject_principal_id uuid;

ALTER TABLE company.evaluation_runs ADD CONSTRAINT r52_evaluation_subject_role UNIQUE(tenant_id,project_id,id,subject_principal_id,role_id);

ALTER TABLE company.agent_qualifications ADD COLUMN subject_principal_id uuid;

ALTER TABLE company.agent_qualifications ADD CONSTRAINT r52_qualification_subject UNIQUE(tenant_id,project_id,id,subject_principal_id);

ALTER TABLE company.memberships ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.sessions ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.projects ADD FOREIGN KEY(tenant_id,workspace_id) REFERENCES workspaces(tenant_id,id);

ALTER TABLE company.objectives ADD FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id);

ALTER TABLE company.plans ADD FOREIGN KEY(tenant_id,project_id,objective_id) REFERENCES objectives(tenant_id,project_id,id);

ALTER TABLE company.tasks ADD FOREIGN KEY(tenant_id,project_id,plan_id) REFERENCES plans(tenant_id,project_id,id);

ALTER TABLE company.task_dependencies ADD FOREIGN KEY(tenant_id,project_id,task_id) REFERENCES tasks(tenant_id,project_id,id);

ALTER TABLE company.task_dependencies ADD FOREIGN KEY(tenant_id,project_id,depends_on_task_id) REFERENCES tasks(tenant_id,project_id,id);

ALTER TABLE company.attempts ADD FOREIGN KEY(tenant_id,project_id,task_id) REFERENCES tasks(tenant_id,project_id,id);

ALTER TABLE company.attempts ADD FOREIGN KEY(tenant_id,worker_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.tasks ADD CONSTRAINT active_attempt_scope FOREIGN KEY(tenant_id,project_id,id,active_attempt_id)
 REFERENCES attempts(tenant_id,project_id,task_id,id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE company.commands ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.artifacts ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES attempts(tenant_id,project_id,task_id,id);

ALTER TABLE company.verification_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES attempts(tenant_id,project_id,task_id,id);

ALTER TABLE company.verification_runs ADD FOREIGN KEY(tenant_id,producer_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.verification_runs ADD FOREIGN KEY(tenant_id,verifier_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.evidence ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,verification_run_id) REFERENCES verification_runs(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.evidence ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,artifact_id) REFERENCES artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.evidence ADD FOREIGN KEY(tenant_id,command_receipt) REFERENCES commands(tenant_id,id);

ALTER TABLE company.acceptance_records ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,verification_run_id) REFERENCES verification_runs(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.acceptance_records ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,evidence_id) REFERENCES evidence(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.acceptance_records ADD FOREIGN KEY(tenant_id,accepted_by) REFERENCES principals(tenant_id,id);

ALTER TABLE company.outbox ADD FOREIGN KEY(tenant_id,project_id) REFERENCES projects(tenant_id,id);

ALTER TABLE company.audit_events ADD FOREIGN KEY(tenant_id,actor_id) REFERENCES principals(tenant_id,id);

ALTER TABLE company.workflow_instances ADD FOREIGN KEY(tenant_id,project_id,plan_id) REFERENCES company.plans(tenant_id,project_id,id);

ALTER TABLE company.workflow_stage_bindings ADD FOREIGN KEY(tenant_id,project_id,instance_id) REFERENCES company.workflow_instances(tenant_id,project_id,id);

ALTER TABLE company.workflow_stage_bindings ADD FOREIGN KEY(tenant_id,project_id,task_id) REFERENCES company.tasks(tenant_id,project_id,id);

ALTER TABLE company.workflow_compile_requests ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.workflow_compile_requests ADD FOREIGN KEY(tenant_id,project_id,instance_id) REFERENCES company.workflow_instances(tenant_id,project_id,id);

ALTER TABLE company.evaluation_runs ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.agent_qualifications ADD FOREIGN KEY(tenant_id,project_id,evaluation_run_id) REFERENCES company.evaluation_runs(tenant_id,project_id,id);

ALTER TABLE company.agent_qualifications ADD FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.tool_requests ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES company.attempts(tenant_id,project_id,task_id,id);

ALTER TABLE company.verifier_receipts ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES company.attempts(tenant_id,project_id,task_id,id);

ALTER TABLE company.verifier_receipts ADD FOREIGN KEY(tenant_id,signer_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.authority_scope_heads ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.authority_scope_heads ADD FOREIGN KEY(tenant_id,session_id) REFERENCES company.sessions(tenant_id,id);

ALTER TABLE company.project_grants ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.project_grants ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES company.memberships(tenant_id,principal_id);

ALTER TABLE company.project_grants ADD FOREIGN KEY(tenant_id,granted_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company_private.request_contexts ADD FOREIGN KEY(operation_id) REFERENCES company_private.operation_permissions(operation_id);

ALTER TABLE company_private.request_contexts ADD FOREIGN KEY(tenant_id,session_id) REFERENCES company.sessions(tenant_id,id);

ALTER TABLE company_private.request_contexts ADD FOREIGN KEY(tenant_id,principal_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company_private.request_contexts ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.clock_epochs ADD FOREIGN KEY(tenant_id,supervisor_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.clock_samples ADD FOREIGN KEY(tenant_id,epoch_id) REFERENCES company.clock_epochs(tenant_id,epoch_id);

ALTER TABLE company.attempts ADD CONSTRAINT r49_attempt_qualification_fk
 FOREIGN KEY (tenant_id,project_id,admission_qualification_id)
 REFERENCES company.agent_qualifications(tenant_id,project_id,id);

ALTER TABLE company.tool_requests ADD CONSTRAINT r49_tool_attempt_epoch_fk
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,request_fencing_epoch)
 REFERENCES company.attempts(tenant_id,project_id,task_id,id,fencing_epoch);

ALTER TABLE company.secret_references ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.secret_references ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.policy_decisions ADD FOREIGN KEY(tenant_id,project_id,source_task_id,source_attempt_id,source_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.policy_decisions ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.policy_decisions ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.policy_decisions ADD FOREIGN KEY(tenant_id,revoked_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.license_records ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.license_records ADD FOREIGN KEY(tenant_id,reviewed_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.license_records ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.objectives ADD CONSTRAINT r50_objective_creator_fk
 FOREIGN KEY(tenant_id,created_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.plans ADD CONSTRAINT r50_plan_objective_review_fk
 FOREIGN KEY(tenant_id,objective_review_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.attempts ADD CONSTRAINT r50_handoff_artifact_fk
 FOREIGN KEY(tenant_id,project_id,task_id,handoff_source_attempt_id,handoff_artifact_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.project_grants ADD CONSTRAINT r50_secret_grant_fk
 FOREIGN KEY(tenant_id,project_id,secret_reference_id,secret_reference_revision)
 REFERENCES company.secret_references(tenant_id,project_id,id,revision);

ALTER TABLE company.verification_runs ADD CONSTRAINT r50_report_artifact_fk
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,source_report_artifact_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.verification_runs ADD CONSTRAINT r50_admission_manifest_fk
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,admission_manifest_artifact_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.agent_qualifications ADD CONSTRAINT r50_qualification_evidence_fk
 FOREIGN KEY(tenant_id,project_id,evaluation_task_id,evaluation_attempt_id,evaluation_evidence_id)
 REFERENCES company.evidence(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.tool_requests ADD CONSTRAINT r50_patch_receipt_artifact_fk
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,receipt_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.host_registrations ADD FOREIGN KEY(tenant_id,binding_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.host_registrations ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.host_registrations ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.projects ADD CONSTRAINT r50_project_host_fk
 FOREIGN KEY(tenant_id,id,host_registration_id,host_registration_revision,instance_generation)
 REFERENCES company.host_registrations(tenant_id,project_id,id,revision,bound_generation);

ALTER TABLE company_private.installation_bootstrap_control ADD FOREIGN KEY(expected_tenant_id,consumed_command_id) REFERENCES company.commands(tenant_id,id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE company_private.bootstrap_receipts ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company_private.bootstrap_receipts ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company_private.bootstrap_receipts ADD FOREIGN KEY(tenant_id,accepted_human_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company_private.bootstrap_request_contexts ADD FOREIGN KEY(installation_id) REFERENCES company_private.installation_bootstrap_control(installation_id);

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_parent FOREIGN KEY(tenant_id,project_id,parent_grant_id) REFERENCES company.project_grants(tenant_id,project_id,grant_id);

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_task FOREIGN KEY(tenant_id,project_id,task_scope_id) REFERENCES company.tasks(tenant_id,project_id,id);

ALTER TABLE company.project_grants ADD CONSTRAINT r51_grant_mandate_fk FOREIGN KEY(tenant_id,project_id,authorization_task_id,authorization_attempt_id,grant_authorization_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.governance_decision_heads ADD FOREIGN KEY(tenant_id) REFERENCES company.tenants(id);

ALTER TABLE company.governance_decision_heads ADD FOREIGN KEY(tenant_id,target_project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.governance_decision_heads ADD FOREIGN KEY(tenant_id,decision_project_id,decision_task_id,decision_attempt_id,decision_artifact_id)
 REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.governance_decision_heads ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.budget_versions ADD FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id);

ALTER TABLE company.budget_versions ADD FOREIGN KEY(tenant_id,project_id,source_task_id,source_attempt_id,approval_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.budget_versions ADD FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.budget_versions ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,project_id,budget_id,budget_revision) REFERENCES company.budget_versions(tenant_id,project_id,budget_id,revision);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,attempt_fencing_epoch) REFERENCES company.attempts(tenant_id,project_id,task_id,id,fencing_epoch);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,admission_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,settlement_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.budget_reservations ADD FOREIGN KEY(tenant_id,release_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,attempt_fencing_epoch) REFERENCES company.attempts(tenant_id,project_id,task_id,id,fencing_epoch);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,reservation_id,task_id,attempt_id,attempt_fencing_epoch) REFERENCES company.budget_reservations(tenant_id,project_id,id,task_id,attempt_id,attempt_fencing_epoch);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,qualification_id) REFERENCES company.agent_qualifications(tenant_id,project_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,worker_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,controller_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,workspace_id) REFERENCES company.workspaces(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,host_registration_id,host_registration_revision,host_generation) REFERENCES company.host_registrations(tenant_id,project_id,id,revision,bound_generation);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,verification_run_id) REFERENCES company.verification_runs(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,manifest_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,project_id,task_id,attempt_id,stop_artifact_id) REFERENCES company.artifacts(tenant_id,project_id,task_id,attempt_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,start_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,stop_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.process_runs ADD FOREIGN KEY(tenant_id,release_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.resource_claims ADD FOREIGN KEY(tenant_id,project_id,process_run_id) REFERENCES company.process_runs(tenant_id,project_id,id);

ALTER TABLE company.resource_claims ADD FOREIGN KEY(tenant_id,slot_id) REFERENCES company.resource_slots(tenant_id,id);

ALTER TABLE company.resource_claims ADD FOREIGN KEY(tenant_id,release_command_id) REFERENCES company.commands(tenant_id,id);

ALTER TABLE company.evaluation_runs ADD CONSTRAINT r52_evaluation_subject_fk FOREIGN KEY(tenant_id,subject_principal_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.agent_qualifications ADD CONSTRAINT r52_qualification_subject_fk FOREIGN KEY(tenant_id,project_id,evaluation_run_id,subject_principal_id,role_id) REFERENCES company.evaluation_runs(tenant_id,project_id,id,subject_principal_id,role_id);

ALTER TABLE company.attempts ADD CONSTRAINT r52_attempt_qualified_subject FOREIGN KEY(tenant_id,project_id,admission_qualification_id,worker_id) REFERENCES company.agent_qualifications(tenant_id,project_id,id,subject_principal_id);

ALTER TABLE company.process_runs ADD CONSTRAINT r52_process_qualified_subject FOREIGN KEY(tenant_id,project_id,qualification_id,worker_id) REFERENCES company.agent_qualifications(tenant_id,project_id,id,subject_principal_id);

ALTER TABLE company.tenants ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.tenants FORCE ROW LEVEL SECURITY;

CREATE INDEX project_grants_principal ON company.project_grants(tenant_id,principal_id,project_id);

ALTER TABLE company.secret_references ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.secret_references FORCE ROW LEVEL SECURITY;

ALTER TABLE company.policy_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.policy_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.license_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.license_records FORCE ROW LEVEL SECURITY;

ALTER TABLE company.host_registrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.host_registrations FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.installation_bootstrap_control ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.installation_bootstrap_control FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_receipts FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_request_contexts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_request_contexts FORCE ROW LEVEL SECURITY;

ALTER TABLE company.governance_decision_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.governance_decision_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE company.budget_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.budget_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.budget_reservations ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.budget_reservations FORCE ROW LEVEL SECURITY;

ALTER TABLE company.process_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.process_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE company.resource_claims ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.resource_claims FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.request_contexts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.request_contexts FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.operation_permissions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.operation_permissions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE company.authority_scope_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.authority_scope_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE company.project_grants ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.project_grants FORCE ROW LEVEL SECURITY;

ALTER TABLE company.tenants ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.tenants FORCE ROW LEVEL SECURITY;

ALTER TABLE company.principals ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.principals FORCE ROW LEVEL SECURITY;

ALTER TABLE company.memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.memberships FORCE ROW LEVEL SECURITY;

ALTER TABLE company.sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.workspaces ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.workspaces FORCE ROW LEVEL SECURITY;

ALTER TABLE company.projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.projects FORCE ROW LEVEL SECURITY;

ALTER TABLE company.objectives ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.objectives FORCE ROW LEVEL SECURITY;

ALTER TABLE company.plans ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.plans FORCE ROW LEVEL SECURITY;

ALTER TABLE company.tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.tasks FORCE ROW LEVEL SECURITY;

ALTER TABLE company.task_dependencies ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.task_dependencies FORCE ROW LEVEL SECURITY;

ALTER TABLE company.attempts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.attempts FORCE ROW LEVEL SECURITY;

ALTER TABLE company.commands ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.commands FORCE ROW LEVEL SECURITY;

ALTER TABLE company.artifacts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.artifacts FORCE ROW LEVEL SECURITY;

ALTER TABLE company.verification_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.verification_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE company.evidence ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.evidence FORCE ROW LEVEL SECURITY;

ALTER TABLE company.acceptance_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.acceptance_records FORCE ROW LEVEL SECURITY;

ALTER TABLE company.resource_slots ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.resource_slots FORCE ROW LEVEL SECURITY;

ALTER TABLE company.outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.outbox FORCE ROW LEVEL SECURITY;

ALTER TABLE company.audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.audit_events FORCE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_instances ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_instances FORCE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_stage_bindings ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_stage_bindings FORCE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_compile_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.workflow_compile_requests FORCE ROW LEVEL SECURITY;

ALTER TABLE company.evaluation_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.evaluation_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE company.agent_qualifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.agent_qualifications FORCE ROW LEVEL SECURITY;

ALTER TABLE company.tool_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.tool_requests FORCE ROW LEVEL SECURITY;

ALTER TABLE company.verifier_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.verifier_receipts FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.scope_lock_registry ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.scope_lock_registry FORCE ROW LEVEL SECURITY;

ALTER TABLE company.authority_scope_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.authority_scope_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE company.project_grants ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.project_grants FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.operation_permissions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.operation_permissions FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.request_contexts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.request_contexts FORCE ROW LEVEL SECURITY;

ALTER TABLE company.clock_epochs ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.clock_epochs FORCE ROW LEVEL SECURITY;

ALTER TABLE company.clock_samples ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.clock_samples FORCE ROW LEVEL SECURITY;

ALTER TABLE company.secret_references ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.secret_references FORCE ROW LEVEL SECURITY;

ALTER TABLE company.policy_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.policy_decisions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.license_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.license_records FORCE ROW LEVEL SECURITY;

ALTER TABLE company.host_registrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.host_registrations FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.installation_bootstrap_control ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.installation_bootstrap_control FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_receipts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_receipts FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_request_contexts ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.bootstrap_request_contexts FORCE ROW LEVEL SECURITY;

ALTER TABLE company.governance_decision_heads ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.governance_decision_heads FORCE ROW LEVEL SECURITY;

ALTER TABLE company.budget_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.budget_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE company.budget_reservations ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.budget_reservations FORCE ROW LEVEL SECURITY;

ALTER TABLE company.process_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.process_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE company.resource_claims ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.resource_claims FORCE ROW LEVEL SECURITY;

ALTER TABLE company_private.scope_lock_registry ENABLE ROW LEVEL SECURITY;

ALTER TABLE company_private.scope_lock_registry FORCE ROW LEVEL SECURITY;

CREATE FUNCTION company.reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY_AUDIT'; END $$;

CREATE FUNCTION company.r49_preserve_admission_binding() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,company,pg_temp AS $$
BEGIN
 
 
 IF (to_jsonb(OLD)-'state'-'lease_expires_at'-'ended_at')
    IS DISTINCT FROM (to_jsonb(NEW)-'state'-'lease_expires_at'-'ended_at') THEN
 RAISE EXCEPTION 'IMMUTABLE_ATTEMPT_ADMISSION'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r49_preserve_tool_request() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,company,pg_temp AS $$
BEGIN
 IF (to_jsonb(OLD)-'receipt_id') IS DISTINCT FROM (to_jsonb(NEW)-'receipt_id') THEN
 RAISE EXCEPTION 'IMMUTABLE_TOOL_REQUEST'; END IF;
 IF OLD.receipt_id IS NOT NULL AND OLD.receipt_id IS DISTINCT FROM NEW.receipt_id THEN
 RAISE EXCEPTION 'IMMUTABLE_TOOL_RECEIPT'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r49_preserve_workflow_input() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,company,pg_temp AS $$
BEGIN
 IF (to_jsonb(OLD)-'state') IS DISTINCT FROM (to_jsonb(NEW)-'state') THEN
 RAISE EXCEPTION 'IMMUTABLE_WORKFLOW_COMPILE_INPUT'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r49_outbox_content_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, company AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'OUTBOX_RETENTION_REQUIRES_SEPARATE_GUARDED_PROTOCOL'; END IF;
 IF ROW(NEW.event_id,NEW.tenant_id,NEW.project_id,NEW.aggregate_id,
        NEW.aggregate_revision,NEW.kind,NEW.payload,NEW.occurred_at)
    IS DISTINCT FROM
    ROW(OLD.event_id,OLD.tenant_id,OLD.project_id,OLD.aggregate_id,
        OLD.aggregate_revision,OLD.kind,OLD.payload,OLD.occurred_at)
 THEN RAISE EXCEPTION 'IMMUTABLE_OUTBOX_CONTENT'; END IF;
 
 
 RETURN NEW;
END $$;

CREATE FUNCTION company.r50_policy_content_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_POLICY_HISTORY'; END IF;
 IF (to_jsonb(OLD)-'revoked_at'-'revoked_by') IS DISTINCT FROM (to_jsonb(NEW)-'revoked_at'-'revoked_by')
 OR (OLD.revoked_at IS NOT NULL AND ROW(OLD.revoked_at,OLD.revoked_by) IS DISTINCT FROM ROW(NEW.revoked_at,NEW.revoked_by))
 THEN RAISE EXCEPTION 'IMMUTABLE_POLICY_DECISION'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r50_immutable_source() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'IMMUTABLE_SOURCE_CREATE_NEW_ID'; END $$;

CREATE FUNCTION company.r50_artifact_immutable() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$ BEGIN
 IF (to_jsonb(OLD)-'state') IS DISTINCT FROM (to_jsonb(NEW)-'state') THEN RAISE EXCEPTION 'IMMUTABLE_ARTIFACT_IDENTITY'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r50_report_binding_immutable() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog AS $$ BEGIN
 IF ROW(OLD.tenant_id,OLD.project_id,OLD.task_id,OLD.attempt_id,OLD.id,OLD.producer_id,OLD.verifier_id,OLD.profile_version,OLD.build_digest,OLD.dirty_digest,OLD.admission_manifest_artifact_id)
 IS DISTINCT FROM ROW(NEW.tenant_id,NEW.project_id,NEW.task_id,NEW.attempt_id,NEW.id,NEW.producer_id,NEW.verifier_id,NEW.profile_version,NEW.build_digest,NEW.dirty_digest,NEW.admission_manifest_artifact_id)
 THEN RAISE EXCEPTION 'IMMUTABLE_VERIFICATION_IDENTITY'; END IF;
 IF OLD.source_report_artifact_id IS NOT NULL AND OLD.source_report_artifact_id IS DISTINCT FROM NEW.source_report_artifact_id
 THEN RAISE EXCEPTION 'IMMUTABLE_VERIFICATION_REPORT'; END IF;
 IF OLD.result IN ('PASS','FAIL','BLOCKED') AND (NEW.result IS DISTINCT FROM OLD.result OR NEW.exit_code IS DISTINCT FROM OLD.exit_code)
 THEN RAISE EXCEPTION 'IMMUTABLE_FINAL_VERIFICATION'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r50_command_identity_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF (to_jsonb(OLD)-'state'-'result_ref') IS DISTINCT FROM (to_jsonb(NEW)-'state'-'result_ref')
 OR (OLD.state IN ('SUCCEEDED','FAILED') AND ROW(OLD.state,OLD.result_ref) IS DISTINCT FROM ROW(NEW.state,NEW.result_ref))
 THEN RAISE EXCEPTION 'IMMUTABLE_COMMAND_RECEIPT'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r51_preserve_host_generation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF NEW.instance_generation<OLD.instance_generation THEN RAISE EXCEPTION 'HOST_GENERATION_REGRESSION'; END IF;
 IF ROW(NEW.host_registration_id,NEW.host_registration_revision) IS DISTINCT FROM ROW(OLD.host_registration_id,OLD.host_registration_revision)
 AND NEW.instance_generation<=OLD.instance_generation THEN RAISE EXCEPTION 'HOST_REBIND_REQUIRES_NEW_GENERATION'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION company.r51f_reservation_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_RESOURCE_HISTORY'; END IF;
 IF (to_jsonb(NEW)-ARRAY['settled_minor','released_minor','state','revision','settlement_command_id','release_command_id','release_op_id'])
 IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['settled_minor','released_minor','state','revision','settlement_command_id','release_command_id','release_op_id']) THEN RAISE EXCEPTION 'IMMUTABLE_RESERVATION_BINDING'; END IF;
 IF OLD.settlement_command_id IS NOT NULL AND ROW(NEW.settlement_command_id,NEW.settled_minor) IS DISTINCT FROM ROW(OLD.settlement_command_id,OLD.settled_minor) THEN RAISE EXCEPTION 'IMMUTABLE_SETTLEMENT'; END IF;
 IF OLD.release_command_id IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'IMMUTABLE_RELEASE'; END IF;
 IF NEW IS DISTINCT FROM OLD AND NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'RESERVATION_REVISION_CAS'; END IF;
 IF NEW.state<>OLD.state AND NOT ((OLD.state='RESERVED' AND NEW.state IN ('SETTLED','OVERDRAWN','UNKNOWN_USAGE'))
 OR (OLD.state='UNKNOWN_USAGE' AND NEW.state IN ('SETTLED','OVERDRAWN')) OR (OLD.state='SETTLED' AND NEW.state='RELEASED')) THEN RAISE EXCEPTION 'RESERVATION_STATE_TRANSITION'; END IF;
 RETURN NEW; END $$;

CREATE FUNCTION company.r51f_process_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_PROCESS_HISTORY'; END IF;
 IF (to_jsonb(NEW)-ARRAY['state','revision','lease_expires_at','stop_command_id','stop_artifact_id','release_command_id'])
 IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','revision','lease_expires_at','stop_command_id','stop_artifact_id','release_command_id']) THEN RAISE EXCEPTION 'IMMUTABLE_PROCESS_BINDING'; END IF;
 IF (OLD.stop_command_id IS NOT NULL AND NEW.stop_command_id IS DISTINCT FROM OLD.stop_command_id)
 OR (OLD.stop_artifact_id IS NOT NULL AND NEW.stop_artifact_id IS DISTINCT FROM OLD.stop_artifact_id)
 OR (OLD.release_command_id IS NOT NULL AND NEW.release_command_id IS DISTINCT FROM OLD.release_command_id) THEN RAISE EXCEPTION 'PROCESS_RECEIPT_SET_ONCE'; END IF;
 IF NEW IS DISTINCT FROM OLD AND NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'PROCESS_REVISION_CAS'; END IF;
 IF OLD.state IN ('STOPPED','COMPLETED','FAILED_NOT_STARTED') AND ROW(NEW.state,NEW.lease_expires_at,NEW.stop_command_id) IS DISTINCT FROM ROW(OLD.state,OLD.lease_expires_at,OLD.stop_command_id) THEN RAISE EXCEPTION 'TERMINAL_PROCESS_NO_REOPEN'; END IF;
 IF NEW.state<>OLD.state AND NOT (
 (OLD.state='LEASED' AND NEW.state IN ('REQUESTED','STOP_REQUESTED','FAILED_NOT_STARTED','UNKNOWN_LOCAL'))
 OR (OLD.state='REQUESTED' AND NEW.state IN ('STARTING','STOP_REQUESTED','FAILED_NOT_STARTED','UNKNOWN_LOCAL'))
 OR (OLD.state='STARTING' AND NEW.state IN ('RUNNING','STOP_REQUESTED','FAILED_NOT_STARTED','UNKNOWN_LOCAL'))
 OR (OLD.state='RUNNING' AND NEW.state IN ('STOP_REQUESTED','COMPLETED','UNKNOWN_LOCAL'))
 OR (OLD.state='STOP_REQUESTED' AND NEW.state IN ('STOPPED','COMPLETED','UNKNOWN_LOCAL'))
 OR (OLD.state='UNKNOWN_LOCAL' AND NEW.state IN ('RUNNING','STOP_REQUESTED','STOPPED','COMPLETED','FAILED_NOT_STARTED'))
 ) THEN RAISE EXCEPTION 'PROCESS_STATE_TRANSITION'; END IF;
 RETURN NEW; END $$;

CREATE FUNCTION company.r51f_claim_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_CLAIM_HISTORY'; END IF;
 IF (to_jsonb(NEW)-ARRAY['state','revision','release_command_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','revision','release_command_id']) THEN RAISE EXCEPTION 'IMMUTABLE_CLAIM_BINDING'; END IF;
 IF OLD.state='RELEASED' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'CLAIM_ALREADY_RELEASED'; END IF;
 IF NEW IS DISTINCT FROM OLD AND NOT (OLD.state='HELD' AND NEW.state='RELEASED' AND NEW.revision=OLD.revision+1 AND NEW.release_command_id IS NOT NULL) THEN RAISE EXCEPTION 'CLAIM_RELEASE_ONLY'; END IF;
 RETURN NEW; END $$;

CREATE TRIGGER immutable_scope_lock BEFORE UPDATE OR DELETE ON company_private.scope_lock_registry
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER immutable_clock_sample BEFORE UPDATE OR DELETE ON company.clock_samples
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_preserve_admission_binding BEFORE UPDATE ON company.attempts
 FOR EACH ROW EXECUTE FUNCTION company.r49_preserve_admission_binding();

CREATE TRIGGER r49_preserve_tool_request BEFORE UPDATE ON company.tool_requests
 FOR EACH ROW EXECUTE FUNCTION company.r49_preserve_tool_request();

CREATE TRIGGER r49_preserve_workflow_input BEFORE UPDATE ON company.workflow_instances
 FOR EACH ROW EXECUTE FUNCTION company.r49_preserve_workflow_input();

CREATE TRIGGER r49_preserve_workflow_binding BEFORE UPDATE OR DELETE ON company.workflow_stage_bindings
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_preserve_workflow_history BEFORE DELETE ON company.workflow_instances
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_preserve_attempt_history BEFORE DELETE ON company.attempts
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_preserve_qualification_history BEFORE UPDATE OR DELETE ON company.agent_qualifications
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_preserve_tool_history BEFORE DELETE ON company.tool_requests
 FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r49_outbox_immutable BEFORE UPDATE OR DELETE ON company.outbox
FOR EACH ROW EXECUTE FUNCTION company.r49_outbox_content_immutable();

CREATE TRIGGER r50_secret_references_immutable BEFORE UPDATE OR DELETE ON company.secret_references FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r50_policy_decisions_immutable BEFORE UPDATE OR DELETE ON company.policy_decisions FOR EACH ROW EXECUTE FUNCTION company.r50_policy_content_immutable();

CREATE TRIGGER r50_license_records_immutable BEFORE UPDATE OR DELETE ON company.license_records FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r50_host_registrations_immutable BEFORE UPDATE OR DELETE ON company.host_registrations FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r50_objective_immutable BEFORE UPDATE OR DELETE ON company.objectives
 FOR EACH ROW EXECUTE FUNCTION company.r50_immutable_source();

CREATE TRIGGER r50_plan_immutable BEFORE UPDATE OR DELETE ON company.plans
 FOR EACH ROW EXECUTE FUNCTION company.r50_immutable_source();

CREATE TRIGGER r50_artifact_immutable BEFORE UPDATE ON company.artifacts FOR EACH ROW EXECUTE FUNCTION company.r50_artifact_immutable();

CREATE TRIGGER r50_artifact_history BEFORE DELETE ON company.artifacts FOR EACH ROW EXECUTE FUNCTION company.r50_immutable_source();

CREATE TRIGGER r50_report_binding_immutable BEFORE UPDATE ON company.verification_runs FOR EACH ROW EXECUTE FUNCTION company.r50_report_binding_immutable();

CREATE TRIGGER r50_verification_history BEFORE DELETE ON company.verification_runs FOR EACH ROW EXECUTE FUNCTION company.r50_immutable_source();

CREATE TRIGGER r50_command_identity_immutable BEFORE UPDATE ON company.commands FOR EACH ROW EXECUTE FUNCTION company.r50_command_identity_immutable();

CREATE TRIGGER r50_command_history BEFORE DELETE ON company.commands FOR EACH ROW EXECUTE FUNCTION company.r50_immutable_source();

CREATE TRIGGER r51_preserve_host_generation BEFORE UPDATE ON company.projects FOR EACH ROW EXECUTE FUNCTION company.r51_preserve_host_generation();

CREATE TRIGGER r51_bootstrap_receipt_immutable BEFORE UPDATE OR DELETE ON company_private.bootstrap_receipts FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r51f_budget_version_immutable BEFORE UPDATE OR DELETE ON company.budget_versions FOR EACH ROW EXECUTE FUNCTION company.reject_audit_mutation();

CREATE TRIGGER r51f_reservation_identity BEFORE UPDATE OR DELETE ON company.budget_reservations FOR EACH ROW EXECUTE FUNCTION company.r51f_reservation_identity();

CREATE TRIGGER r51f_process_identity BEFORE UPDATE OR DELETE ON company.process_runs FOR EACH ROW EXECUTE FUNCTION company.r51f_process_identity();

CREATE TRIGGER r51f_claim_identity BEFORE UPDATE OR DELETE ON company.resource_claims FOR EACH ROW EXECUTE FUNCTION company.r51f_claim_identity();

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA company FROM PUBLIC;

REVOKE ALL ON company.acceptance_records FROM PUBLIC;

REVOKE ALL ON company.agent_qualifications FROM PUBLIC;

REVOKE ALL ON company.artifacts FROM PUBLIC;

REVOKE ALL ON company.attempts FROM PUBLIC;

REVOKE ALL ON company.audit_events FROM PUBLIC;

REVOKE ALL ON company.authority_scope_heads FROM PUBLIC;

REVOKE ALL ON company.budget_reservations FROM PUBLIC;

REVOKE ALL ON company.budget_versions FROM PUBLIC;

REVOKE ALL ON company.clock_epochs FROM PUBLIC;

REVOKE ALL ON company.clock_samples FROM PUBLIC;

REVOKE ALL ON company.commands FROM PUBLIC;

REVOKE ALL ON company.evaluation_runs FROM PUBLIC;

REVOKE ALL ON company.evidence FROM PUBLIC;

REVOKE ALL ON company.governance_decision_heads FROM PUBLIC;

REVOKE ALL ON company.host_registrations FROM PUBLIC;

REVOKE ALL ON company.license_records FROM PUBLIC;

REVOKE ALL ON company.memberships FROM PUBLIC;

REVOKE ALL ON company.objectives FROM PUBLIC;

REVOKE ALL ON company.outbox FROM PUBLIC;

REVOKE ALL ON company.plans FROM PUBLIC;

REVOKE ALL ON company.policy_decisions FROM PUBLIC;

REVOKE ALL ON company.principals FROM PUBLIC;

REVOKE ALL ON company.process_runs FROM PUBLIC;

REVOKE ALL ON company.project_grants FROM PUBLIC;

REVOKE ALL ON company.projects FROM PUBLIC;

REVOKE ALL ON company.resource_claims FROM PUBLIC;

REVOKE ALL ON company.resource_slots FROM PUBLIC;

REVOKE ALL ON company.secret_references FROM PUBLIC;

REVOKE ALL ON company.sessions FROM PUBLIC;

REVOKE ALL ON company.task_dependencies FROM PUBLIC;

REVOKE ALL ON company.tasks FROM PUBLIC;

REVOKE ALL ON company.tenants FROM PUBLIC;

REVOKE ALL ON company.tool_requests FROM PUBLIC;

REVOKE ALL ON company.verification_runs FROM PUBLIC;

REVOKE ALL ON company.verifier_receipts FROM PUBLIC;

REVOKE ALL ON company.workflow_compile_requests FROM PUBLIC;

REVOKE ALL ON company.workflow_instances FROM PUBLIC;

REVOKE ALL ON company.workflow_stage_bindings FROM PUBLIC;

REVOKE ALL ON company.workspaces FROM PUBLIC;

REVOKE ALL ON company_private.bootstrap_receipts FROM PUBLIC;

REVOKE ALL ON company_private.bootstrap_request_contexts FROM PUBLIC;

REVOKE ALL ON company_private.installation_bootstrap_control FROM PUBLIC;

REVOKE ALL ON company_private.operation_permissions FROM PUBLIC;

REVOKE ALL ON company_private.request_contexts FROM PUBLIC;

REVOKE ALL ON company_private.scope_lock_registry FROM PUBLIC;

-- Function/trigger/EXECUTE policies are authoritative A native-constructor dependency; not installed here.

ROLLBACK;
