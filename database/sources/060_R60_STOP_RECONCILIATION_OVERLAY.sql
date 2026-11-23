BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_process_stop_release(p_process uuid,p_revision bigint,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;r company.process_runs%ROWTYPE;m company_private.r58_attestations%ROWTYPE;b company.budget_reservations%ROWTYPE;cl company.resource_claims%ROWTYPE;ch company_private.r58_controller_heads%ROWTYPE;c company.commands%ROWTYPE;j jsonb;
BEGIN
 -- Cleanup uses current PROJECT authority, not an expired worker lease. It
 -- grants no new execution and cannot authorize another spawn or new spend.
 x=company_private.r58_context('process.stop_release');m=company_private.r58_attestation(p_attestation,'r58.quiescence.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['process_id','task_id','attempt_id','fencing_epoch','host_boot_id','controller_generation','cgroup_inode','process_identity_digest','cgroup_populated','workspace_fenced','no_post_fence_spawn','settled_minor','outcome']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('process_id',p_process,'expected_revision',p_revision,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 SELECT * INTO STRICT ch FROM company_private.r58_controller_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND controller_id=r.controller_id AND generation=r.controller_generation FOR SHARE;
 IF r.e0_evaluation_run_id IS NOT NULL OR r.kind IS DISTINCT FROM 'TASK_EXECUTION' OR r.revision IS DISTINCT FROM p_revision OR r.release_command_id IS NOT NULL OR (m.issuer_id IS DISTINCT FROM r.controller_id AND NOT (EXISTS(SELECT 1 FROM company_private.r60_process_reconciliations z JOIN company_private.r58_attestations ob ON ob.tenant_id=z.tenant_id AND ob.project_id=z.project_id AND ob.id=z.attestation_id WHERE z.tenant_id=x.tenant_id AND z.project_id=x.project_id AND z.process_id=r.id AND z.outcome IN ('EXITED','NOT_STARTED') AND ob.issuer_id NOT IN (r.worker_id,r.controller_id) AND ob.payload->>'process_identity_digest'=j->>'process_identity_digest' AND ob.payload->'cgroup_inode'=j->'cgroup_inode'))) OR m.issuer_id IS DISTINCT FROM x.principal_id
 OR j->>'process_id' IS DISTINCT FROM r.id::text OR j->>'task_id' IS DISTINCT FROM r.task_id::text OR j->>'attempt_id' IS DISTINCT FROM r.attempt_id::text OR j->>'fencing_epoch' IS DISTINCT FROM r.attempt_fencing_epoch::text
 OR j->>'host_boot_id' IS DISTINCT FROM r.r55_host_boot_id::text OR ch.host_boot_id IS DISTINCT FROM r.r55_host_boot_id OR j->>'controller_generation' IS DISTINCT FROM r.controller_generation::text
 OR j->>'process_identity_digest' !~ '^[a-f0-9]{64}$' OR jsonb_typeof(j->'cgroup_inode') IS DISTINCT FROM 'number'
 OR j->'cgroup_populated' IS DISTINCT FROM '0'::jsonb OR j->'workspace_fenced' IS DISTINCT FROM 'true'::jsonb OR j->'no_post_fence_spawn' IS DISTINCT FROM 'true'::jsonb
 OR j->'settled_minor' IS DISTINCT FROM '0'::jsonb OR j->>'outcome' NOT IN ('STOPPED','FAILED_NOT_STARTED') THEN RAISE EXCEPTION 'R58_ACTUAL_QUIESCENCE_REQUIRED_NO_TTL_RELEASE'; END IF;
 -- The signed identity must agree with the immutable launch callback. For an
 -- uncertain spawn without callback, reconciliation remains blocked rather
 -- than fabricating a process identity or freeing resources by TTL.
 IF NOT EXISTS(SELECT 1 FROM company_private.r58_launch_capabilities cap JOIN company_private.r58_attestations cb ON cb.tenant_id=cap.tenant_id AND cb.project_id=cap.project_id AND cb.id=cap.callback_attestation_id WHERE cap.tenant_id=x.tenant_id AND cap.project_id=x.project_id AND cap.process_id=r.id AND cb.payload->>'process_identity_digest'=j->>'process_identity_digest' AND cb.payload->'cgroup_inode'=j->'cgroup_inode') AND NOT (EXISTS(SELECT 1 FROM company_private.r60_process_reconciliations z JOIN company_private.r58_attestations ob ON ob.tenant_id=z.tenant_id AND ob.project_id=z.project_id AND ob.id=z.attestation_id WHERE z.tenant_id=x.tenant_id AND z.project_id=x.project_id AND z.process_id=r.id AND z.outcome IN ('EXITED','NOT_STARTED') AND ob.issuer_id NOT IN (r.worker_id,r.controller_id) AND ob.payload->>'process_identity_digest'=j->>'process_identity_digest' AND ob.payload->'cgroup_inode'=j->'cgroup_inode')) THEN RAISE EXCEPTION 'R58_STOP_IDENTITY_RECONCILIATION_REQUIRED'; END IF;
 SELECT * INTO STRICT b FROM company.budget_reservations WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.reservation_id FOR UPDATE;
 IF b.amount_minor<>0 OR b.state IS DISTINCT FROM 'RESERVED' OR b.task_id IS DISTINCT FROM r.task_id OR b.attempt_id IS DISTINCT FROM r.attempt_id OR b.attempt_fencing_epoch IS DISTINCT FROM r.attempt_fencing_epoch THEN RAISE EXCEPTION 'R58_ZERO_LOCAL_RESERVATION_ONLY'; END IF;
 FOR cl IN SELECT * FROM company.resource_claims WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND process_run_id=r.id ORDER BY slot_id FOR UPDATE LOOP
  IF cl.state IS DISTINCT FROM 'HELD' THEN RAISE EXCEPTION 'R58_RESOURCE_ALREADY_RELEASED'; END IF;
  UPDATE company.resource_slots SET reserved=reserved-cl.units WHERE tenant_id=cl.tenant_id AND id=cl.slot_id AND reserved>=cl.units;
  IF NOT FOUND THEN RAISE EXCEPTION 'R58_RESOURCE_ACCOUNTING'; END IF;
  UPDATE company.resource_claims SET state='RELEASED',revision=revision+1,release_command_id=c.id WHERE tenant_id=cl.tenant_id AND project_id=cl.project_id AND process_run_id=cl.process_run_id AND slot_id=cl.slot_id AND state='HELD' AND revision=cl.revision;
  IF NOT FOUND THEN RAISE EXCEPTION 'R58_CLAIM_RELEASE_CAS'; END IF;
 END LOOP;
 IF r.state NOT IN ('STOPPED','COMPLETED','FAILED_NOT_STARTED') THEN
  IF j->>'outcome'='FAILED_NOT_STARTED' AND r.state NOT IN ('LEASED','REQUESTED','STARTING','UNKNOWN_LOCAL') THEN RAISE EXCEPTION 'R58_RUNNING_PROCESS_CANNOT_BECOME_NOT_STARTED'; END IF;
  IF j->>'outcome'='STOPPED' AND r.state NOT IN ('STOP_REQUESTED','UNKNOWN_LOCAL') THEN
   UPDATE company.process_runs SET state='STOP_REQUESTED',revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision;
   IF NOT FOUND THEN RAISE EXCEPTION 'R58_STOP_REQUEST_CAS'; END IF;
   r.revision=r.revision+1;
  END IF;
  UPDATE company.process_runs SET state=j->>'outcome',revision=revision+1,stop_command_id=c.id WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision;
  IF NOT FOUND THEN RAISE EXCEPTION 'R58_STOP_CONFIRM_CAS'; END IF;
  r.revision=r.revision+1;
 END IF;
 UPDATE company.budget_reservations SET state='SETTLED',revision=revision+1,settled_minor=0,settlement_command_id=c.id WHERE tenant_id=b.tenant_id AND project_id=b.project_id AND id=b.id AND state='RESERVED' AND revision=b.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_RESERVATION_SETTLEMENT_CAS'; END IF;
 UPDATE company.budget_reservations SET state='RELEASED',revision=revision+1,released_minor=0,release_command_id=c.id,release_op_id=gen_random_uuid() WHERE tenant_id=b.tenant_id AND project_id=b.project_id AND id=b.id AND state='SETTLED' AND revision=b.revision+1;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_RESERVATION_RELEASE_CAS'; END IF;
 UPDATE company.process_runs SET release_command_id=c.id,revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision AND release_command_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PROCESS_RELEASE_CAS'; END IF;
 RETURN company_private.r58_finish(c.id,r.id,jsonb_build_object('process_id',r.id,'resources_released',true,'quiescence_attestation',m.id,'settled_minor',0,'respawn_permitted',false));
END $$;
ROLLBACK;
