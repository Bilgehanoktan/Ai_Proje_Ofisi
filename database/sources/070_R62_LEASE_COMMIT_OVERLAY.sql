BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r60_lease_commit(p_extension uuid,p_attestation uuid,p_key text,p_correlation uuid) RETURNS jsonb
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
 IF e.new_expires_at>least(company_private.r61_grant_deadline(x.grant_chain_ids,x.principal_id,'process.lease_commit',r.task_id),company_private.r61_worker_deadline(r.task_id,r.attempt_id),company_private.r62_prepared_deadline(e.id)) THEN RAISE EXCEPTION 'R62_EXTENSION_EXCEEDS_PREPARED_OR_CURRENT_AUTHORITY'; END IF;
 PERFORM company_private.r55_cp_require_not_expired(x.tenant_id,x.project_id,e.new_expires_at);
 UPDATE company.process_runs SET lease_expires_at=e.new_expires_at,revision=revision+1 WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=r.id AND revision=r.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'R60_LEASE_PROCESS_CAS'; END IF;
 UPDATE company.attempts SET lease_expires_at=e.new_expires_at WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND task_id=r.task_id AND id=r.attempt_id AND fencing_epoch=r.attempt_fencing_epoch;
 UPDATE company_private.r60_lease_extensions SET state='COMMITTED',prepared_attestation_id=m.id WHERE tenant_id=x.tenant_id AND project_id=x.project_id AND id=e.id AND state='PREPARED';
 INSERT INTO company_private.r61_extension_authorities VALUES(x.tenant_id,x.project_id,e.id,x.principal_id,'COMMITTED',x.grant_chain_ids);
 RETURN company_private.r58_finish(c.id,e.id,jsonb_build_object('state','COMMITTED','extension_id',e.id,'proposal_digest',e.proposal_digest,'new_deadline',e.new_deadline_ns,'tool_use_allowed',false));
END $$;
ROLLBACK;
