-- r53 sealed execution tuple; existing Qualification owner, no new Role/Profile authority table.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
ALTER TABLE company.evaluation_runs ADD COLUMN execution_binding jsonb;
ALTER TABLE company.evaluation_runs ADD COLUMN execution_binding_digest text CHECK(execution_binding_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE company.evaluation_runs ADD CONSTRAINT r53_execution_binding_pair CHECK ((execution_binding IS NULL)=(execution_binding_digest IS NULL));
ALTER TABLE company.evaluation_runs ADD CONSTRAINT r53_execution_binding_shape CHECK(execution_binding IS NULL OR ((
 jsonb_typeof(execution_binding)='object' AND execution_binding->>'schema_version'='r53.execution-binding.v1'
 AND execution_binding->>'subject_principal_id'=subject_principal_id::text
 AND execution_binding#>>'{role_definition,identity}'=role_id
 AND execution_binding#>>'{model,sha256}'=model_digest
 AND execution_binding#>>'{suite,sha256}'=fixture_digest
 AND execution_binding ?& ARRAY['role_definition','agent_profile','model','engine','tools','suite','policy','resource_scope','independent_evidence','source_revision']) IS TRUE));
ALTER TABLE company.evaluation_runs ADD CONSTRAINT r53_evaluation_sealed_binding UNIQUE(tenant_id,project_id,id,subject_principal_id,role_id,execution_binding_digest);
ALTER TABLE company.agent_qualifications ADD COLUMN execution_binding_digest text CHECK(execution_binding_digest ~ '^[a-f0-9]{64}$');
ALTER TABLE company.agent_qualifications ADD CONSTRAINT r53_qualification_sealed_evaluation FOREIGN KEY(tenant_id,project_id,evaluation_run_id,subject_principal_id,role_id,execution_binding_digest) REFERENCES company.evaluation_runs(tenant_id,project_id,id,subject_principal_id,role_id,execution_binding_digest);
ALTER TABLE company.agent_qualifications ADD CONSTRAINT r53_qualification_version_shape CHECK(execution_binding_digest IS NULL OR ((
 jsonb_typeof(version_binding)='object' AND version_binding->>'schema_version'='r53.execution-binding.v1'
 AND version_binding->>'subject_principal_id'=subject_principal_id::text
 AND version_binding#>>'{role_definition,identity}'=role_id) IS TRUE));
-- legacy NULL stays quarantined, not silently retroactively admitted. Admission must require nonNULL digest.
ROLLBACK;
