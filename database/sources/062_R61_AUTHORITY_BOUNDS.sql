BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE TABLE company_private.r61_attempt_authorities (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,task_id uuid NOT NULL,attempt_id uuid NOT NULL,
 worker_id uuid NOT NULL,grant_chain_ids uuid[] NOT NULL CHECK(cardinality(grant_chain_ids)>0),
 admitted_until timestamptz NOT NULL CHECK(isfinite(admitted_until)),command_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,project_id,task_id,attempt_id),
 FOREIGN KEY(tenant_id,project_id,task_id,attempt_id) REFERENCES company.attempts(tenant_id,project_id,task_id,id),
 FOREIGN KEY(tenant_id,command_id) REFERENCES company.commands(tenant_id,id)
);
CREATE TABLE company_private.r61_extension_authorities (
 tenant_id uuid NOT NULL,project_id uuid NOT NULL,extension_id uuid NOT NULL,controller_id uuid NOT NULL,
 phase text NOT NULL CHECK(phase IN ('PREPARED','COMMITTED')),grant_chain_ids uuid[] NOT NULL CHECK(cardinality(grant_chain_ids)>0),
 PRIMARY KEY(tenant_id,project_id,extension_id,phase),
 FOREIGN KEY(tenant_id,project_id,extension_id) REFERENCES company_private.r60_lease_extensions(tenant_id,project_id,id)
);
CREATE FUNCTION company_private.r61_grant_deadline(p_chain uuid[],p_actor uuid,p_permission text,p_task uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;current_chain uuid[];until_at timestamptz;n integer;finite_chain boolean;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 IF p_actor IS NULL OR p_permission IS NULL OR p_task IS NULL OR p_chain IS NULL OR cardinality(p_chain)=0 OR cardinality(p_chain)<>(SELECT count(DISTINCT id) FROM unnest(p_chain) id) THEN RAISE EXCEPTION 'R61_COMPLETE_UNIQUE_CHAIN_REQUIRED'; END IF;
 current_chain=company_private.r54_grant_chain(x.tenant_id,x.project_id,p_actor,p_permission,p_task,p_chain[1]);
 IF current_chain IS DISTINCT FROM p_chain THEN RAISE EXCEPTION 'R61_ANCESTOR_CHAIN_CHANGED'; END IF;
 SELECT count(*),least(min(g.valid_until),x.expires_at),bool_and(isfinite(g.valid_until)) INTO n,until_at,finite_chain FROM company.project_grants g WHERE g.tenant_id=x.tenant_id AND g.project_id=x.project_id AND g.grant_id=ANY(p_chain) AND g.revoked_at IS NULL;
 IF n<>cardinality(p_chain) OR finite_chain IS NOT TRUE OR until_at IS NULL OR NOT isfinite(until_at) THEN RAISE EXCEPTION 'R61_CURRENT_FINITE_AUTHORITY_REQUIRED'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 RETURN until_at;
END $$;
CREATE FUNCTION company_private.r61_worker_deadline(p_task uuid,p_attempt uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company_private.r61_attempt_authorities%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT a FROM company_private.r61_attempt_authorities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt;
 RETURN company_private.r61_grant_deadline(a.grant_chain_ids,a.worker_id,'worker.claim',p_task);
END $$;
CREATE FUNCTION company_private.r61_extension_deadline(p_extension uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;pr company_private.r61_extension_authorities%ROWTYPE;co company_private.r61_extension_authorities%ROWTYPE;e company_private.r60_lease_extensions%ROWTYPE;r company.process_runs%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT e FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_extension;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.process_id;
 SELECT * INTO STRICT pr FROM company_private.r61_extension_authorities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND extension_id=e.id AND phase='PREPARED';
 SELECT * INTO STRICT co FROM company_private.r61_extension_authorities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND extension_id=e.id AND phase='COMMITTED';
 IF pr.controller_id IS DISTINCT FROM r.controller_id OR co.controller_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id THEN RAISE EXCEPTION 'R61_EXACT_CONTROLLER_CHAINS_REQUIRED'; END IF;
 RETURN least(company_private.r61_worker_deadline(r.task_id,r.attempt_id),company_private.r61_grant_deadline(pr.grant_chain_ids,r.controller_id,'process.lease_prepare',r.task_id),company_private.r61_grant_deadline(co.grant_chain_ids,r.controller_id,'process.lease_commit',r.task_id));
END $$;
ROLLBACK;
