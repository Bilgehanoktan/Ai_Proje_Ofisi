BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Legacy rows remain NULL and are blocked, never guessed/backfilled.
ALTER TABLE company_private.r61_attempt_authorities ADD COLUMN worker_session_id uuid;
ALTER TABLE company_private.r61_attempt_authorities ADD COLUMN worker_session_expires_at timestamptz;
ALTER TABLE company_private.r61_attempt_authorities ADD COLUMN worker_session_epoch bigint;
ALTER TABLE company_private.r61_attempt_authorities ADD CONSTRAINT r62_worker_session_pair CHECK(
 (worker_session_id IS NULL AND worker_session_expires_at IS NULL AND worker_session_epoch IS NULL)
 OR (worker_session_id IS NOT NULL AND worker_session_expires_at IS NOT NULL AND isfinite(worker_session_expires_at) AND worker_session_epoch IS NOT NULL AND worker_session_epoch>=0));
ALTER TABLE company_private.r61_attempt_authorities ADD FOREIGN KEY(tenant_id,worker_session_id) REFERENCES company.sessions(tenant_id,id);
CREATE OR REPLACE FUNCTION company_private.r61_worker_deadline(p_task uuid,p_attempt uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company_private.r61_attempt_authorities%ROWTYPE;s company.sessions%ROWTYPE;until_at timestamptz;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT a FROM company_private.r61_attempt_authorities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt;
 IF a.worker_session_id IS NULL OR a.worker_session_expires_at IS NULL THEN RAISE EXCEPTION 'R62_LEGACY_WORKER_SESSION_UNPROVEN'; END IF;
 SELECT * INTO STRICT s FROM company.sessions WHERE tenant_id=x.tenant_id AND id=a.worker_session_id AND principal_id=a.worker_id AND revoked_at IS NULL;
 IF NOT EXISTS(SELECT 1 FROM company.authority_scope_heads h WHERE h.tenant_id=x.tenant_id AND h.scope_kind='SESSION' AND h.scope_ref=a.worker_session_id AND h.epoch=a.worker_session_epoch) THEN RAISE EXCEPTION 'R62_WORKER_SESSION_EPOCH_REVOKED'; END IF;
 until_at=least(a.worker_session_expires_at,s.expires_at,company_private.r61_grant_deadline(a.grant_chain_ids,a.worker_id,'worker.claim',p_task));
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 RETURN until_at;
END $$;
CREATE FUNCTION company_private.r62_prepared_deadline(p_extension uuid) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;pr company_private.r61_extension_authorities%ROWTYPE;e company_private.r60_lease_extensions%ROWTYPE;r company.process_runs%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 SELECT * INTO STRICT e FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_extension AND state='PREPARED';
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.process_id;
 SELECT * INTO STRICT pr FROM company_private.r61_extension_authorities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND extension_id=e.id AND phase='PREPARED';
 IF pr.controller_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id THEN RAISE EXCEPTION 'R62_EXACT_PREPARED_CONTROLLER_REQUIRED'; END IF;
 RETURN least(company_private.r61_worker_deadline(r.task_id,r.attempt_id),company_private.r61_grant_deadline(pr.grant_chain_ids,r.controller_id,'process.lease_prepare',r.task_id));
END $$;
ROLLBACK;
