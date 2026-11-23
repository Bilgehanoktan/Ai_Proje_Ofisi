BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
LOCK TABLE company.commands IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM company.commands WHERE idempotency_key LIKE 'r60:%') THEN RAISE EXCEPTION 'R60_RESERVED_PREFIX_LEGACY_CONFLICT'; END IF; END $$;
CREATE TABLE company_private.r60_command_scopes (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,principal_id uuid NOT NULL,operation text NOT NULL,
 original_key text NOT NULL,physical_key text NOT NULL,command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,principal_id,operation,original_key),
 UNIQUE(tenant_id,command_id),UNIQUE(tenant_id,principal_id,operation,physical_key),
 FOREIGN KEY(tenant_id,project_id) REFERENCES company.projects(tenant_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id) DEFERRABLE INITIALLY DEFERRED
);
CREATE FUNCTION company_private.r60_find_command(p_key text) RETURNS company.commands
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_PROJECT_SCOPE_REQUIRED'; END IF;
 SELECT c0.* INTO c FROM company.commands c0 JOIN company_private.r60_command_scopes s ON s.tenant_id=c0.tenant_id AND s.command_id=c0.id
 WHERE s.tenant_id=x.tenant_id AND s.project_id=x.project_id AND s.principal_id=x.principal_id AND s.operation=x.operation_id AND s.original_key=p_key FOR UPDATE OF c0;
 IF FOUND THEN RETURN c; END IF;
 -- Unknown legacy attribution blocks; it is never guessed/backfilled.
 IF EXISTS(SELECT 1 FROM company.commands c0 WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key AND r55_project_id IS NULL AND NOT EXISTS(SELECT 1 FROM company_private.r60_command_scopes ns WHERE ns.tenant_id=c0.tenant_id AND ns.command_id=c0.id)) THEN RAISE EXCEPTION 'R60_LEGACY_SCOPE_UNPROVEN'; END IF;
 SELECT c0.* INTO c FROM company.commands c0 WHERE tenant_id=x.tenant_id AND principal_id=x.principal_id AND operation=x.operation_id AND idempotency_key=p_key AND r55_project_id=x.project_id AND NOT EXISTS(SELECT 1 FROM company_private.r60_command_scopes ns WHERE ns.tenant_id=c0.tenant_id AND ns.command_id=c0.id) FOR UPDATE;
 RETURN c;
END $$;
CREATE FUNCTION company_private.r60_command_scope_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;original text;
BEGIN
 IF NEW.operation='trusted_setup.consume' THEN RETURN NEW; END IF;
 x=company_private.r58_context(NEW.operation);
 IF NEW.tenant_id IS DISTINCT FROM x.tenant_id OR NEW.principal_id IS DISTINCT FROM x.principal_id OR NEW.idempotency_key !~ '^[A-Za-z0-9_.:-]{16,128}$' THEN RAISE EXCEPTION 'R60_COMMAND_CONTEXT_SCOPE'; END IF;
 original=NEW.idempotency_key;
 -- Ensures no insert can bypass a legacy quarantine or same-project replay.
 IF (company_private.r60_find_command(original)).id IS NOT NULL THEN RAISE EXCEPTION 'R60_EXISTING_COMMAND_MUST_REPLAY'; END IF;
 NEW.idempotency_key='r60:'||x.project_id::text||':'||encode(sha256(convert_to(original,'UTF8')),'hex');
 INSERT INTO company_private.r60_command_scopes VALUES(x.tenant_id,x.project_id,x.principal_id,x.operation_id,original,NEW.idempotency_key,NEW.id);
 RETURN NEW;
END $$;
CREATE TRIGGER aaa_r60_command_scope_insert BEFORE INSERT ON company.commands FOR EACH ROW EXECUTE FUNCTION company_private.r60_command_scope_insert();
-- Existing commands global uniqueness and immutable receipt triggers stay intact.
ROLLBACK;
