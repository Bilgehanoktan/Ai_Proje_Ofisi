-- Report only aggregate readiness for the four operations in the first SQL test.
-- Requires the synthetic native bootstrap from run_sql_fixture.py.
DO $check$
BEGIN
    IF (SELECT count(*) FROM company_private.bootstrap_receipts) <> 1 THEN
        RAISE EXCEPTION 'Expected one synthetic bootstrap receipt';
    END IF;
END $check$;

WITH required(operation_id) AS (
    VALUES ('workspace.current_head'), ('patch.receipt'),
           ('process.launch_delivery'), ('process.reconcile')
)
SELECT required.operation_id,
       operation.operation_id IS NOT NULL AS registered,
       operation.approved_policy_digest IS NOT NULL AS policy_approved,
       EXISTS (
           SELECT FROM company.project_grants AS g
           JOIN company_private.bootstrap_receipts AS receipt
             ON receipt.tenant_id = g.tenant_id AND receipt.project_id = g.project_id
           WHERE g.permission = operation.permission
       ) AS has_project_grant
FROM required
LEFT JOIN company_private.operation_permissions AS operation USING (operation_id)
ORDER BY required.operation_id;
