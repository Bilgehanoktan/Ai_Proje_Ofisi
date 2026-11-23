-- Disposable fixture control rows. The privileged setup does not confer a delivery grant.
DO $setup$
DECLARE
    tenant uuid := gen_random_uuid();
    project uuid := gen_random_uuid();
    workspace uuid := gen_random_uuid();
    controller uuid := gen_random_uuid();
    command uuid := gen_random_uuid();
    session_id uuid := gen_random_uuid();
BEGIN
    INSERT INTO company.tenants (id, name) VALUES (tenant, 'delivery fixture');
    INSERT INTO company.principals (tenant_id, id, name, kind)
        VALUES (tenant, controller, 'fixture controller', 'WORKER');
    INSERT INTO company.workspaces (tenant_id, id, root_ref, trust_class)
        VALUES (tenant, workspace, 'delivery-rls-fixture', 'DISPOSABLE_TEST');
    INSERT INTO company.projects (tenant_id, id, workspace_id, name)
        VALUES (tenant, project, workspace, 'delivery fixture');
    INSERT INTO company.sessions (tenant_id, id, principal_id, token_hash, expires_at)
        VALUES (tenant, session_id, controller, repeat('a', 64), now() + interval '1 hour');
    INSERT INTO company.audit_events (tenant_id, actor_id, correlation_id, kind)
        VALUES (tenant, controller, gen_random_uuid(), 'LaunchConsumed');
    INSERT INTO company.outbox
        (tenant_id, project_id, aggregate_id, aggregate_revision, kind, payload,
         project_sequence, event_writer_generation, event_instance_id, event_digest)
        VALUES (tenant, project, command, 1, 'LaunchConsumed', '{}'::jsonb,
                1, 54, command, repeat('b', 64));
    IF (SELECT count(*) FROM company.audit_events WHERE kind='LaunchConsumed') <> 1
       OR (SELECT count(*) FROM company.outbox WHERE kind='LaunchConsumed') <> 1 THEN
        RAISE EXCEPTION 'Fixture control rows missing';
    END IF;
    -- A bare operation context exercises the installed policies without minting a command.
    INSERT INTO company_private.request_contexts
        (backend_pid, transaction_id, request_nonce, db_login, tenant_id, project_id,
         principal_id, session_id, operation_id, tenant_epoch, project_epoch,
         session_epoch, writer_generation, authenticated_at, expires_at)
        VALUES (pg_backend_pid(), pg_current_xact_id(), gen_random_uuid(), session_user,
                tenant, project, controller, session_id, 'process.launch_delivery',
                0, 0, 0, 54, now(), now() + interval '1 hour');
END $setup$;

SET LOCAL ROLE company_execution_functions_r58;
DO $test$
BEGIN
    IF NOT row_security_active('company.audit_events')
       OR NOT row_security_active('company.outbox') THEN
        RAISE EXCEPTION 'Receipt row security inactive for test caller';
    END IF;
    IF EXISTS (SELECT FROM company.audit_events WHERE kind='LaunchConsumed')
       OR EXISTS (SELECT FROM company.outbox WHERE kind='LaunchConsumed') THEN
        RAISE EXCEPTION 'Uncommitted receipt visible to delivery role';
    END IF;
    BEGIN
        PERFORM company_private.r60_delivery_guard(gen_random_uuid(), gen_random_uuid(), '{}'::jsonb);
        RAISE EXCEPTION 'Unauthorised delivery unexpectedly succeeded';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'R60_DELIVERY_DENIED' THEN RAISE; END IF;
    END;
END $test$;
RESET ROLE;
SELECT 'REAL_RECEIPTS_PRESENT_UNCOMMITTED_ROWS_HIDDEN_DELIVERY_DENIED';
