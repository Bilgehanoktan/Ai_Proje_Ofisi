BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_worker_claim(p_task uuid,p_revision bigint,p_qualification uuid,p_binding text,p_policy_revision bigint,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;t company.tasks%ROWTYPE;q company.agent_qualifications%ROWTYPE;
 h company_private.r58_workspace_heads%ROWTYPE;lp company_private.r58_lease_policies%ROWTYPE;c company.commands%ROWTYPE;b jsonb;until_at timestamptz;aid uuid;n integer;
BEGIN
 x=company_private.r58_context('worker.claim');
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=x.principal_id AND kind IN ('WORKER','VERIFIER')) THEN RAISE EXCEPTION 'R58_TECHNICAL_WORKER_REQUIRED'; END IF;
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'revision',p_revision,'qualification',p_qualification,'binding',p_binding,'lease_policy_revision',p_policy_revision));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT lp FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=p_policy_revision AND enabled FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=lp.approved_by AND kind='HUMAN') THEN RAISE EXCEPTION 'R58_HUMAN_LEASE_POLICY_REQUIRED'; END IF;
 PERFORM company_private.r60_assert_ready(p_task,p_revision);
 q=company_private.r58_qualification(p_qualification,x.principal_id,p_binding);
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 SELECT * INTO STRICT t FROM company.tasks WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_task FOR UPDATE;
 IF x.task_id IS DISTINCT FROM p_task OR x.attempt_id IS NOT NULL OR t.execution_kind IS DISTINCT FROM 'ORDINARY' OR t.state IS DISTINCT FROM 'READY' OR t.revision IS DISTINCT FROM p_revision OR t.active_attempt_id IS NOT NULL OR t.role_id IS DISTINCT FROM q.role_id
 OR EXISTS(SELECT 1 FROM company.task_dependencies d JOIN company.tasks parent ON parent.tenant_id=d.tenant_id AND parent.project_id=d.project_id AND parent.id=d.depends_on_task_id WHERE d.tenant_id=t.tenant_id AND d.project_id=t.project_id AND d.task_id=t.id AND parent.state<>'ACCEPTED') THEN RAISE EXCEPTION 'R58_TASK_NOT_CLAIMABLE'; END IF;
 b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 until_at=least((b->>'utc_lower_bound')::timestamptz+(lp.duration_ms::numeric*interval '1 millisecond'),q.valid_until,lp.valid_until,company_private.r61_grant_deadline(x.grant_chain_ids,x.principal_id,'worker.claim',p_task));
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 SELECT coalesce(max(attempt_no),0)+1 INTO n FROM company.attempts WHERE tenant_id=t.tenant_id AND project_id=t.project_id AND task_id=t.id;
 aid=gen_random_uuid();
 INSERT INTO company.attempts(tenant_id,project_id,task_id,id,attempt_no,fencing_epoch,worker_id,state,lease_expires_at,admission_qualification_id,r58_binding_digest,r58_head_digest,r58_policy_revision,r58_verification_profile_digest)
 VALUES(t.tenant_id,t.project_id,t.id,aid,n,t.fencing_epoch+1,x.principal_id,'CLAIMED',until_at,q.id,p_binding,h.head_digest,lp.revision,lp.verification_profile_digest);
 INSERT INTO company_private.r61_attempt_authorities VALUES(x.tenant_id,x.project_id,p_task,aid,x.principal_id,x.grant_chain_ids,until_at,c.id);
 UPDATE company.tasks SET state='RUNNING',revision=revision+1,fencing_epoch=fencing_epoch+1,active_attempt_id=aid WHERE tenant_id=t.tenant_id AND project_id=t.project_id AND id=t.id AND revision=p_revision AND state='READY';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_TASK_CLAIM_CAS'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 RETURN company_private.r58_finish(c.id,aid,jsonb_build_object('attempt_id',aid,'task_id',t.id,'fencing_epoch',t.fencing_epoch+1,'lease_expires_at',until_at,'qualification_id',q.id,'head_digest',h.head_digest,'lease_policy_revision',lp.revision));
END $$;
CREATE OR REPLACE FUNCTION company_private.r58_worker_heartbeat(p_task uuid,p_attempt uuid,p_fence bigint,p_policy_revision bigint,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;lp company_private.r58_lease_policies%ROWTYPE;q company.agent_qualifications%ROWTYPE;c company.commands%ROWTYPE;r company.process_runs%ROWTYPE;b jsonb;until_at timestamptz;
BEGIN
 x=company_private.r58_context('worker.heartbeat');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fencing_epoch',p_fence,'lease_policy_revision',p_policy_revision));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT lp FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=p_policy_revision AND enabled FOR SHARE;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 IF a.worker_id IS DISTINCT FROM x.principal_id OR a.r58_policy_revision IS DISTINCT FROM lp.revision OR a.state NOT IN ('CLAIMED','RUNNING') THEN RAISE EXCEPTION 'R58_STALE_WORKER_HEARTBEAT'; END IF;
 q=company_private.r58_qualification(a.admission_qualification_id,a.worker_id,a.r58_binding_digest);
 b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 until_at=least((b->>'utc_lower_bound')::timestamptz+(lp.duration_ms::numeric*interval '1 millisecond'),q.valid_until,lp.valid_until,company_private.r61_grant_deadline(x.grant_chain_ids,x.principal_id,'worker.heartbeat',p_task),company_private.r61_worker_deadline(p_task,p_attempt));
 IF until_at<a.lease_expires_at THEN RAISE EXCEPTION 'R58_LEASE_POLICY_SHRANK_REQUIRES_FENCE'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 FOR r IN SELECT * FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt ORDER BY id FOR UPDATE LOOP
  PERFORM company_private.r58_process_current(r.id);
  -- A running controller must first support a separately accepted OS lease
  -- extension handshake. DB timestamps alone never extend an active OS lease.
  IF r.worker_id IS DISTINCT FROM a.worker_id OR r.attempt_fencing_epoch IS DISTINCT FROM p_fence OR r.state IS DISTINCT FROM 'REQUESTED' OR r.release_command_id IS NOT NULL THEN RAISE EXCEPTION 'R58_LIVE_OS_RENEWAL_NOT_ACCEPTED'; END IF;
  PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,r.lease_expires_at);
  UPDATE company.process_runs SET lease_expires_at=until_at,revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision;
  IF NOT FOUND THEN RAISE EXCEPTION 'R58_PROCESS_LEASE_CAS'; END IF;
 END LOOP;
 UPDATE company.attempts SET lease_expires_at=until_at WHERE tenant_id=a.tenant_id AND project_id=a.project_id AND task_id=a.task_id AND id=a.id AND fencing_epoch=p_fence AND lease_expires_at=a.lease_expires_at;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_ATTEMPT_LEASE_CAS'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 RETURN company_private.r58_finish(c.id,a.id,jsonb_build_object('attempt_id',a.id,'fencing_epoch',p_fence,'lease_expires_at',until_at,'lease_policy_revision',lp.revision));
END $$;
ROLLBACK;
