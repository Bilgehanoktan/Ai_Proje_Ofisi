-- MOD-012, MOD-013, MOD-014 additive schema candidate (inert until explicitly assembled/approved).
-- Preserves tenant isolation, FORCE ROW LEVEL SECURITY, and separation of duties.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

CREATE TABLE IF NOT EXISTS company.catalog_entries (
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    kind text NOT NULL CHECK (kind IN ('SKILL', 'ROLE', 'TOOL', 'MODEL')),
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version text NOT NULL CHECK (length(trim(version)) > 0),
    digest text NOT NULL CHECK (length(trim(digest)) > 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, kind, name, version)
);
ALTER TABLE company.catalog_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.catalog_entries FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.catalog_entries FROM PUBLIC;

DROP POLICY IF EXISTS catalog_entries_tenant_isolation ON company.catalog_entries;
CREATE POLICY catalog_entries_tenant_isolation ON company.catalog_entries
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS company.memory_promotions (
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    record_id text NOT NULL CHECK (length(trim(record_id)) > 0),
    summary text NOT NULL CHECK (length(trim(summary)) > 0),
    evidence_digest text NOT NULL CHECK (length(trim(evidence_digest)) > 0),
    state text NOT NULL CHECK (state IN ('CANDIDATE', 'VERIFIED', 'PROMOTED', 'REJECTED')),
    verified_by text,
    promoted_by text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, record_id),
    CHECK (promoted_by IS NULL OR (verified_by IS NOT NULL AND promoted_by <> verified_by))
);
ALTER TABLE company.memory_promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.memory_promotions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.memory_promotions FROM PUBLIC;

DROP POLICY IF EXISTS memory_promotions_tenant_isolation ON company.memory_promotions;
CREATE POLICY memory_promotions_tenant_isolation ON company.memory_promotions
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS company.work_template_validations (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    work_type text NOT NULL CHECK (work_type IN ('RESEARCH', 'SPREADSHEET', 'OBLIGATION')),
    template_id text NOT NULL CHECK (length(trim(template_id)) > 0),
    template_version text NOT NULL CHECK (length(trim(template_version)) > 0),
    validated boolean NOT NULL,
    evidence_digest text NOT NULL CHECK (length(trim(evidence_digest)) > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE company.work_template_validations ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.work_template_validations FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.work_template_validations FROM PUBLIC;

DROP POLICY IF EXISTS work_template_validations_tenant_isolation ON company.work_template_validations;
CREATE POLICY work_template_validations_tenant_isolation ON company.work_template_validations
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS company.external_effect_ledger (
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) > 0),
    effect_id text NOT NULL CHECK (length(trim(effect_id)) > 0),
    provider text NOT NULL CHECK (length(trim(provider)) > 0),
    status text NOT NULL CHECK (status IN ('COMMITTED', 'UNKNOWN', 'REVERTED')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, idempotency_key)
);
ALTER TABLE company.external_effect_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.external_effect_ledger FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.external_effect_ledger FROM PUBLIC;

DROP POLICY IF EXISTS external_effect_ledger_tenant_isolation ON company.external_effect_ledger;
CREATE POLICY external_effect_ledger_tenant_isolation ON company.external_effect_ledger
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ROLLBACK;
