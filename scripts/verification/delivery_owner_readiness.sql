-- Read the native prerequisites after running the synthetic owner bootstrap.
SELECT json_build_object(
    'bootstrap_receipts', (SELECT count(*) FROM company_private.bootstrap_receipts),
    'projects', (SELECT count(*) FROM company.projects),
    'sessions', (SELECT count(*) FROM company.sessions),
    'operation_grants', (SELECT count(*) FROM company.project_grants WHERE permission='process.launch_delivery'),
    'approved_delivery_policies', (SELECT count(*) FROM company_private.operation_permissions
                                  WHERE operation_id='process.launch_delivery' AND approved_policy_digest IS NOT NULL),
    'launch_capabilities', (SELECT count(*) FROM company_private.r58_launch_capabilities),
    'successful_consume_commands', (SELECT count(*) FROM company.commands
                                    WHERE operation='process.launch_consume' AND state='SUCCEEDED')
);
