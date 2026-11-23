BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
ALTER FUNCTION company_private.r61_worker_deadline(uuid,uuid) OWNER TO company_context_owner;
REVOKE ALL ON FUNCTION company_private.r61_worker_deadline(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.r61_worker_deadline(uuid,uuid) TO company_execution_functions_r58;
GRANT SELECT ON company_private.r61_attempt_authorities TO company_context_owner;
CREATE POLICY r62_context_attempt_authority_read ON company_private.r61_attempt_authorities FOR SELECT TO company_context_owner USING(EXISTS(SELECT 1 FROM company_private.request_contexts x WHERE x.backend_pid=pg_backend_pid() AND x.transaction_id=pg_current_xact_id() AND x.db_login=session_user AND x.writer_generation=54 AND x.tenant_id=r61_attempt_authorities.tenant_id AND x.project_id=r61_attempt_authorities.project_id));
ALTER FUNCTION company_private.r62_prepared_deadline(uuid) OWNER TO company_execution_functions_r58;
REVOKE ALL ON FUNCTION company_private.r62_prepared_deadline(uuid) FROM PUBLIC;

ROLLBACK;
