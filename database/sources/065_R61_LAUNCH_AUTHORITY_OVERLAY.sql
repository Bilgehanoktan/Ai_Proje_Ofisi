BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_launch_consume(p_capability uuid,p_digest text,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;c company.commands%ROWTYPE;b jsonb;
BEGIN
 x=company_private.r58_context('process.launch_consume');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('capability',p_capability,'tuple_digest',p_digest));
 -- Even an exact replay may not return a second OS launch instruction.
 IF c.state='SUCCEEDED' THEN RETURN jsonb_build_object('outcome','REPLAY_RECONCILE_ONLY','command_id',c.id,'spawn_permitted',false); END IF;
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_capability FOR UPDATE;
 a=company_private.r58_attempt((cap.tuple->>'task_id')::uuid,(cap.tuple->>'attempt_id')::uuid,(cap.tuple->>'fencing_epoch')::bigint);
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=cap.process_id FOR UPDATE;
 PERFORM company_private.r58_process_current(r.id);
 b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 IF cap.state IS DISTINCT FROM 'RESERVED' OR cap.tuple_digest IS DISTINCT FROM p_digest OR r.controller_id IS DISTINCT FROM x.principal_id OR r.state IS DISTINCT FROM 'REQUESTED'
 OR b->>'host_boot_id' IS DISTINCT FROM cap.tuple->>'host_boot_id' OR (b->>'boottime_after_ns')::numeric>=(cap.tuple->>'not_after_boottime_ns')::numeric
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_workspace_heads h WHERE h.tenant_id=x.tenant_id AND h.project_id=x.project_id AND h.head_digest=cap.tuple->>'head_digest') THEN RAISE EXCEPTION 'R58_CAPABILITY_NOT_CURRENT_OR_ALREADY_USED'; END IF;
 IF r.lease_expires_at>least(company_private.r61_grant_deadline(x.grant_chain_ids,x.principal_id,'process.launch_consume',r.task_id),company_private.r61_worker_deadline(r.task_id,r.attempt_id)) THEN RAISE EXCEPTION 'R61_LAUNCH_LEASE_EXCEEDS_AUTHORITY'; END IF;
 UPDATE company_private.r58_launch_capabilities SET state='CONSUMED',consume_command_id=c.id WHERE tenant_id=cap.tenant_id AND project_id=cap.project_id AND id=cap.id AND state='RESERVED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_CAPABILITY_CONSUME_CAS'; END IF;
 UPDATE company.process_runs SET state='STARTING',revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision AND state='REQUESTED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PROCESS_START_CAS'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,a.lease_expires_at);
 RETURN company_private.r58_finish(c.id,cap.id,jsonb_build_object('capability_id',cap.id,'tuple',cap.tuple,'tuple_raw',cap.tuple::text,'tuple_digest',cap.tuple_digest,'spawn_permitted',true,'release_only_after_commit',true));
END $$;
ROLLBACK;
