BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
DO $dependency$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='company_provisioning_runtime_r55' AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole) THEN
  RAISE EXCEPTION 'PROVISIONING_ROLE_DEPENDENCY_NOT_INSTALLED';
 END IF;
END $dependency$;
-- Exact provisioning metadata readback, not current authority or grant issuance.
-- No table SELECT rights or role membership are given to callers.
CREATE ROLE company_bootstrap_readback_v1 NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT USAGE ON SCHEMA company,company_private TO company_bootstrap_readback_v1;
GRANT USAGE ON SCHEMA company_private TO company_provisioning_runtime_r55;
GRANT SELECT(installation_id,generation,tenant_id,project_id,accepted_human_id,command_id,payload_digest,setup_manifest_digest,initial_grants_digest,r56_result_digest,r56_final_proof) ON company_private.bootstrap_receipts TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company_private.bootstrap_receipts FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(installation_id,generation,state,payload_digest,expected_tenant_id,expected_project_id,expected_human_id) ON company_private.installation_bootstrap_control TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company_private.installation_bootstrap_control FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(tenant_id,id,kind) ON company.principals TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company.principals FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(tenant_id,principal_id,role) ON company.memberships TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company.memberships FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(tenant_id,id,principal_id,operation,state,result_ref,payload_digest,r55_source_revision,r55_result_digest,r55_result_payload,r55_audit_id,correlation_id) ON company.commands TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company.commands FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(tenant_id,id,kind,actor_id,correlation_id) ON company.audit_events TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company.audit_events FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');
GRANT SELECT(tenant_id,project_id,event_instance_id,kind,project_sequence,event_writer_generation,payload,aggregate_id,aggregate_revision,event_digest) ON company.outbox TO company_bootstrap_readback_v1;
CREATE POLICY application_bootstrap_readback_v1 ON company.outbox FOR SELECT TO company_bootstrap_readback_v1 USING(session_user='company_provisioning_runtime_r55');

CREATE FUNCTION company_private.bootstrap_receipt_readback_v1(
 p_installation uuid,p_generation bigint,p_tenant uuid,p_project uuid,p_human uuid,p_command uuid,
 p_payload text,p_setup text,p_initial text,p_result text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE matches integer;
BEGIN
 IF session_user<>'company_provisioning_runtime_r55' THEN
  RAISE EXCEPTION 'BOOTSTRAP_READBACK_PROVISIONER_REQUIRED';
 END IF;
 IF num_nulls(p_installation,p_generation,p_tenant,p_project,p_human,p_command,p_payload,p_setup,p_initial,p_result)<>0
 OR p_generation<1 OR p_generation>9007199254740991
 OR p_payload !~ '^[a-f0-9]{64}$' OR p_setup !~ '^[a-f0-9]{64}$'
 OR p_initial !~ '^[a-f0-9]{64}$' OR p_result !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'EXACT_BOOTSTRAP_READBACK_INPUT_REQUIRED'; END IF;
 SELECT count(*) INTO matches FROM (SELECT 1
FROM company_private.bootstrap_receipts b
JOIN company_private.installation_bootstrap_control ctl ON ctl.installation_id=b.installation_id
JOIN company.principals p ON p.tenant_id=b.tenant_id AND p.id=b.accepted_human_id
JOIN company.memberships m ON m.tenant_id=p.tenant_id AND m.principal_id=p.id
JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id
JOIN company.audit_events a ON a.tenant_id=c.tenant_id AND a.id=c.r55_audit_id
JOIN company.outbox e ON e.tenant_id=c.tenant_id AND e.project_id=b.project_id AND e.event_instance_id=c.id
WHERE b.installation_id=p_installation AND b.generation=p_generation
AND ctl.state='CONSUMED' AND ctl.payload_digest=b.payload_digest
AND ctl.generation=b.generation AND ctl.expected_tenant_id=b.tenant_id AND ctl.expected_project_id=b.project_id
AND ctl.expected_human_id=b.accepted_human_id
AND p.kind='HUMAN' AND m.role='OWNER'
AND c.operation='trusted_setup.consume' AND c.principal_id=b.accepted_human_id
AND c.state='SUCCEEDED' AND c.result_ref=b.installation_id AND c.payload_digest=b.payload_digest
AND c.r55_source_revision='r56' AND c.r55_result_digest=b.r56_result_digest
AND b.r56_final_proof IS NOT NULL AND b.r56_final_proof->>'phase'='COMMIT_CUT'
AND c.r55_result_payload->'final_proof'=b.r56_final_proof
AND b.r56_final_proof->>'installation_id'=b.installation_id::text
AND b.r56_final_proof->>'generation'=b.generation::text
AND b.r56_final_proof->>'manifest_digest'=b.payload_digest
AND c.r55_result_digest=encode(sha256(convert_to(jsonb_build_array(c.id,c.payload_digest,b.installation_id,c.r55_result_payload)::text,'UTF8')),'hex')
AND a.kind='InstallationBootstrapped' AND a.actor_id=c.principal_id AND a.correlation_id=c.correlation_id
AND e.kind='InstallationBootstrapped' AND e.project_sequence=1 AND e.event_writer_generation=54
AND e.payload->>'result_digest'=c.r55_result_digest AND e.aggregate_id=b.project_id AND e.aggregate_revision=0
AND e.payload->>'request_digest'=c.payload_digest
AND e.event_digest=encode(sha256(convert_to(jsonb_build_array(e.aggregate_id,e.aggregate_revision,e.kind,e.payload)::text,'UTF8')),'hex')
AND b.tenant_id=p_tenant AND b.project_id=p_project AND b.accepted_human_id=p_human
AND b.command_id=p_command AND b.payload_digest=p_payload
AND b.setup_manifest_digest=p_setup AND b.initial_grants_digest=p_initial AND b.r56_result_digest=p_result
LIMIT 2) AS witnesses;
 IF matches<>1 THEN RAISE EXCEPTION 'BOOTSTRAP_READBACK_WITNESS_MISMATCH'; END IF;
 RETURN jsonb_build_object('installation_id',p_installation,'generation',p_generation,
  'tenant_id',p_tenant,'project_id',p_project,'accepted_human_id',p_human,'command_id',p_command,
  'payload_digest',p_payload,'setup_manifest_digest',p_setup,'initial_grants_digest',p_initial,
  'r56_result_digest',p_result,'readback','EXACT_COMMITTED_WITNESS_MATCH',
  'authorization','NOT_VERIFIED','new_grants',0);
END $$;
ALTER FUNCTION company_private.bootstrap_receipt_readback_v1(uuid,bigint,uuid,uuid,uuid,uuid,text,text,text,text) OWNER TO company_bootstrap_readback_v1;
REVOKE ALL ON FUNCTION company_private.bootstrap_receipt_readback_v1(uuid,bigint,uuid,uuid,uuid,uuid,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.bootstrap_receipt_readback_v1(uuid,bigint,uuid,uuid,uuid,uuid,text,text,text,text) TO company_provisioning_runtime_r55;
ROLLBACK;
