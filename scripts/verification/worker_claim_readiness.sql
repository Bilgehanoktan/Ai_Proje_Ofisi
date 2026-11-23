-- Requires --synthetic-owner. Setup and observations roll back together.
\i scripts/verification/workspace_head_native_probe.sql

SELECT json_build_object(
    'workspace_heads', (SELECT count(*) FROM company_private.r58_workspace_heads),
    'ready_tasks', (SELECT count(*) FROM company.tasks WHERE state = 'READY'),
    'lease_policies', (SELECT count(*) FROM company_private.r58_lease_policies WHERE enabled),
    'qualification_rows', (SELECT count(*) FROM company.agent_qualifications),
    'claim_policy_approved', EXISTS (
        SELECT FROM company_private.operation_permissions
        WHERE operation_id = 'worker.claim' AND approved_policy_digest IS NOT NULL
    ),
    'claim_grants', (SELECT count(*) FROM company.project_grants WHERE permission = 'worker.claim'),
    'attempts', (SELECT count(*) FROM company.attempts)
);
