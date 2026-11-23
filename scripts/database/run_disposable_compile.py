"""Scoped mount/build/private-install/load/rollback-compile/unmount lifecycle."""
import pathlib,subprocess,json,uuid,hashlib
P=pathlib.Path('/mnt/e/Projeler/Ai_Proje_Ofisi');OUT=P/'evidence'
TARGET='/var/lib/ai-proje-ofisi-dbtest/storage'
IMAGE='/var/lib/ai-proje-ofisi-dbtest/storage-1g.ext4'
record={'scope':'SCOPED_NATIVE_BUILD_AND_ROLLBACK_COMPILE_NOT_G0_ACCEPTANCE'}
def call(a,t=110):return subprocess.run(a,capture_output=True,text=True,timeout=t)
def unit(code,label,props):
 name=label+'-'+uuid.uuid4().hex[:8]
 r=call(['systemd-run','--wait','--collect','--pipe','--unit='+name]+['--property='+v for v in props]+['/usr/bin/python3','-c',code])
 parsed=None
 for line in r.stdout.splitlines():
  try:parsed=json.loads(line)
  except json.JSONDecodeError:pass
 return {'unit':name,'exit_code':r.returncode,'result':parsed,'stderr':r.stderr[-2500:],'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'properties':props}
props=['User=aipof-dbtest','Group=aipof-dbtest','MemoryMax=512M','MemorySwapMax=0','CPUQuota=50%','TasksMax=64','RuntimeMaxSec=90','TimeoutStopSec=15','LimitNOFILE=256','LimitCORE=0','NoNewPrivileges=yes','PrivateNetwork=yes','ProtectSystem=strict','ProtectHome=yes','ReadWritePaths='+TARGET,'OOMPolicy=stop','KillMode=control-group']
m=call(['systemd-mount','--collect','--no-ask-password','--type=ext4','--options=nosuid,nodev,noexec',IMAGE,TARGET],20)
if m.returncode:raise RuntimeError(m.stderr)
try:
 trial=unit((P/'scripts/database/disposable_compile_trial.py').read_text(),'aipof-newtree-sql',props);record['sql_trial']=trial
except Exception as e:record['error']=str(e)
finally:
 u=call(['systemd-mount','--umount',TARGET],20);record['unmount_exit']=u.returncode
 f=OUT/('NATIVE_CLOCK_TRIAL_'+uuid.uuid4().hex[:8]+'.json')
 with f.open('x') as stream:stream.write(json.dumps(record,indent=2))
 print('RECEIPT',str(f),flush=True);print(json.dumps(record),flush=True)

raise SystemExit(0 if record.get("sql_trial",{}).get("result",{}).get("compile_pass") is True and record.get("unmount_exit")==0 else 1)
