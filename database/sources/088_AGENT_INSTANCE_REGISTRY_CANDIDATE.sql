-- MOD-003 / MOD-011: Canonical AgentInstance & task attempt binding schema (inert until assembled).
-- Enforces tenant/project isolation (FORCE RLS), distinct agent instances per role,
-- and prevents stale/superseded attempts from remaining active on an agent instance.
BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;

CREATE TABLE IF NOT EXISTS company.agent_instances (
    agent_instance_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    project_id uuid NOT NULL,
    role_id text NOT NULL CHECK (role_id ~ '^(?:MGR|EXP|QA)-[0-9]{2,3}$'),
    display_name text NOT NULL CHECK (length(trim(display_name)) > 0),
    worker_principal text NOT NULL CHECK (length(trim(worker_principal)) > 0),
    state text NOT NULL CHECK (state IN ('IDLE', 'RUNNING', 'BLOCKED', 'STALE')),
    active_task_id text,
    active_attempt_id uuid,
    active_task_title text,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (tenant_id, project_id) REFERENCES company.projects(tenant_id, id),
    CHECK (
        (state = 'RUNNING' AND active_task_id IS NOT NULL AND active_attempt_id IS NOT NULL)
        OR (state <> 'RUNNING' AND active_task_id IS NULL AND active_attempt_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_instances_unique_active_attempt_idx
    ON company.agent_instances (tenant_id, project_id, active_attempt_id)
    WHERE active_attempt_id IS NOT NULL;

ALTER TABLE company.agent_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.agent_instances FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.agent_instances FROM PUBLIC;

DROP POLICY IF EXISTS agent_instances_tenant_isolation ON company.agent_instances;
CREATE POLICY agent_instances_tenant_isolation ON company.agent_instances
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS company.agent_instance_assignments (
    assignment_id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES company.tenants(id),
    project_id uuid NOT NULL,
    agent_instance_id uuid NOT NULL REFERENCES company.agent_instances(agent_instance_id),
    task_id text NOT NULL CHECK (length(trim(task_id)) > 0),
    attempt_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('ACTIVE', 'COMPLETED', 'SUPERSEDED', 'FAILED')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ended_at timestamptz,
    FOREIGN KEY (tenant_id, project_id) REFERENCES company.projects(tenant_id, id)
);

ALTER TABLE company.agent_instance_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE company.agent_instance_assignments FORCE ROW LEVEL SECURITY;
REVOKE ALL ON company.agent_instance_assignments FROM PUBLIC;

DROP POLICY IF EXISTS agent_assignments_tenant_isolation ON company.agent_instance_assignments;
CREATE POLICY agent_assignments_tenant_isolation ON company.agent_instance_assignments
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ROLLBACK;
