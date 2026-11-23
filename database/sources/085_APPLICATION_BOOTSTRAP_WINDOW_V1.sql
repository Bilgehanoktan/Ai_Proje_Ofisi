BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
-- Exposes the existing r56 trusted local clock/root check, never a new clock
-- oracle, approval, provisioning writer or general runtime authorization.
CREATE FUNCTION company_private.bootstrap_window_readback_v1(
 p_installation uuid,p_generation bigint,p_enrollment text,p_boot uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE result jsonb;
BEGIN
 IF session_user<>'company_provisioning_runtime_r55' THEN
  RAISE EXCEPTION 'BOOTSTRAP_WINDOW_PROVISIONER_REQUIRED';
 END IF;
 IF num_nulls(p_installation,p_generation,p_enrollment,p_boot)<>0
 OR p_generation<1 OR p_generation>9007199254740991 OR p_enrollment !~ '^[a-f0-9]{64}$'
 THEN RAISE EXCEPTION 'EXACT_BOOTSTRAP_WINDOW_INPUT_REQUIRED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM company_private.r55_setup_root_enrollments e
 JOIN company_private.installation_bootstrap_control b USING(installation_id,generation)
 WHERE e.installation_id=p_installation AND e.generation=p_generation
 AND e.enrollment_digest=p_enrollment AND e.host_boot_id=p_boot
 AND b.state IN ('ARMED','CONSUMED'))
 THEN RAISE EXCEPTION 'CURRENT_BOOTSTRAP_WINDOW_NOT_ENROLLED'; END IF;
 result=company_private.r56_root_bounds(p_installation);
 IF result->>'installation_id' IS DISTINCT FROM p_installation::text
 OR result->>'generation' IS DISTINCT FROM p_generation::text
 OR result->>'host_boot_id' IS DISTINCT FROM p_boot::text
 THEN RAISE EXCEPTION 'CURRENT_BOOTSTRAP_WINDOW_CHANGED'; END IF;
 RETURN result || jsonb_build_object('enrollment_digest',p_enrollment,
  'authorization','BOOTSTRAP_WINDOW_ONLY_NOT_RUNTIME','new_grants',0);
END $$;
ALTER FUNCTION company_private.bootstrap_window_readback_v1(uuid,bigint,text,uuid) OWNER TO company_bootstrap_functions_r56;
REVOKE ALL ON FUNCTION company_private.bootstrap_window_readback_v1(uuid,bigint,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION company_private.bootstrap_window_readback_v1(uuid,bigint,text,uuid) TO company_provisioning_runtime_r55;
ROLLBACK;
