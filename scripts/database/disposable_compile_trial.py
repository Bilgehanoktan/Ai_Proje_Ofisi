"""Scoped rollback-only compile. Active SQL and inert preview remain unchanged."""
import os,pathlib,subprocess,json,hashlib,re
R=pathlib.Path('/var/lib/ai-proje-ofisi-dbtest');S=R/'storage';B=R/'binary/usr/lib/postgresql/18/bin'
P=pathlib.Path('/mnt/e/Projeler/Ai_Proje_Ofisi');E=os.environ.copy();E['LD_LIBRARY_PATH']=str(R/'binary/usr/lib/x86_64-linux-gnu');E['PGCONNECT_TIMEOUT']='3'
assert os.geteuid()==999
raw=(P/'evidence/disposable_compile.sql').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='c796c3113807c6476dfda7aad6122a80455c5a3213c77d2438a43c647f1ff4eb'
assert raw.rstrip().endswith(b'ROLLBACK;')
def run(a,**kw):return subprocess.run([str(x) for x in a],env=E,capture_output=True,text=True,timeout=55,**kw)
def sql(text):return run([B/'psql','-X','-h',S/'socket','-U','aipof-dbtest','-d','postgres','-v','ON_ERROR_STOP=1','-A','-t','-f','-'],input=text)
r={'scope':'NEW_TREE_REAL_DDL_ROLLBACK_NOT_AUTHORIZATION_ACCEPTANCE','company_commit':False};started=False
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
 if o['backend_pid']!=observation['backend_pid'] or o['boottime_before_ns']>o['boottime_after_ns'] or o['source_sync_state'] not in ['SYNC','UNKNOWN']:raise RuntimeError('NATIVE_CLOCK_OBSERVATION_BINDING')
 negative=sql("BEGIN; CREATE FUNCTION public.disposable_wrong_symbol() RETURNS jsonb AS '$libdir/r55_clock_observer','invalid_disposable_symbol' LANGUAGE C; ROLLBACK;")
 r['wrong_symbol_rejected']=negative.returncode!=0 and 'invalid_disposable_symbol' in negative.stderr
 if not r['wrong_symbol_rejected']:raise RuntimeError('WRONG_NATIVE_SYMBOL_NOT_REJECTED')
 compile=sql(raw.decode());r['catalog_json']=[json.loads(l) for l in compile.stdout.splitlines() if l.startswith('{')];r['compile_exit']=compile.returncode;r['compile_stderr']=compile.stderr[-6000:];r['compile_stdout_tail']=compile.stdout[-3000:]
 match=re.search(r'<stdin>:(\d+):',compile.stderr)
 if match:
  line=int(match.group(1));lines=raw.decode().splitlines();r['execution_line']=line;r['nearest_source']=next((x for x in reversed(lines[:line]) if x.startswith('-- SOURCE ')),None)
 check=sql("SELECT json_build_object('company_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company'),'company_private_exists',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='company_private'),'smoke_rows',(SELECT count(*) FROM public.disposable_smoke_probe));")
 if check.returncode:raise RuntimeError('POST_ROLLBACK_READBACK_FAILED:'+check.stderr[-1000:])
 r['after_rollback']=json.loads(check.stdout.strip());r['compile_pass']=compile.returncode==0;r['rollback_verified']=not r['after_rollback']['company_exists'] and not r['after_rollback']['company_private_exists']
except Exception as e:r['error']=str(e)
finally:
 if started:r['stop_exit']=run([B/'pg_ctl','-D',S/'data','-m','fast','-w','-t','10','stop']).returncode
 r['db_stopped']=not (S/'data/postmaster.pid').exists()
 print(json.dumps(r),flush=True)
raise SystemExit(0 if r.get('compile_pass') and r.get('rollback_verified') and r['db_stopped'] else 1)
