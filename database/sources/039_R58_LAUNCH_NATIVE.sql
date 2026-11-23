BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE FUNCTION company_private.r58_launch_reserve(p_task uuid,p_attempt uuid,p_fence bigint,p_manifest uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;a company.attempts%ROWTYPE;m company_private.r58_attestations%ROWTYPE;lp company_private.r58_lease_policies%ROWTYPE;
 h company_private.r58_workspace_heads%ROWTYPE;host company.host_registrations%ROWTYPE;v company.budget_versions%ROWTYPE;c company.commands%ROWTYPE;
 j jsonb;cl jsonb;cap uuid;process uuid;reservation uuid;tuple jsonb;now_bounds jsonb;remaining_ns numeric;
BEGIN
 x=company_private.r58_context('process.launch_reserve');
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('task_id',p_task,'attempt_id',p_attempt,'fence',p_fence,'manifest',p_manifest));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 a=company_private.r58_attempt(p_task,p_attempt,p_fence);
 m=company_private.r58_attestation(p_manifest,'r58.launch-manifest.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['task_id','attempt_id','fencing_epoch','workspace_id','head_digest','host_id','host_revision','host_generation','host_boot_id','controller_id','controller_generation','executable_digest','argv','budget_id','budget_revision','admission_artifact_id','claims']);
 SELECT * INTO STRICT lp FROM company_private.r58_lease_policies WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND revision=a.r58_policy_revision AND enabled FOR SHARE;
 SELECT * INTO STRICT h FROM company_private.r58_workspace_heads WHERE tenant_id=x.tenant_id AND project_id=x.project_id FOR SHARE;
 SELECT hr.* INTO STRICT host FROM company.host_registrations hr JOIN company.projects p ON p.tenant_id=hr.tenant_id AND p.id=hr.project_id AND p.host_registration_id=hr.id AND p.host_registration_revision=hr.revision AND p.instance_generation=hr.bound_generation
 WHERE p.tenant_id=x.tenant_id AND p.id=x.project_id AND hr.state='BOUND_NOT_LEASED' FOR SHARE OF hr;
 IF a.worker_id IS DISTINCT FROM x.principal_id OR m.issuer_id IS DISTINCT FROM lp.controller_id OR m.issuer_id=a.worker_id
 OR j->>'task_id' IS DISTINCT FROM p_task::text OR j->>'attempt_id' IS DISTINCT FROM p_attempt::text OR j->>'fencing_epoch' IS DISTINCT FROM p_fence::text
 OR j->>'head_digest' IS DISTINCT FROM h.head_digest OR j->>'head_digest' IS DISTINCT FROM a.r58_head_digest OR j->>'workspace_id' IS DISTINCT FROM h.workspace_id::text
 OR j->>'host_id' IS DISTINCT FROM host.id::text OR j->>'host_revision' IS DISTINCT FROM host.revision::text OR j->>'host_generation' IS DISTINCT FROM host.bound_generation::text
 OR j->>'controller_id' IS DISTINCT FROM lp.controller_id::text OR j->>'executable_digest' IS DISTINCT FROM lp.executable_digest
 OR (j->>'controller_generation')::bigint<1 OR jsonb_typeof(j->'argv') IS DISTINCT FROM 'array' OR jsonb_array_length(j->'argv') NOT BETWEEN 1 AND 64
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(j->'argv') z WHERE jsonb_typeof(z) IS DISTINCT FROM 'string' OR length(z#>>'{}')>4096)
 OR jsonb_typeof(j->'claims') IS DISTINCT FROM 'array' OR jsonb_array_length(j->'claims') NOT BETWEEN 1 AND 16
 OR EXISTS(SELECT 1 FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=p_task AND attempt_id=p_attempt) THEN RAISE EXCEPTION 'R58_LAUNCH_EXACT_BINDING_OR_NO_RESPAWN'; END IF;
 now_bounds=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 IF j->>'host_boot_id' IS DISTINCT FROM now_bounds->>'host_boot_id' THEN RAISE EXCEPTION 'R58_DB_LOCAL_BOOT_REQUIRED'; END IF;
 remaining_ns=floor(extract(epoch FROM (least(a.lease_expires_at,lp.valid_until)-(now_bounds->>'utc_upper_bound')::timestamptz))*1000000000);
 IF remaining_ns<=0 THEN RAISE EXCEPTION 'R58_LAUNCH_LEASE_EXPIRED'; END IF;
 SELECT * INTO STRICT v FROM company.budget_versions WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND budget_id=(j->>'budget_id')::uuid AND revision=(j->>'budget_revision')::bigint FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM company.artifacts art WHERE art.tenant_id=x.tenant_id AND art.project_id=x.project_id AND art.task_id=p_task AND art.attempt_id=p_attempt AND art.id=(j->>'admission_artifact_id')::uuid AND art.state='AVAILABLE' AND art.sha256=m.raw_digest) THEN RAISE EXCEPTION 'R58_MANIFEST_ARTIFACT_DIGEST'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company.principals WHERE tenant_id=x.tenant_id AND id=v.approved_by AND kind='HUMAN') THEN RAISE EXCEPTION 'R58_HUMAN_LOCAL_ZERO_BUDGET_REQUIRED'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(j->'claims') z GROUP BY z->>'slot_id' HAVING count(*)>1) THEN RAISE EXCEPTION 'R58_DUPLICATE_SLOT'; END IF;
 cap=gen_random_uuid();process=gen_random_uuid();reservation=gen_random_uuid();
 INSERT INTO company.budget_reservations(tenant_id,project_id,id,budget_id,budget_revision,task_id,attempt_id,attempt_fencing_epoch,semantic_key,payload_digest,admission_artifact_id,amount_minor,state,command_id)
 VALUES(x.tenant_id,x.project_id,reservation,v.budget_id,v.revision,p_task,p_attempt,p_fence,'r58:'||p_attempt::text,m.raw_digest,(j->>'admission_artifact_id')::uuid,0,'RESERVED',c.id);
 INSERT INTO company.process_runs(tenant_id,project_id,id,task_id,attempt_id,attempt_fencing_epoch,worker_lease_id,worker_id,qualification_id,lease_expires_at,workspace_id,host_registration_id,host_registration_revision,host_generation,controller_id,controller_generation,kind,state,reservation_id,manifest_artifact_id,manifest_digest,semantic_run_digest,start_command_id,r55_host_boot_id)
 VALUES(x.tenant_id,x.project_id,process,p_task,p_attempt,p_fence,gen_random_uuid(),a.worker_id,a.admission_qualification_id,a.lease_expires_at,h.workspace_id,host.id,host.revision,host.bound_generation,lp.controller_id,(j->>'controller_generation')::bigint,'TASK_EXECUTION','REQUESTED',reservation,(j->>'admission_artifact_id')::uuid,m.raw_digest,encode(sha256(convert_to(jsonb_build_array(p_task,p_attempt,p_fence,m.raw_digest)::text,'UTF8')),'hex'),c.id,(j->>'host_boot_id')::uuid);
 FOR cl IN SELECT value FROM jsonb_array_elements(j->'claims') ORDER BY value->>'slot_id' LOOP
  PERFORM company_private.r58_shape(cl,ARRAY['slot_id','units']);
  IF jsonb_typeof(cl->'units') IS DISTINCT FROM 'number' OR cl->>'units' !~ '^[1-9][0-9]*$' THEN RAISE EXCEPTION 'R58_FINITE_RESOURCE_UNITS'; END IF;
  UPDATE company.resource_slots SET reserved=reserved+(cl->>'units')::integer WHERE tenant_id=x.tenant_id AND id=(cl->>'slot_id')::uuid AND capacity-reserved>=(cl->>'units')::integer;
  IF NOT FOUND THEN RAISE EXCEPTION 'R58_RESOURCE_CAPACITY'; END IF;
  INSERT INTO company.resource_claims(tenant_id,project_id,process_run_id,slot_id,units,state) VALUES(x.tenant_id,x.project_id,process,(cl->>'slot_id')::uuid,(cl->>'units')::integer,'HELD');
 END LOOP;
 tuple=jsonb_build_object('capability_id',cap,'tenant_id',x.tenant_id,'project_id',x.project_id,'task_id',p_task,'attempt_id',p_attempt,'fencing_epoch',p_fence,'worker_id',a.worker_id,'qualification_id',a.admission_qualification_id,'binding_digest',a.r58_binding_digest,'workspace_id',h.workspace_id,'head_digest',h.head_digest,'host_id',host.id,'host_revision',host.revision,'host_generation',host.bound_generation,'host_boot_id',j->>'host_boot_id','controller_id',lp.controller_id,'controller_generation',j->'controller_generation','process_id',process,'executable_digest',lp.executable_digest,'argv',j->'argv','reservation_id',reservation,'claims',j->'claims','lease_policy_revision',lp.revision,'not_after_boottime_ns',(now_bounds->>'boottime_after_ns')::numeric+remaining_ns);
 INSERT INTO company_private.r58_launch_capabilities(tenant_id,project_id,id,process_id,tuple,tuple_digest,state) VALUES(x.tenant_id,x.project_id,cap,process,tuple,encode(sha256(convert_to(tuple::text,'UTF8')),'hex'),'RESERVED');
 PERFORM company_private.r58_process_current(process);
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,a.lease_expires_at);
 RETURN company_private.r58_finish(c.id,cap,jsonb_build_object('capability_id',cap,'process_id',process,'tuple',tuple,'spawned',false));
END $$;

CREATE FUNCTION company_private.r58_launch_consume(p_capability uuid,p_digest text,p_key text,p_correlation uuid) RETURNS jsonb
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
 UPDATE company_private.r58_launch_capabilities SET state='CONSUMED',consume_command_id=c.id WHERE tenant_id=cap.tenant_id AND project_id=cap.project_id AND id=cap.id AND state='RESERVED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_CAPABILITY_CONSUME_CAS'; END IF;
 UPDATE company.process_runs SET state='STARTING',revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND revision=r.revision AND state='REQUESTED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_PROCESS_START_CAS'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,a.lease_expires_at);
 RETURN company_private.r58_finish(c.id,cap.id,jsonb_build_object('capability_id',cap.id,'tuple',cap.tuple,'tuple_raw',cap.tuple::text,'tuple_digest',cap.tuple_digest,'spawn_permitted',true,'release_only_after_commit',true));
END $$;

CREATE FUNCTION company_private.r58_launch_callback(p_capability uuid,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;cap company_private.r58_launch_capabilities%ROWTYPE;m company_private.r58_attestations%ROWTYPE;r company.process_runs%ROWTYPE;a company.attempts%ROWTYPE;c company.commands%ROWTYPE;j jsonb;b jsonb;
BEGIN
 x=company_private.r58_context('process.launch_callback');m=company_private.r58_attestation(p_attestation,'r58.launch-callback.v1');j=m.payload;
 PERFORM company_private.r58_shape(j,ARRAY['capability_id','tuple_digest','controller_generation','host_boot_id','process_identity_digest','isolation_digest','cgroup_inode','outcome']);
 c=company_private.r58_begin_command(p_key,p_correlation,jsonb_build_object('capability',p_capability,'attestation',p_attestation));
 IF c.state='SUCCEEDED' THEN RETURN company_private.r58_finish(c.id,c.result_ref,c.r55_result_payload); END IF;
 SELECT * INTO STRICT cap FROM company_private.r58_launch_capabilities WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=p_capability FOR UPDATE;
 a=company_private.r58_attempt((cap.tuple->>'task_id')::uuid,(cap.tuple->>'attempt_id')::uuid,(cap.tuple->>'fencing_epoch')::bigint);
 SELECT * INTO STRICT r FROM company.process_runs WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=cap.process_id FOR UPDATE;
 PERFORM company_private.r58_process_current(r.id);
 IF cap.state IS DISTINCT FROM 'CONSUMED' OR m.issuer_id IS DISTINCT FROM r.controller_id OR x.principal_id IS DISTINCT FROM r.controller_id
 OR j->>'capability_id' IS DISTINCT FROM cap.id::text OR j->>'tuple_digest' IS DISTINCT FROM cap.tuple_digest
 OR j->>'host_boot_id' IS DISTINCT FROM cap.tuple->>'host_boot_id' OR j->>'controller_generation' IS DISTINCT FROM r.controller_generation::text
 OR jsonb_typeof(j->'cgroup_inode') IS DISTINCT FROM 'number' OR j->>'cgroup_inode' !~ '^[1-9][0-9]*$'
 OR j->>'process_identity_digest' !~ '^[a-f0-9]{64}$' OR j->>'isolation_digest' !~ '^[a-f0-9]{64}$' OR j->>'outcome' NOT IN ('RUNNING','UNKNOWN_LOCAL') THEN RAISE EXCEPTION 'R58_CALLBACK_BINDING'; END IF;
 b=company_private.r55_cp_clock_current_bounds(x.tenant_id,x.project_id);
 IF b->>'host_boot_id' IS DISTINCT FROM j->>'host_boot_id' OR (b->>'boottime_after_ns')::numeric>=(cap.tuple->>'not_after_boottime_ns')::numeric THEN RAISE EXCEPTION 'R58_STALE_CALLBACK_REQUIRES_RECONCILIATION'; END IF;
 UPDATE company.process_runs SET state=j->>'outcome',revision=revision+1 WHERE tenant_id=r.tenant_id AND project_id=r.project_id AND id=r.id AND state='STARTING' AND revision=r.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_CALLBACK_PROCESS_CAS'; END IF;
 UPDATE company_private.r58_launch_capabilities SET state=j->>'outcome',callback_attestation_id=m.id WHERE tenant_id=cap.tenant_id AND project_id=cap.project_id AND id=cap.id AND state='CONSUMED';
 IF NOT FOUND THEN RAISE EXCEPTION 'R58_CALLBACK_CAPABILITY_CAS'; END IF;
 UPDATE company.attempts SET state=CASE WHEN j->>'outcome'='RUNNING' THEN 'RUNNING' ELSE 'UNKNOWN_RECOVERY' END WHERE tenant_id=a.tenant_id AND project_id=a.project_id AND task_id=a.task_id AND id=a.id;
 RETURN company_private.r58_finish(c.id,cap.id,jsonb_build_object('process_id',r.id,'capability_id',cap.id,'outcome',j->>'outcome','process_identity_digest',j->>'process_identity_digest','isolation_digest',j->>'isolation_digest','callback_attestation_id',m.id,'respawn_permitted',false));
END $$;
ROLLBACK;
