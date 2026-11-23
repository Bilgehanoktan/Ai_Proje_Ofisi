BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r60_lease_prepare(p_process uuid,p_revision bigint,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;q company.agent_qualifications%ROWTYPE;lp company_private.r58_lease_policies%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;cb company_private.r58_attestations%ROWTYPE;c company.commands%ROWTYPE;b jsonb;oldns bigint;newns bigint;until_at timestamptz;identity jsonb;proposal jsonb;id uuid;
BEGIN
 x=company_private.r58_context('process.lease_prepare');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('process_id',p_process,'revision',p_revision));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 PERFORM company_private.r58_process_current(r.id);a=company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);
 IF r.state IS DISTINCT FROM 'RUNNING' OR r.revision IS DISTINCT FROM p_revision OR x.principal_id IS DISTINCT FROM r.controller_id OR x.task_id IS DISTINCT FROM r.task_id OR x.attempt_id IS DISTINCT FROM r.attempt_id
 OR EXISTS(SELECT 1 FROM company_private.r60_tool_consumptions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state IN ('CONSUMED','UNKNOWN')) THEN RAISE EXCEPTION 'R60_ONLY_KNOWN_IDLE_RUNNING_PROCESS_RENEWABLE'; END IF;
 SELECT * INTO STRICT lp FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=a.r58_policy_revision AND enabled FOR SHARE;
 q=company_private.r58_qualification(a.admission_qualification_id,a.worker_id,a.r58_binding_digest);
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state='RUNNING';
 cb=company_private.r58_attestation(cap.callback_attestation_id,'r58.launch-callback.v1');b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 SELECT new_deadline_ns INTO oldns FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id AND state='ACTIVE' ORDER BY new_deadline_ns DESC LIMIT 1;
 oldns=coalesce(oldns,(cap.tuple->>'not_after_boottime_ns')::bigint);
 until_at=least((b->>'utc_lower_bound')::timestamptz+lp.duration_ms*interval '1 millisecond',q.valid_until,lp.valid_until,x.expires_at);
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,until_at);
 -- Convert conservatively using upper UTC bound; never add uncertainty to lease.
 newns=(b->>'boottime_after_ns')::bigint+floor(extract(epoch FROM (until_at-(b->>'utc_upper_bound')::timestamptz))*1000000000)::bigint;
 IF (b->>'boottime_after_ns')::bigint>=oldns OR newns<=oldns OR until_at<=r.lease_expires_at THEN RAISE EXCEPTION 'R60_NO_EXPIRED_OR_NONINCREASING_EXTENSION'; END IF;
 id=gen_random_uuid();identity=jsonb_build_object('process_id',r.id,'attempt_id',r.attempt_id,'fence',r.attempt_fencing_epoch,'host_boot_id',r.r55_host_boot_id,'controller_generation',r.controller_generation,'process_identity_digest',cb.payload->>'process_identity_digest','cgroup_inode',cb.payload->'cgroup_inode');
 proposal=jsonb_build_object('extension_id',id,'identity',identity,'old_deadline',oldns,'new_deadline',newns,'process_revision',r.revision,'policy_revision',lp.revision,'new_expires_at',until_at);
 INSERT INTO company_private.r60_lease_extensions VALUES(x.tenant_id,x.project_id,id,r.id,oldns,newns,r.lease_expires_at,until_at,identity,encode(sha256(convert_to(proposal::text,'UTF8')),'hex'),lp.revision,'PREPARED',NULL,NULL,c.id);
 RETURN company_private.r58_finish(c.id,id,jsonb_build_object('extension_id',id,'proposal',proposal,'proposal_raw',proposal::text,'proposal_digest',encode(sha256(convert_to(proposal::text,'UTF8')),'hex'),'os_extended',false));
END $$;
CREATE FUNCTION company_private.r60_lease_commit(p_extension uuid,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company_private.r60_lease_extensions%ROWTYPE;m company_private.r58_attestations%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;c company.commands%ROWTYPE;b jsonb;
BEGIN
 x=company_private.r58_context('process.lease_commit');m=company_private.r58_attestation(p_attestation,'r60.lease-prepared.v1');
 PERFORM company_private.r58_shape(m.payload,ARRAY['extension_id','proposal_digest','identity','old_deadline','new_deadline','state']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('extension',p_extension,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT e FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_extension FOR UPDATE;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.process_id FOR UPDATE;
 PERFORM company_private.r58_process_current(r.id);a=company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 IF e.state IS DISTINCT FROM 'PREPARED' OR r.state IS DISTINCT FROM 'RUNNING' OR m.issuer_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id OR m.payload->>'state' IS DISTINCT FROM 'PREPARED'
 OR m.payload->>'extension_id' IS DISTINCT FROM e.id::text OR m.payload->>'proposal_digest' IS DISTINCT FROM e.proposal_digest OR m.payload->'identity' IS DISTINCT FROM e.identity OR m.payload->>'old_deadline' IS DISTINCT FROM e.old_deadline_ns::text OR m.payload->>'new_deadline' IS DISTINCT FROM e.new_deadline_ns::text
 OR r.lease_expires_at IS DISTINCT FROM e.old_expires_at OR (b->>'boottime_after_ns')::bigint>=e.old_deadline_ns
 OR NOT EXISTS(SELECT 1 FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=e.policy_revision AND enabled AND valid_until>=e.new_expires_at)
 OR NOT EXISTS(SELECT 1 FROM company.agent_qualifications WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=a.admission_qualification_id AND valid_until>=e.new_expires_at) THEN RAISE EXCEPTION 'R60_LEASE_PREPARED_ACK_BINDING'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,e.new_expires_at);
 UPDATE company.process_runs SET lease_expires_at=e.new_expires_at,revision=revision+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=r.id AND revision=r.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_LEASE_PROCESS_CAS'; END IF;
 UPDATE company.attempts SET lease_expires_at=e.new_expires_at WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=r.task_id AND id=r.attempt_id AND fencing_epoch=r.attempt_fencing_epoch;
 UPDATE company_private.r60_lease_extensions SET state='COMMITTED',prepared_attestation_id=m.id WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.id AND state='PREPARED';
 RETURN company_private.r58_finish(c.id,e.id,jsonb_build_object('state','COMMITTED','extension_id',e.id,'proposal_digest',e.proposal_digest,'new_deadline',e.new_deadline_ns,'tool_use_allowed',false));
END $$;
CREATE FUNCTION company_private.r60_lease_activate(p_extension uuid,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company_private.r60_lease_extensions%ROWTYPE;m company_private.r58_attestations%ROWTYPE;r company.process_runs%ROWTYPE;c company.commands%ROWTYPE;
BEGIN
 x=company_private.r58_context('process.lease_activate');m=company_private.r58_attestation(p_attestation,'r60.lease-active.v1');
 PERFORM company_private.r58_shape(m.payload,ARRAY['extension_id','proposal_digest','identity','active_deadline','activated_at_boottime_ns','state']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('extension',p_extension,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT e FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_extension FOR UPDATE;
 r=company_private.r58_process_current(e.process_id);PERFORM company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);
 IF e.state IS DISTINCT FROM 'COMMITTED' OR m.issuer_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id OR m.payload->>'state' IS DISTINCT FROM 'ACTIVE' OR m.payload->>'extension_id' IS DISTINCT FROM e.id::text OR m.payload->>'proposal_digest' IS DISTINCT FROM e.proposal_digest OR m.payload->'identity' IS DISTINCT FROM e.identity OR m.payload->>'active_deadline' IS DISTINCT FROM e.new_deadline_ns::text
 OR (m.payload->>'activated_at_boottime_ns')::bigint NOT BETWEEN 0 AND e.old_deadline_ns-1 THEN RAISE EXCEPTION 'R60_ACTIVE_WATCHDOG_PROOF_REQUIRED'; END IF;
 UPDATE company_private.r60_lease_extensions SET state='ACTIVE',active_attestation_id=m.id WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.id AND state='COMMITTED';
 RETURN company_private.r58_finish(c.id,e.id,jsonb_build_object('state','ACTIVE','extension_id',e.id,'new_deadline',e.new_deadline_ns));
END $$;
CREATE FUNCTION company_private.r60_lease_read(p_extension uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;e company_private.r60_lease_extensions%ROWTYPE;r company.process_runs%ROWTYPE;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54 AND operation_id='process.lease_read';
 IF company_private.r54_allowed(x.tenant_id,x.project_id,'process.lease_read',x.task_id,false) IS NOT TRUE THEN RAISE EXCEPTION 'R60_LEASE_READ_DENIED'; END IF;
 PERFORM 1 FROM company.projects WHERE tenant_id=x.tenant_id AND id=x.project_id FOR UPDATE;
 SELECT * INTO STRICT e FROM company_private.r60_lease_extensions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_extension AND state='COMMITTED' FOR SHARE;
 r=company_private.r58_process_current(e.process_id);PERFORM company_private.r58_attempt(r.task_id,r.attempt_id,r.attempt_fencing_epoch);
 IF x.principal_id IS DISTINCT FROM r.controller_id OR r.state IS DISTINCT FROM 'RUNNING' THEN RAISE EXCEPTION 'R60_LEASE_CONTROLLER_READBACK'; END IF;
 RETURN jsonb_build_object('state',e.state,'extension_id',e.id,'proposal_digest',e.proposal_digest,'new_deadline',e.new_deadline_ns,'identity',e.identity);
END $$;
CREATE FUNCTION company_private.r60_process_reconcile(p_process uuid,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;r company.process_runs%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;c company.commands%ROWTYPE;j jsonb;reconciliation_id uuid;
BEGIN
 x=company_private.r58_context('process.reconcile');m=company_private.r58_attestation(p_attestation,'r60.process-observation.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['process_id','capability_id','tuple_digest','host_boot_id','controller_generation','process_identity_digest','cgroup_inode','observer_id','outcome','cgroup_populated','workspace_fenced','no_respawn_intent','usage_zero']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('process',p_process,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_process FOR UPDATE;
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND process_id=r.id;
 -- Deliberately does not call r58_process_current: an expired lease may be stopped.
 IF r.state NOT IN ('STARTING','RUNNING','UNKNOWN_LOCAL','STOP_REQUESTED') OR m.issuer_id IS DISTINCT FROM x.principal_id OR m.issuer_id IN (r.worker_id,r.controller_id) OR j->>'observer_id' IS DISTINCT FROM m.issuer_id::text
 OR NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=m.issuer_id AND kind='VERIFIER')
 OR j->>'process_id' IS DISTINCT FROM r.id::text OR j->>'capability_id' IS DISTINCT FROM cap.id::text OR j->>'tuple_digest' IS DISTINCT FROM cap.tuple_digest OR j->>'host_boot_id' IS DISTINCT FROM r.r55_host_boot_id::text OR j->>'controller_generation' IS DISTINCT FROM r.controller_generation::text
 OR j->>'process_identity_digest' !~ '^[a-f0-9]{64}$' OR jsonb_typeof(j->'cgroup_inode') IS DISTINCT FROM 'number' OR (j->>'cgroup_inode')::bigint<=0 OR j->>'outcome' NOT IN ('RUNNING','EXITED','NOT_STARTED') THEN RAISE EXCEPTION 'R60_INDEPENDENT_EXACT_OBSERVATION_REQUIRED'; END IF;
 IF cap.callback_attestation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM company_private.r58_attestations cb WHERE cb.tenant_id=x.tenant_id AND cb.project_id=x.project_id AND cb.id=cap.callback_attestation_id AND cb.payload->>'process_identity_digest'=j->>'process_identity_digest' AND cb.payload->'cgroup_inode'=j->'cgroup_inode') THEN RAISE EXCEPTION 'R60_CALLBACK_OBSERVATION_IDENTITY_MISMATCH'; END IF;
 IF j->>'outcome'='NOT_STARTED' AND (cap.callback_attestation_id IS NOT NULL OR r.state='RUNNING') THEN RAISE EXCEPTION 'R60_KNOWN_STARTED_PROCESS_CANNOT_BECOME_NOT_STARTED'; END IF;
 IF j->>'outcome'<>'RUNNING' AND (j->'cgroup_populated' IS DISTINCT FROM '0'::jsonb OR j->'workspace_fenced' IS DISTINCT FROM 'true'::jsonb OR j->'no_respawn_intent' IS DISTINCT FROM 'true'::jsonb OR j->'usage_zero' IS DISTINCT FROM 'true'::jsonb) THEN RAISE EXCEPTION 'R60_ACTUAL_QUIESCENCE_REQUIRED'; END IF;
 reconciliation_id=gen_random_uuid();INSERT INTO company_private.r60_process_reconciliations VALUES(x.tenant_id,x.project_id,reconciliation_id,r.id,m.id,j->>'outcome',c.id);
 -- The process trigger requires an intermediate stop request for active runs.
 IF j->>'outcome'<>'RUNNING' AND r.state IN ('STARTING','RUNNING') THEN
  UPDATE company.process_runs SET state='STOP_REQUESTED',revision=revision+1
  WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND company.process_runs.id=r.id AND revision=r.revision
  RETURNING * INTO STRICT r;
 END IF;
 UPDATE company.process_runs SET state=CASE WHEN j->>'outcome'='RUNNING' THEN 'UNKNOWN_LOCAL' ELSE 'STOPPED' END,revision=revision+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=r.id AND revision=r.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_RECONCILIATION_CAS'; END IF;
 -- No acceptance, respawn, root issuance, budget or slot release here.
 RETURN company_private.r58_finish(c.id,reconciliation_id,jsonb_build_object('process_id',r.id,'observation',j->>'outcome','respawn_permitted',false,'release_performed',false));
END $$;
ROLLBACK;
