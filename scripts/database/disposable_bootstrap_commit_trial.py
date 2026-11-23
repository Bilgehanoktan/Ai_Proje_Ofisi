"""Scoped rollback-only compile. Active SQL and inert preview remain unchanged."""
import os,pathlib,subprocess,json,hashlib,re
R=pathlib.Path('/var/lib/ai-proje-ofisi-dbtest');S=R/'storage';B=R/'binary/usr/lib/postgresql/18/bin'
P=pathlib.Path('/mnt/e/Projeler/Ai_Proje_Ofisi');E=os.environ.copy();E['LD_LIBRARY_PATH']=str(R/'binary/usr/lib/x86_64-linux-gnu');E['PGCONNECT_TIMEOUT']='3'
assert os.geteuid()==999
raw=(P/'evidence/disposable_bootstrap_commit.sql').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='3e22ab435b1729c8d8dfa0665dc26b27e8a9b56c2355c765d0de19a70f5727b0'
assert raw.rstrip().endswith(b'COMMIT;')
def run(a,**kw):return subprocess.run([str(x) for x in a],env=E,capture_output=True,text=True,timeout=55,**kw)
def sql(text):return run([B/'psql','-X','-h',S/'socket','-U','aipof-dbtest','-d','postgres','-v','ON_ERROR_STOP=1','-A','-t','-f','-'],input=text)
r={'scope':'SYNTHETIC_BOOTSTRAP_COMMIT_READBACK_NOT_REAL_OWNER_INSTALLATION','company_commit':False};started=False
try:
 started=True
 opts="-k /var/lib/ai-proje-ofisi-dbtest/storage/socket -c listen_addresses='' -c shared_buffers=32MB -c max_connections=5 -c max_worker_processes=0 -c max_parallel_workers=0 -c dynamic_shared_memory_type=mmap -c unix_socket_permissions=0700"
 a=run([B/'pg_ctl','-D',S/'data','-l',S/'journal/compile.log','-o',opts,'-w','-t','15','start']);r['start_exit']=a.returncode
 if a.returncode:raise RuntimeError(a.stderr[-1000:])
 original=(P/'database/sources/001_R53_FIRST_RUN_PHYSICAL_SCHEMA_CANDIDATE.sql').read_text()
 guard=sql(original);r['original_guard_rejected']=guard.returncode!=0 and 'DESIGN_ONLY_G0_OPEN_NOT_AUTHORIZED' in guard.stderr
 if not r['original_guard_rejected']:raise RuntimeError('ORIGINAL_GUARD_NOT_ENFORCED')
 probe=sql("BEGIN; CREATE FUNCTION public.disposable_clock_probe() RETURNS jsonb AS '$libdir/r55_clock_observer','r55_cp_clock_observe_local' LANGUAGE C VOLATILE; SELECT json_build_object('backend_pid',pg_backend_pid(),'observation',public.disposable_clock_probe()); ROLLBACK;")
 if probe.returncode:raise RuntimeError('NATIVE_CLOCK_LOAD_PROBE_FAILED:'+probe.stderr[-1000:])
 observation=next(json.loads(line) for line in probe.stdout.splitlines() if line.startswith('{'))
 r['clock_load_probe']=observation
 o=observation['observation']
 r['clock_preflight_observations']=[o]
 import time
 for attempt in range(10):
  if o.get('source_sync_state')=='SYNC':break
  time.sleep(2)
  repeat=sql("BEGIN; CREATE FUNCTION public.disposable_clock_probe() RETURNS jsonb AS '$libdir/r55_clock_observer','r55_cp_clock_observe_local' LANGUAGE C VOLATILE; SELECT json_build_object('backend_pid',pg_backend_pid(),'observation',public.disposable_clock_probe()); ROLLBACK;")
  if repeat.returncode:raise RuntimeError('CLOCK_PREFLIGHT_PROBE_FAILED')
  observation=next(json.loads(line) for line in repeat.stdout.splitlines() if line.startswith('{'))
  o=observation['observation'];r['clock_preflight_observations'].append(o)
 if o.get('source_sync_state')!='SYNC':raise RuntimeError('CLOCK_NOT_SYNCED_NO_INSTALLATION_WRITES')
 if o['backend_pid']!=observation['backend_pid'] or o['boottime_before_ns']>o['boottime_after_ns'] or o['source_sync_state'] not in ['SYNC','UNKNOWN']:raise RuntimeError('NATIVE_CLOCK_OBSERVATION_BINDING')
 negative=sql("BEGIN; CREATE FUNCTION public.disposable_wrong_symbol() RETURNS jsonb AS '$libdir/r55_clock_observer','invalid_disposable_symbol' LANGUAGE C; ROLLBACK;")
 r['wrong_symbol_rejected']=negative.returncode!=0 and 'invalid_disposable_symbol' in negative.stderr
 if not r['wrong_symbol_rejected']:raise RuntimeError('WRONG_NATIVE_SYMBOL_NOT_REJECTED')
 baseline=sql("SELECT json_build_object('existing_schemas',(SELECT count(*) FROM pg_namespace WHERE nspname IN ('company','company_private')),'existing_roles',(SELECT count(*) FROM pg_roles WHERE rolname=ANY(ARRAY['company_atomic_functions_r55','company_attestation_functions_r58','company_bootstrap_functions_r56','company_bootstrap_transport_r56','company_clock_policy_owner_r57','company_clock_policy_transport_r57','company_clock_runtime_r55','company_context_owner','company_e0_process_functions_r55','company_event_functions_r54','company_execution_functions_r58','company_first_run_functions_r53','company_provisioning_runtime_r55','company_readback_functions_r54','company_receipt_functions_r55','company_receipt_ingest_r55','company_revoke_functions_r53','company_transport_r53','company_transport_r54'])));")
 if baseline.returncode:raise RuntimeError('BASELINE_READBACK_FAILED')
 r['preflight']=json.loads(baseline.stdout.strip())
 if r['preflight']!={'existing_schemas':0,'existing_roles':0}:raise RuntimeError('PREEXISTING_OBJECTS_NO_AUTOMATIC_CLEANUP')
 compile=sql(raw.decode());r['catalog_json']=[json.loads(l) for l in compile.stdout.splitlines() if l.startswith('{')];r['compile_exit']=compile.returncode;r['compile_stderr']=compile.stderr[-6000:];r['compile_stdout_tail']=compile.stdout[-3000:]
 match=re.search(r'<stdin>:(\d+):',compile.stderr)
 if match:
  line=int(match.group(1));lines=raw.decode().splitlines();r['execution_line']=line;r['nearest_source']=next((x for x in reversed(lines[:line]) if x.startswith('-- SOURCE ')),None)
 if compile.returncode!=0:
  failed=sql("SELECT json_build_object('company_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company'),'company_private_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company_private'));")
  r['after_failed_transaction']=json.loads(failed.stdout.strip()) if failed.returncode==0 else None
  raise RuntimeError('BOOTSTRAP_COMPILE_FAILED_NO_COMMIT')
 r['company_commit']=True
 readback=sql("SELECT json_build_object('bootstrap_receipts',(SELECT count(*) FROM company_private.bootstrap_receipts),'objectives',(SELECT count(*) FROM company.objectives),'plans',(SELECT count(*) FROM company.plans),'consumed',(SELECT count(*) FROM company_private.installation_bootstrap_control WHERE state='CONSUMED'),'audit_events',(SELECT count(*) FROM company.audit_events),'outbox_events',(SELECT count(*) FROM company.outbox),'project_grants',(SELECT count(*) FROM company.project_grants),'exact_receipt_witnesses',(SELECT count(*) FROM company_private.bootstrap_receipts b JOIN company.commands c ON c.tenant_id=b.tenant_id AND c.id=b.command_id WHERE c.state='SUCCEEDED' AND c.r55_result_digest=b.r56_result_digest AND c.principal_id=b.accepted_human_id));")
 r['independent_committed_readback']=json.loads(readback.stdout.strip()) if readback.returncode==0 else {'error':readback.stderr[-1000:]}
 session_probe=run([P/'.runtime/kernel-linux314/bin/python','-B',P/'scripts/database/disposable_session_check.py'])
 r['session_probe_exit']=session_probe.returncode;r['session_probe_stdout']=session_probe.stdout[-2000:];r['session_probe_stderr']=session_probe.stderr[-2000:]
 clean=sql('BEGIN; DROP SCHEMA company CASCADE; DROP SCHEMA company_private CASCADE; DROP OWNED BY company_atomic_functions_r55; DROP OWNED BY company_attestation_functions_r58; DROP OWNED BY company_bootstrap_functions_r56; DROP OWNED BY company_bootstrap_transport_r56; DROP OWNED BY company_clock_policy_owner_r57; DROP OWNED BY company_clock_policy_transport_r57; DROP OWNED BY company_clock_runtime_r55; DROP OWNED BY company_context_owner; DROP OWNED BY company_e0_process_functions_r55; DROP OWNED BY company_event_functions_r54; DROP OWNED BY company_execution_functions_r58; DROP OWNED BY company_first_run_functions_r53; DROP OWNED BY company_provisioning_runtime_r55; DROP OWNED BY company_readback_functions_r54; DROP OWNED BY company_receipt_functions_r55; DROP OWNED BY company_receipt_ingest_r55; DROP OWNED BY company_revoke_functions_r53; DROP OWNED BY company_transport_r53; DROP OWNED BY company_transport_r54; DROP ROLE company_atomic_functions_r55; DROP ROLE company_attestation_functions_r58; DROP ROLE company_bootstrap_functions_r56; DROP ROLE company_bootstrap_transport_r56; DROP ROLE company_clock_policy_owner_r57; DROP ROLE company_clock_policy_transport_r57; DROP ROLE company_clock_runtime_r55; DROP ROLE company_context_owner; DROP ROLE company_e0_process_functions_r55; DROP ROLE company_event_functions_r54; DROP ROLE company_execution_functions_r58; DROP ROLE company_first_run_functions_r53; DROP ROLE company_provisioning_runtime_r55; DROP ROLE company_readback_functions_r54; DROP ROLE company_receipt_functions_r55; DROP ROLE company_receipt_ingest_r55; DROP ROLE company_revoke_functions_r53; DROP ROLE company_transport_r53; DROP ROLE company_transport_r54; COMMIT;');r['cleanup_exit']=clean.returncode;r['cleanup_stderr']=clean.stderr[-1500:]
 check=sql("SELECT json_build_object('company_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company'),'company_private_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company_private'),'smoke_rows',(SELECT count(*) FROM public.disposable_smoke_probe));")
 if check.returncode:raise RuntimeError('POST_ROLLBACK_READBACK_FAILED:'+check.stderr[-1000:])
 r['after_rollback']=json.loads(check.stdout.strip());r['compile_pass']=compile.returncode==0;r['cleanup_verified']=not r['after_rollback']['company_exists'] and not r['after_rollback']['company_private_exists'];r['rollback_verified']=False
except Exception as e:r['error']=str(e)
finally:
 if started:r['stop_exit']=run([B/'pg_ctl','-D',S/'data','-m','fast','-w','-t','10','stop']).returncode
 r['db_stopped']=not (S/'data/postmaster.pid').exists()
 print(json.dumps(r),flush=True)
raise SystemExit(0 if r.get('compile_pass') and r.get('session_probe_exit')==0 and r.get('cleanup_verified') and r['db_stopped'] else 1)
