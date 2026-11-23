-- Exercise the predicates extracted from the installed function bodies. Synthetic
-- rows have production column types. No domain records or sessions are issued.
SET LOCAL plpgsql.variable_conflict = 'error';

CREATE TEMP TABLE probe_projects AS TABLE company.projects WITH NO DATA;
CREATE TEMP TABLE probe_hosts AS TABLE company.host_registrations WITH NO DATA;
CREATE TEMP TABLE probe_consumptions AS TABLE company_private.r60_tool_consumptions WITH NO DATA;
CREATE TEMP TABLE probe_attestations AS TABLE company_private.r58_attestations WITH NO DATA;

DO $fixture$
DECLARE
  tenant uuid := gen_random_uuid();
  project uuid := gen_random_uuid();
  host_id uuid := gen_random_uuid();
  request_id uuid := gen_random_uuid();
  process_id uuid := gen_random_uuid();
  proof_id uuid := gen_random_uuid();
  patch jsonb;
  host jsonb;
  body text;
  predicate text;
  harness text;
BEGIN
  INSERT INTO probe_projects (tenant_id,id,host_registration_id,host_registration_revision,instance_generation)
    VALUES (tenant,project,host_id,1,2);
  INSERT INTO probe_hosts (tenant_id,project_id,id,revision,bound_generation,state)
    VALUES (tenant,project,host_id,1,2,'BOUND_NOT_LEASED');
  host := jsonb_build_object('host_id',host_id,'host_revision',1,'host_generation',2);
  SELECT prosrc INTO STRICT body FROM pg_proc
    WHERE oid='company_private.r58_workspace_current_head(uuid,text,uuid)'::regprocedure;
  predicate := substring(body FROM 'OR NOT EXISTS\((SELECT 1 FROM company\.projects p JOIN company\.host_registrations.*?)\) THEN RAISE EXCEPTION ''R58_WORKSPACE_HOST_BINDING''');
  IF predicate IS NULL THEN RAISE EXCEPTION 'workspace probe extraction failed'; END IF;
  predicate := replace(replace(predicate,'company.projects','pg_temp.probe_projects'),
                       'company.host_registrations','pg_temp.probe_hosts');
  harness := format($sql$
    DO $test$ DECLARE x company_private.request_contexts%%ROWTYPE;
      h company_private.r58_workspace_heads%%ROWTYPE; v jsonb := %L;
    BEGIN
      x.tenant_id := %L; x.project_id := %L;
      IF NOT EXISTS(%s) THEN RAISE EXCEPTION 'matching host rejected'; END IF;
      v := v || '{"host_generation":3}'::jsonb;
      IF EXISTS(%s) THEN RAISE EXCEPTION 'stale host accepted'; END IF;
    END $test$
  $sql$,host,tenant,project,predicate,predicate);
  EXECUTE harness;

  patch := jsonb_build_object('tool_request_id',request_id,'process_id',process_id,
    'request_digest',repeat('a',64),'base_head',repeat('b',64),
    'result_head',repeat('c',64),'patch_digest',repeat('d',64));
  INSERT INTO probe_consumptions
    (tenant_id,project_id,kernel_request_id,process_id,frame_digest,state,effect_attestation_id)
    VALUES (tenant,project,request_id,process_id,patch->>'request_digest','SUCCEEDED',proof_id);
  INSERT INTO probe_attestations (tenant_id,project_id,id,profile,payload)
    VALUES (tenant,project,proof_id,'r60.tool-effect.v1',
            patch || jsonb_build_object('effect_digest',patch->>'patch_digest'));
  SELECT prosrc INTO STRICT body FROM pg_proc
    WHERE oid='company_private.r58_patch_receipt(uuid,uuid,bigint,uuid,text,uuid)'::regprocedure;
  predicate := substring(body FROM 'IF NOT EXISTS\((SELECT 1 FROM company_private\.r60_tool_consumptions.*?)\) THEN RAISE EXCEPTION ''R60_COMPLETED_PATCH_EFFECT_REQUIRED''');
  IF predicate IS NULL THEN RAISE EXCEPTION 'patch probe extraction failed'; END IF;
  predicate := replace(replace(predicate,'company_private.r60_tool_consumptions','pg_temp.probe_consumptions'),
                       'company_private.r58_attestations','pg_temp.probe_attestations');
  harness := format($sql$
    DO $test$ DECLARE x company_private.request_contexts%%ROWTYPE;
      m company_private.r58_attestations%%ROWTYPE; j jsonb := %L;
    BEGIN
      x.tenant_id := %L; x.project_id := %L;
      IF NOT EXISTS(%s) THEN RAISE EXCEPTION 'matching effect rejected'; END IF;
      j := j || jsonb_build_object('patch_digest',repeat('e',64));
      IF EXISTS(%s) THEN RAISE EXCEPTION 'mismatched effect accepted'; END IF;
    END $test$
  $sql$,patch,tenant,project,predicate,predicate);
  EXECUTE harness;
END $fixture$;
SELECT 'WORKSPACE_PATCH_PREDICATES_PASS';
