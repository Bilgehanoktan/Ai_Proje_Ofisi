BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE TABLE company.signer_enrollments (
 tenant_id uuid NOT NULL,
 issuer_id uuid NOT NULL,
 key_id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('TASK_VERIFICATION','EVALUATION','EGRESS_QUIESCENCE')),
 profile_id text NOT NULL,
 secret_ref text NOT NULL CHECK(length(secret_ref)>0),
 key_fingerprint text NOT NULL CHECK(key_fingerprint ~ '^[a-f0-9]{64}$'),
 enrollment_revision bigint NOT NULL CHECK(enrollment_revision>=0),
 valid_from timestamptz NOT NULL,
 valid_until timestamptz NOT NULL,
 revoked_at timestamptz,
 compromised_since timestamptz,
 approved_by uuid NOT NULL,
 PRIMARY KEY(tenant_id,issuer_id,key_id,purpose,enrollment_revision),
 UNIQUE(tenant_id,issuer_id,key_id,purpose,enrollment_revision,profile_id),
 CHECK(valid_until>valid_from)
);

CREATE TABLE company.internal_receipt_envelopes (
 tenant_id uuid NOT NULL,
 issuer_id uuid NOT NULL,
 key_id uuid NOT NULL,
 purpose text NOT NULL,
 enrollment_revision bigint NOT NULL,
 receipt_id uuid NOT NULL,
 profile_id text NOT NULL,
 envelope_digest text NOT NULL CHECK(envelope_digest ~ '^[a-f0-9]{64}$'),
 expected_binding_digest text NOT NULL CHECK(expected_binding_digest ~ '^[a-f0-9]{64}$'),
 canonical_artifact_digest text NOT NULL CHECK(canonical_artifact_digest ~ '^[a-f0-9]{64}$'),
 auth_tag text NOT NULL CHECK(auth_tag ~ '^[A-Za-z0-9_-]{43}$'),
 verified_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,receipt_id),
 UNIQUE(tenant_id,receipt_id,purpose,expected_binding_digest)
);

ALTER TABLE company.signer_enrollments ADD FOREIGN KEY(tenant_id,issuer_id) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.signer_enrollments ADD FOREIGN KEY(tenant_id,approved_by) REFERENCES company.principals(tenant_id,id);

ALTER TABLE company.internal_receipt_envelopes ADD FOREIGN KEY(tenant_id,issuer_id,key_id,purpose,enrollment_revision,profile_id) REFERENCES company.signer_enrollments(tenant_id,issuer_id,key_id,purpose,enrollment_revision,profile_id);

ALTER TABLE company.signer_enrollments ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.signer_enrollments FORCE ROW LEVEL SECURITY;

ALTER TABLE company.internal_receipt_envelopes ENABLE ROW LEVEL SECURITY;

ALTER TABLE company.internal_receipt_envelopes FORCE ROW LEVEL SECURITY;

REVOKE ALL ON company.signer_enrollments,company.internal_receipt_envelopes FROM PUBLIC;
ROLLBACK;
