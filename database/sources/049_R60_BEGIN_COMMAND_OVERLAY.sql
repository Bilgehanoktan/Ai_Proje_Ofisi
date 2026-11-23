BEGIN;
DO $$ BEGIN RAISE EXCEPTION 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED'; END $$;
CREATE OR REPLACE FUNCTION company_private.r58_begin_command(p_key text,p_correlation uuid,p_request jsonb) RETURNS company.commands
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE x company_private.request_contexts%ROWTYPE;c company.commands%ROWTYPE;d text;
BEGIN
 SELECT * INTO STRICT x FROM company_private.request_contexts WHERE backend_pid=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND db_login=session_user AND writer_generation=54;
 x=company_private.r58_context(x.operation_id);
 IF p_key IS NULL OR p_key !~ '^[A-Za-z0-9_.:-]{16,128}$' OR p_correlation IS NULL OR jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'R58_COMMAND_BINDING'; END IF;
 d=encode(sha256(convert_to(p_request::text,'UTF8')),'hex');
 c=company_private.r60_find_command(p_key);
 IF c.id IS NOT NULL THEN
  IF c.payload_digest IS DISTINCT FROM d OR c.state IS DISTINCT FROM 'SUCCEEDED' OR c.r55_result_digest IS NULL THEN RAISE EXCEPTION 'R58_IDEMPOTENCY_CONFLICT_OR_INCOMPLETE'; END IF;
  RETURN c;
 END IF;
 INSERT INTO company.commands(tenant_id,id,principal_id,operation,idempotency_key,payload_digest,correlation_id,state,result_ref)
 VALUES(x.tenant_id,gen_random_uuid(),x.principal_id,x.operation_id,p_key,d,p_correlation,'RUNNING',NULL) RETURNING * INTO c;
 RETURN c;
END $$;
ROLLBACK;
