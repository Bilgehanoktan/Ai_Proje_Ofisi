"""Tek tikla yerel AI Proje Ofisi baslatici.

WSL PostgreSQL 18.6 + systemd + ucretsiz yerel Ollama (qwen2.5-coder:3b) +
AutonomousWorkerDaemon + Canli Ofis Web/SSE sunucusu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "product/backend"),
    str(ROOT / "contracts/source/python"),
    str(ROOT / "verifier/src"),
]

from company_os.api.http.app import make_wsgi_app  # noqa: E402
from company_os.budget.ledger import ExternalEffectEntry  # noqa: E402
from company_os.catalog.extensions_store import Extensions087Store  # noqa: E402
from company_os.catalog.live_lifecycle import LiveMemoryAndBudgetCoordinator  # noqa: E402
from company_os.catalog.memory_promotion import (  # noqa: E402
    CatalogEntry,
    CatalogKind,
    MemoryRecord,
    build_default_087_catalog_entries,
)
from company_os.engine.ollama_adapter import (  # noqa: E402
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    LOCAL_OLLAMA_MODEL_PROFILES,
    OllamaClient,
    ensure_local_ollama_running,
)
from company_os.projections.sse_stream import OfficeEventReplay, ProjectionEvent  # noqa: E402
from company_os.runtime.agent_instances import AgentInstanceRecord, AgentInstanceRegistry  # noqa: E402
from company_os.runtime.ceo_improvement import CeoContinuousImprovementEngine  # noqa: E402
from company_os.runtime.live_task_runner import (  # noqa: E402
    ENGINEER_PILOT_PROMPT,
    ENGINEER_PILOT_VERSION,
    LiveOfficeTaskRunner,
    OfficeTaskRecord,
)
from company_os.workflows.templates import TEMPLATES, WorkType  # noqa: E402

DEFAULT_KERNEL_PROFILE = ROOT / ".runtime/trials/live-flow-20261120/http_kernel_profile.json"
DEFAULT_TENANT_ID = "b7a6faa0-895f-4bdc-8cf7-e4b2c6501d73"
DEFAULT_PROJECT_ID = "37434287-b083-46ef-97fd-7577ee394509"
DEFAULT_AGENT_SPECS = (
    ("11111111-0001-4000-8000-000000000001", "EXP-01", "Engineer #1", "worker-eng-01"),
    ("11111111-0001-4000-8000-000000000002", "EXP-01", "Engineer #2", "worker-eng-02"),
    ("11111111-0002-4000-8000-000000000001", "EXP-02", "Research #1", "worker-res-01"),
    ("11111111-0003-4000-8000-000000000001", "MGR-01", "Orchestrator #1", "worker-mgr-01"),
    ("11111111-0004-4000-8000-000000000001", "QA-01", "QA #1", "worker-qa-01"),
    ("11111111-0005-4000-8000-000000000001", "EXP-03", "Security #1", "worker-sec-01"),
    ("11111111-0006-4000-8000-000000000001", "EXP-04", "Data #1", "worker-data-01"),
)

WSL_BOOT_PY = """
import json, subprocess
from pathlib import Path

pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'
data = '/var/lib/ai-proje-ofisi-local/data'
logf = '/var/lib/ai-proje-ofisi-local/postgres.log'

chk = subprocess.run(['/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'pg_isready'), '-h', sock, '-p', '55490'], env=env, capture_output=True)
if chk.returncode != 0:
    st = subprocess.run(['/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'pg_ctl'), '-D', data, '-l', logf, '-w', 'start'], env=env, capture_output=True, text=True)
    if st.returncode != 0:
        raise RuntimeError(st.stderr or st.stdout)

for unit in ('aipof-worker-daemon.service', 'aipof-pg-backup.timer'):
    act = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True)
    if act.stdout.strip() != 'active':
        subprocess.run(['systemctl', 'start', unit], capture_output=True, text=True)

w_state = subprocess.run(['systemctl', 'is-active', 'aipof-worker-daemon.service'], capture_output=True, text=True).stdout.strip()
t_state = subprocess.run(['systemctl', 'is-active', 'aipof-pg-backup.timer'], capture_output=True, text=True).stdout.strip()
print(json.dumps({'postgres_55490': 'ready', 'worker_daemon': w_state, 'backup_timer': t_state}))
"""

WSL_SNAPSHOT_PY = """
import json, subprocess, sys
from pathlib import Path

pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'

query = '''
SELECT set_config('app.tenant_id', :'tenant_id', false);
SELECT json_build_object(
  'counts', json_build_object(
    'objectives', (SELECT count(*) FROM company.objectives),
    'plans', (SELECT count(*) FROM company.plans),
    'tasks', (SELECT count(*) FROM company.tasks),
    'accepted_tasks', (SELECT count(*) FROM company.tasks WHERE state='ACCEPTED'),
    'acceptance_records', (SELECT count(*) FROM company.acceptance_records),
    'catalog_entries', (SELECT count(*) FROM company.catalog_entries),
    'memory_promotions', (SELECT count(*) FROM company.memory_promotions),
    'work_template_validations', (SELECT count(*) FROM company.work_template_validations),
    'external_effect_ledger', (SELECT count(*) FROM company.external_effect_ledger)
  ),
  'tasks', COALESCE((
    SELECT json_agg(t) FROM (
      SELECT id::text, title, state, revision
      FROM company.tasks ORDER BY id DESC LIMIT 10
    ) t
  ), '[]'::json),
  'approvals', COALESCE((
    SELECT json_agg(a) FROM (
      SELECT id::text, accepted_by::text, created_at::text
      FROM company.acceptance_records ORDER BY created_at DESC LIMIT 8
    ) a
  ), '[]'::json),
  'outbox', COALESCE((
    SELECT json_agg(o) FROM (
      SELECT event_id, kind, occurred_at::text AS created_at
      FROM company.outbox
      WHERE tenant_id = :'tenant_id'::uuid AND project_id = :'project_id'::uuid
      ORDER BY event_id DESC LIMIT 12
    ) o
  ), '[]'::json),
  'agent_instances', COALESCE((
    SELECT json_agg(ai) FROM (
      SELECT agent_instance_id::text, tenant_id::text, project_id::text, role_id,
             display_name, worker_principal, state, active_task_id,
             active_attempt_id::text, active_task_title, revision, last_seen_at::text,
             NULL::numeric AS lease_remaining_ms
      FROM company.agent_instances AS agent
      WHERE tenant_id = :'tenant_id'::uuid AND project_id = :'project_id'::uuid
      ORDER BY role_id, display_name, agent_instance_id
    ) ai
  ), '[]'::json)
);
'''

lease_remaining = '''
  (SELECT floor(1000 * extract(epoch FROM (a.lease_expires_at -
          (company_private.r55_cp_clock_current_bounds(a.tenant_id, a.project_id)
              ->> 'utc_upper_bound')::timestamptz)))
   FROM company.attempts a
   JOIN company.tasks t ON (t.tenant_id, t.project_id, t.id, t.active_attempt_id, t.fencing_epoch)
                         = (a.tenant_id, a.project_id, a.task_id, a.id, a.fencing_epoch)
   WHERE agent.state = 'RUNNING' AND t.state = 'RUNNING'
     AND (agent.tenant_id, agent.project_id, agent.active_attempt_id)
       = (a.tenant_id, a.project_id, a.id)
     AND agent.active_task_id = a.task_id::text
     AND agent.worker_principal = a.worker_id::text
     AND a.state IN ('CLAIMED', 'RUNNING') AND a.ended_at IS NULL)
'''
psql = ['/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'psql'),
     '-X', '-h', sock, '-p', '55490', '-d', 'ai_proje_ofisi', '-Atq',
     '-v', 'ON_ERROR_STOP=1', '-v', f'tenant_id={sys.argv[1]}',
     '-v', f'project_id={sys.argv[2]}', '-f', '-']
def read_snapshot(sql):
    return subprocess.run(psql, input=sql, text=True, capture_output=True, env=env, timeout=15)

res = read_snapshot(query.replace('NULL::numeric AS lease_remaining_ms',
                                  lease_remaining + ' AS lease_remaining_ms'))
if res.returncode != 0:
    # Keep the office readable when the trusted clock or its read permission is unavailable.
    res = read_snapshot(query)
if res.returncode != 0:
    raise RuntimeError(res.stderr.strip())
w_state = subprocess.run(['systemctl', 'is-active', 'aipof-worker-daemon.service'], capture_output=True, text=True).stdout.strip()
t_state = subprocess.run(['systemctl', 'is-active', 'aipof-pg-backup.timer'], capture_output=True, text=True).stdout.strip()
raw_out = res.stdout.strip()
start_idx = raw_out.find('{"counts"')
data, _ = json.JSONDecoder().raw_decode(raw_out[start_idx if start_idx >= 0 else 0:])
data['services'] = {'postgres_55490': 'ready', 'worker_daemon': w_state, 'backup_timer': t_state}
print(json.dumps(data))
"""

WSL_KERNEL_SUBMIT_PY = """
import json, os, sys
from pathlib import Path
from uuid import uuid4

payload = json.loads(sys.stdin.read())
token = payload['bearer_token']
profile_path = payload['profile_path']
profile_sha = payload['profile_sha256']
task_spec = payload['task']

root = Path('/mnt/e/Projeler/Ai_Proje_Ofisi')
sys.path[:0] = [str(root / 'product/backend'), str(root / 'contracts/source/python')]
os.environ.setdefault('PGSERVICEFILE', '/var/lib/ai-proje-ofisi-local/live-flow-20261120/pg_service.conf')

from company_os.api.http.kernel_binding import load_binding, make_connector
from company_os.api.http.task_http import create_project_backend

profile = load_binding(profile_path, expected_sha256=profile_sha)
connect = make_connector(profile)
backend = create_project_backend(
    connect=connect,
    project_id=profile['project_id'],
    grant_ids=profile['grant_ids'],
    emission_timeout=profile['emission_timeout'],
)

# Read current project revision cleanly before creating plan
with connect() as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT revision FROM company.projects WHERE id = %s::uuid', (profile['project_id'],))
        row = cur.fetchone()
        if not row:
            raise RuntimeError('PROJECT_NOT_FOUND')
        expected_rev = int(row[0])

obj_req_id = str(uuid4())
_, obj_env = backend.prepare(
    token,
    '/api/objectives',
    {
        'request_id': obj_req_id,
        'goal': task_spec['goal'],
        'constraints': [f"work_type={task_spec['work_type']}"],
        'expected_outputs': [f"role={task_spec['role_id']} verified output"],
    },
)
obj_id = obj_env['command_receipt']['result_ref']

plan_req_id = str(uuid4())
_, plan_env = backend.prepare(
    token,
    '/api/plans',
    {
        'request_id': plan_req_id,
        'objective_id': obj_id,
        'expected_revision': expected_rev,
        'assumptions': ['local_ollama_free_default'],
        'acceptance_criteria': task_spec['acceptance_criteria'],
    },
)
plan_id = plan_env['command_receipt']['result_ref']

task_req_id = str(uuid4())
_, task_env = backend.prepare(
    token,
    '/api/tasks',
    {
        'request_id': task_req_id,
        'plan_id': plan_id,
        'title': task_spec['title'],
        'role_id': task_spec['role_id'],
        'acceptance_criteria': task_spec['acceptance_criteria'],
        'depends_on': [],
    },
)
task_id = task_env['command_receipt']['result_ref']

print(json.dumps({
    'persisted': True,
    'mode': 'KERNEL_AUTHENTICATED_POSTGRES',
    'objective_id': obj_id,
    'plan_id': plan_id,
    'task_id': task_id,
    'command_id': task_env['command_receipt']['command_id'],
}))
"""

WSL_PERSIST_VALIDATION_PY = """
import json, subprocess, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'

sql = (
    "BEGIN; "
    "SELECT set_config('app.tenant_id', :'tid', true); "
    "INSERT INTO company.work_template_validations "
    "(tenant_id, work_type, template_id, template_version, validated, evidence_digest) "
    "VALUES (:'tid'::uuid, :'wt', :'tpl_id', :'tpl_ver', :'val'::boolean, :'dig'); "
    "COMMIT;"
)

res = subprocess.run(
    [
        '/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'psql'),
        '-X', '-h', sock, '-p', '55490', '-d', 'ai_proje_ofisi', '-Atq', '-v', 'ON_ERROR_STOP=1',
        '-v', f"tid={payload['tenant_id']}",
        '-v', f"wt={payload['work_type']}",
        '-v', f"tpl_id={payload['template_id']}",
        '-v', f"tpl_ver={payload['template_version']}",
        '-v', f"val={'true' if payload['validated'] else 'false'}",
        '-v', f"dig={payload['evidence_digest']}",
        '-f', '-',
    ],
    input=sql, text=True, capture_output=True, env=env, timeout=15
)
if res.returncode != 0:
    raise RuntimeError(res.stderr.strip())
print(json.dumps({'saved': True}))
"""

WSL_UPSERT_MEMORY_PROMOTION_PY = """
import json, subprocess, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'

sql = (
    "BEGIN; "
    "SELECT set_config('app.tenant_id', :'tid', true); "
    "INSERT INTO company.memory_promotions "
    "(tenant_id, record_id, summary, evidence_digest, state, verified_by, promoted_by) "
    "VALUES (:'tid'::uuid, :'rid', :'summary', :'dig', :'st', NULLIF(:'vby', ''), NULLIF(:'pby', '')) "
    "ON CONFLICT (tenant_id, record_id) DO UPDATE SET "
    "state = EXCLUDED.state, verified_by = EXCLUDED.verified_by, promoted_by = EXCLUDED.promoted_by; "
    "COMMIT;"
)

res = subprocess.run(
    [
        '/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'psql'),
        '-X', '-h', sock, '-p', '55490', '-d', 'ai_proje_ofisi', '-Atq', '-v', 'ON_ERROR_STOP=1',
        '-v', f"tid={payload['tenant_id']}",
        '-v', f"rid={payload['record_id']}",
        '-v', f"summary={payload['summary']}",
        '-v', f"dig={payload['evidence_digest']}",
        '-v', f"st={payload['state']}",
        '-v', f"vby={payload.get('verified_by') or ''}",
        '-v', f"pby={payload.get('promoted_by') or ''}",
        '-f', '-',
    ],
    input=sql, text=True, capture_output=True, env=env, timeout=15
)
if res.returncode != 0:
    raise RuntimeError(res.stderr.strip())
print(json.dumps({'saved': True}))
"""

WSL_UPSERT_EXTERNAL_EFFECT_PY = """
import json, subprocess, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'

sql = (
    "BEGIN; "
    "SELECT set_config('app.tenant_id', :'tid', true); "
    "INSERT INTO company.external_effect_ledger "
    "(tenant_id, idempotency_key, effect_id, provider, status) "
    "VALUES (:'tid'::uuid, :'ikey', :'eid', :'prov', :'st') "
    "ON CONFLICT (tenant_id, idempotency_key) DO UPDATE SET status = EXCLUDED.status; "
    "COMMIT;"
)

res = subprocess.run(
    [
        '/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'psql'),
        '-X', '-h', sock, '-p', '55490', '-d', 'ai_proje_ofisi', '-Atq', '-v', 'ON_ERROR_STOP=1',
        '-v', f"tid={payload['tenant_id']}",
        '-v', f"ikey={payload['idempotency_key']}",
        '-v', f"eid={payload['effect_id']}",
        '-v', f"prov={payload['provider']}",
        '-v', f"st={payload['status']}",
        '-f', '-',
    ],
    input=sql, text=True, capture_output=True, env=env, timeout=15
)
if res.returncode != 0:
    raise RuntimeError(res.stderr.strip())
print(json.dumps({'saved': True}))
"""

WSL_UPSERT_AGENT_INSTANCE_PY = """
import json, subprocess, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'

sql = (
    "BEGIN; "
    "SELECT set_config('app.tenant_id', :'tid', true); "
    "INSERT INTO company.agent_instances "
    "(agent_instance_id, tenant_id, project_id, role_id, display_name, worker_principal, "
    " state, active_task_id, active_attempt_id, active_task_title, revision, last_seen_at) "
    "VALUES (:'aid'::uuid, :'tid'::uuid, :'pid'::uuid, :'rid', :'dname', :'wprin', "
    " :'st', NULLIF(:'task_id', ''), NULLIF(:'att_id', '')::uuid, NULLIF(:'task_title', ''), "
    " :'rev'::bigint, clock_timestamp()) "
    "ON CONFLICT (agent_instance_id) DO UPDATE SET "
    "state = EXCLUDED.state, active_task_id = EXCLUDED.active_task_id, "
    "active_attempt_id = EXCLUDED.active_attempt_id, active_task_title = EXCLUDED.active_task_title, "
    "revision = EXCLUDED.revision, last_seen_at = clock_timestamp(); "
    "COMMIT;"
)

res = subprocess.run(
    [
        '/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'psql'),
        '-X', '-h', sock, '-p', '55490', '-d', 'ai_proje_ofisi', '-Atq', '-v', 'ON_ERROR_STOP=1',
        '-v', f"aid={payload['agent_instance_id']}",
        '-v', f"tid={payload['tenant_id']}",
        '-v', f"pid={payload['project_id']}",
        '-v', f"rid={payload['role_id']}",
        '-v', f"dname={payload['display_name']}",
        '-v', f"wprin={payload['worker_principal']}",
        '-v', f"st={payload['state']}",
        '-v', f"task_id={payload.get('active_task_id') or ''}",
        '-v', f"att_id={payload.get('active_attempt_id') or ''}",
        '-v', f"task_title={payload.get('active_task_title') or ''}",
        '-v', f"rev={int(payload.get('revision') or 0)}",
        '-f', '-',
    ],
    input=sql, text=True, capture_output=True, env=env, timeout=15
)
if res.returncode != 0:
    raise RuntimeError(res.stderr.strip())
print(json.dumps({'saved': True}))
"""

WSL_CATALOG_087_PY = """
import json, os, sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
root = Path('/mnt/e/Projeler/Ai_Proje_Ofisi')
sys.path[:0] = [str(root / 'product/backend'), str(root / 'contracts/source/python')]
os.environ.setdefault('PGSERVICEFILE', '/var/lib/ai-proje-ofisi-local/live-flow-20261120/pg_service.conf')

import psycopg
from company_os.catalog.extensions_store import Extensions087Store
from company_os.catalog.memory_promotion import CatalogEntry, CatalogKind

service_name = payload.get('service') or ''
if service_name:
    connect = lambda: psycopg.connect(service=service_name, connect_timeout=5)
else:
    connect = lambda: psycopg.connect(
        host='/var/lib/ai-proje-ofisi-local/socket',
        port=55490,
        dbname='ai_proje_ofisi',
        user='aipof-dbtest',
        connect_timeout=5,
    )

store = Extensions087Store(connect=connect)
op = payload.get('op')
if op == 'upsert':
    entry = CatalogEntry(
        tenant_id=payload['tenant_id'],
        kind=CatalogKind(payload['kind']),
        name=payload['name'],
        version=payload['version'],
        digest=payload['digest'],
        active=bool(payload.get('active', True)),
    )
    print(json.dumps(store.upsert_catalog_entry(entry)))
elif op == 'list':
    print(json.dumps({'items': store.list_catalog_entries(payload['tenant_id'])}))
else:
    raise ValueError(f'UNSUPPORTED_CATALOG_OP:{op}')
"""


def _kernel_research_readback(distro, service, scope, receipt_id=None):
    """Run the independent verifier in a fresh WSL process with its own DB login."""
    script = """
import json, os, sys
from pathlib import Path
import psycopg
payload = json.load(sys.stdin)
sys.path.insert(0, str(Path('/mnt/e/Projeler/Ai_Proje_Ofisi/verifier/src')))
from independent_verifier.research_readback import confirm_receipt, current_read
os.environ.setdefault('PGSERVICEFILE', '/var/lib/ai-proje-ofisi-local/live-flow-20261120/pg_service.conf')
def connect():
    return psycopg.connect(service=payload['service'], connect_timeout=4)
if payload['receipt_id'] is None:
    print(json.dumps(current_read(connect, payload['scope'])))
else:
    print(json.dumps(confirm_receipt(connect, payload['scope'], payload['receipt_id'], require_current=True)))
"""
    payload = {'scope': scope, 'receipt_id': receipt_id, 'service': service}
    result = subprocess.run(
        ['wsl', '-d', distro, '--exec', '/usr/sbin/runuser', '-u', 'aipof-dbtest',
         '--', 'python3', '-c', script],
        input=json.dumps(payload), text=True, capture_output=True, timeout=12,
    )
    if result.returncode:
        raise RuntimeError('KERNEL_RESEARCH_READBACK_UNAVAILABLE')
    return json.loads(result.stdout)


class WslCatalog087Adapter:
    """Bridges Windows office process to WSL PostgreSQL 18.6 Extensions087Store."""

    def __init__(self, distro: str = "Ubuntu-E", service: str | None = None) -> None:
        self.distro = distro
        self.service = service

    def _call(self, payload: dict) -> dict:
        wire = json.dumps({**payload, "service": self.service}, ensure_ascii=False)
        res = subprocess.run(
            [
                "wsl",
                "-d",
                self.distro,
                "--",
                "setpriv",
                "--reuid=aipof-dbtest",
                "--regid=aipof-dbtest",
                "--init-groups",
                "python3",
                "-c",
                WSL_CATALOG_087_PY,
            ],
            input=wire,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout).strip())
        lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("{")]
        if not lines:
            raise RuntimeError("EMPTY_WSL_CATALOG_087_RESPONSE")
        return json.loads(lines[-1])

    def upsert_catalog_entry(self, entry: CatalogEntry) -> dict:
        return self._call(
            {
                "op": "upsert",
                "tenant_id": entry.tenant_id,
                "kind": entry.kind.value,
                "name": entry.name,
                "version": entry.version,
                "digest": entry.digest,
                "active": entry.active,
            }
        )

    def list_catalog_entries(self, tenant_id: str) -> list[dict]:
        return list(self._call({"op": "list", "tenant_id": tenant_id}).get("items") or [])

    def seed_default_catalog_profiles(self, tenant_id: str) -> list[dict]:
        entries = build_default_087_catalog_entries(
            tenant_id, model_profiles=LOCAL_OLLAMA_MODEL_PROFILES
        )
        return [self.upsert_catalog_entry(entry) for entry in entries]


def parse_allowed_https_domains(raw: str | None) -> frozenset[str]:
    """Parse and validate comma-separated external HTTPS domain allowlist."""
    if not raw or not str(raw).strip():
        return frozenset()
    domains: set[str] = set()
    for part in str(raw).split(","):
        item = part.strip().lower()
        if not item:
            continue
        if (
            "://" in item
            or "/" in item
            or ":" in item
            or "*" in item
            or item.startswith(".")
            or item.endswith(".")
            or ".." in item
            or "." not in item
        ):
            raise ValueError(f"INVALID_ALLOWED_HTTPS_DOMAIN:{part.strip()}")
        domains.add(item)
    return frozenset(domains)


def build_remote_production_preflight(
    ssh_host_alias: str,
    allowed_https_domains: frozenset[str],
) -> dict[str, object]:
    """Validate approved remote SSH host alias and HTTPS allowlist and emit PRODUCTION_RUNBOOK.md step plan."""
    alias = str(ssh_host_alias or "").strip()
    if not alias or any(ch.isspace() for ch in alias) or alias.startswith("-"):
        raise ValueError("INVALID_SSH_HOST_ALIAS")
    domain_csv = ",".join(sorted(allowed_https_domains))
    return {
        "ssh_host_alias": alias,
        "allowed_https_domains": sorted(allowed_https_domains),
        "runbook": "docs/operations/PRODUCTION_RUNBOOK.md",
        "steps": [
            {
                "step": 1,
                "title": "001..088 PostgreSQL 18.6 kurulum ve yükseltme doğrulaması",
                "remote_command": f"ssh {alias} 'cd /opt/aipof && PYTHONPATH=. python3 -B scripts/verification/verify_087_migration_pg.py'",
            },
            {
                "step": 2,
                "title": "r65_spawn_linux.c derlemesi ve delegated cgroup v2 MGT-01 (13/13) doğrulaması",
                "remote_command": (
                    f"ssh {alias} 'cd /opt/aipof && gcc -Wall -Wextra -Werror -O2 -shared -fPIC "
                    "-o /opt/aipof/lib/r65_spawn_linux.so product/backend/native/linux/r65_spawn_linux.c "
                    "&& AIPOF_CGROUP_PATH=/sys/fs/cgroup/aipof_eval/worker python3 -B scripts/verification/verify_mgt01_native_launcher.py'"
                ),
            },
            {
                "step": 3,
                "title": "087 rol/beceri kartları ve yerel Ollama model profillerinin tohumlanması",
                "remote_command": (
                    f"ssh {alias} 'cd /opt/aipof && python3 -B scripts/operations/start_office_local.py "
                    f"--skip-wsl --check-only --allowed-https-domains=\"{domain_csv}\"'"
                ),
            },
            {
                "step": 4,
                "title": "Systemd worker daemon ve zamanlanmış pg_basebackup/pg_verifybackup timer etkinleştirme",
                "remote_command": (
                    f"ssh {alias} 'sudo systemctl enable --now aipof-worker-daemon.service aipof-pg-backup.timer "
                    "&& systemctl is-active aipof-worker-daemon.service aipof-pg-backup.timer'"
                ),
            },
        ],
    }



def ensure_wsl_services(distro: str = "Ubuntu-E") -> dict[str, str]:
    """WSL2 uzerindeki PostgreSQL 18.6 ve systemd servislerinin acik oldugunu dogrular."""
    if sys.platform != "win32":
        return {"postgres_55490": "skipped_non_windows", "worker_daemon": "n/a", "backup_timer": "n/a"}
    res = subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_BOOT_PY],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if res.returncode != 0:
        raise RuntimeError(f"WSL servisleri baslatilamadi: {(res.stderr or res.stdout).strip()}")
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"Beklenmeyen WSL ciktisi: {res.stdout.strip()}")
    return json.loads(lines[-1])


def fetch_live_office_snapshot(distro: str = "Ubuntu-E") -> dict:
    """Canli PostgreSQL 18.6 (55490) ve systemd servis durumlarini okur."""
    if sys.platform != "win32":
        return {"mode": "DEMO_SYNTHETIC", "connected": False}
    try:
        res = subprocess.run(
            [
                "wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_SNAPSHOT_PY,
                DEFAULT_TENANT_ID, DEFAULT_PROJECT_ID,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode != 0:
            return {"mode": "DEMO_SYNTHETIC", "connected": False, "error": (res.stderr or res.stdout).strip()[:200]}
        lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("{")]
        data = json.loads(lines[-1])
        data.update(
            {
                "mode": "LIVE_POSTGRES_18_6",
                "connected": True,
                "cluster": "PostgreSQL 18.6 (port 55490 · ai_proje_ofisi)",
                "g0": "APPROVED_BY_HUMAN_20261123",
                "first13": "13/13",
                "updated_at": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
            }
        )
        return data
    except Exception as exc:  # noqa: BLE001
        return {"mode": "DEMO_SYNTHETIC", "connected": False, "error": str(exc)[:200]}


def _persist_submission_via_wsl_kernel(
    distro: str,
    task_spec: dict,
    bearer_token: str | None,
    *,
    require_session_token: bool,
) -> dict:
    """Persist Objective->Plan->Task via canonical Kernel when a Bearer session token is supplied."""
    if not bearer_token:
        if require_session_token:
            raise PermissionError("OWNER_SESSION_TOKEN_REQUIRED")
        return {
            "persisted": False,
            "mode": "LOCAL_WORKER_WITHOUT_KERNEL_SESSION",
            "note": "Oturum anahtari girilmedi; gorev yerel AutonomousWorkerDaemon + Ollama ile calistirildi.",
        }
    if sys.platform != "win32" or not DEFAULT_KERNEL_PROFILE.is_file():
        raise PermissionError("KERNEL_BINDING_PROFILE_UNAVAILABLE")

    profile_sha = hashlib.sha256(DEFAULT_KERNEL_PROFILE.read_bytes()).hexdigest()
    wsl_profile_path = "/mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/trials/live-flow-20261120/http_kernel_profile.json"
    wire = json.dumps(
        {
            "bearer_token": bearer_token,
            "profile_path": wsl_profile_path,
            "profile_sha256": profile_sha,
            "task": task_spec,
        },
        ensure_ascii=False,
    )
    res = subprocess.run(
        ["wsl", "-d", distro, "-u", "aipof-dbtest", "--", "python3", "-c", WSL_KERNEL_SUBMIT_PY],
        input=wire,
        capture_output=True,
        text=True,
        timeout=25,
    )
    if res.returncode != 0:
        raise PermissionError("KERNEL_SESSION_OR_AUTHORITY_REJECTED")
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise PermissionError("KERNEL_RESPONSE_INVALID")
    return json.loads(lines[-1])


def _persist_validation_to_wsl_pg087(distro: str, record: OfficeTaskRecord) -> None:
    """Persist RESEARCH/SPREADSHEET/OBLIGATION verification outcome into 087 table."""
    if sys.platform != "win32":
        return
    if record.work_type not in ("RESEARCH", "SPREADSHEET", "OBLIGATION"):
        return
    if not record.verification or not record.exec_result:
        return
    spec = TEMPLATES.get(WorkType(record.work_type))
    if spec is None:
        return
    wire = json.dumps(
        {
            "tenant_id": DEFAULT_TENANT_ID,
            "work_type": record.work_type,
            "template_id": spec.template_id,
            "template_version": spec.version,
            "validated": bool(record.verification.get("accepted")),
            "evidence_digest": f"sha256:{record.exec_result.get('response_sha256', '')}",
        }
    )
    subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_PERSIST_VALIDATION_PY],
        input=wire,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _persist_memory_promotion_to_wsl_pg087(distro: str, rec: MemoryRecord) -> None:
    """Persist product memory promotion record into 087 company.memory_promotions."""
    if sys.platform != "win32":
        return
    wire = json.dumps(
        {
            "tenant_id": rec.tenant_id,
            "record_id": rec.record_id,
            "summary": rec.summary,
            "evidence_digest": rec.evidence_digest,
            "state": rec.state.value,
            "verified_by": rec.verified_by,
            "promoted_by": rec.promoted_by,
        },
        ensure_ascii=False,
    )
    subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_UPSERT_MEMORY_PROMOTION_PY],
        input=wire,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _persist_agent_instance_to_wsl_pg088(
    distro: str, rec: AgentInstanceRecord, _transition: str | None = None
) -> None:
    """Persist canonical AgentInstance state into 088 company.agent_instances."""
    if sys.platform != "win32":
        return
    wire = json.dumps(rec.to_dict(), ensure_ascii=False)
    subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_UPSERT_AGENT_INSTANCE_PY],
        input=wire,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _persist_external_effect_to_wsl_pg087(distro: str, entry: ExternalEffectEntry) -> None:
    """Persist external effect ledger entry into 087 company.external_effect_ledger."""
    if sys.platform != "win32":
        return
    wire = json.dumps(
        {
            "tenant_id": entry.tenant_id,
            "idempotency_key": entry.idempotency_key,
            "effect_id": entry.effect_id,
            "provider": entry.provider,
            "status": entry.status,
        },
        ensure_ascii=False,
    )
    subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_UPSERT_EXTERNAL_EFFECT_PY],
        input=wire,
        capture_output=True,
        text=True,
        timeout=15,
    )


def dispatch_memory_action(coordinator: LiveMemoryAndBudgetCoordinator, payload: dict) -> dict:
    """Route POST /api/memory-promotions actions to LiveMemoryAndBudgetCoordinator."""
    action = str(payload.get("action") or "").strip().lower()
    record_id = str(payload.get("record_id") or "").strip()
    if action == "promote":
        return coordinator.promote_memory(
            record_id=record_id, approver_id=str(payload.get("actor_id") or "OWNER_HUMAN")
        )
    if action == "verify":
        return coordinator.verify_candidate(
            record_id=record_id, verifier_id=str(payload.get("actor_id") or "")
        )
    if action == "reject":
        return coordinator.reject_memory(
            record_id=record_id, reviewer_id=str(payload.get("actor_id") or "OWNER_HUMAN")
        )
    raise ValueError("UNSUPPORTED_MEMORY_ACTION")


def dispatch_external_effect_action(
    coordinator: LiveMemoryAndBudgetCoordinator, payload: dict
) -> dict:
    """Route POST /api/external-effects actions to LiveMemoryAndBudgetCoordinator."""
    action = str(payload.get("action") or "dispatch").strip().lower()
    if action == "dispatch":
        return coordinator.execute_external_effect(
            idempotency_key=str(payload.get("idempotency_key") or ""),
            provider=str(payload.get("provider") or ""),
            target_url=str(payload.get("target_url") or ""),
            payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            reserved_minor=int(payload.get("reserved_minor") or 0),
            actual_minor=(
                None if payload.get("actual_minor") is None else int(payload["actual_minor"])
            ),
        )
    if action == "reconcile":
        return coordinator.reconcile_unknown_effect(
            idempotency_key=str(payload.get("idempotency_key") or ""),
            actual_minor=int(payload.get("actual_minor") or 0),
            final_status=str(payload.get("final_status") or "COMMITTED"),
        )
    raise ValueError("UNSUPPORTED_EXTERNAL_EFFECT_ACTION")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Proje Ofisi tek tikla baslatici.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--wsl-distro", default="Ubuntu-E")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--skip-wsl", action="store_true", help="WSL PG/systemd kontrolunu atla")
    parser.add_argument("--skip-ollama", action="store_true", help="Yerel Ollama otomatik baslatmayi atla")
    parser.add_argument(
        "--require-session-token",
        action="store_true",
        help="Gorev gonderiminde aktif Kernel OWNER session Bearer token zorunlu kil",
    )
    parser.add_argument("--no-browser", action="store_true", help="Tarayiciyi otomatik acma")
    parser.add_argument("--check-only", action="store_true", help="Servisleri kontrol et ve cik")
    parser.add_argument(
        "--research-readback-service",
        default="aipof_research_readback",
        help="Kernel makbuzlarını okuyabilen doğrulayıcı PG servis adı",
    )
    parser.add_argument(
        "--engineer-pilot-service",
        default="aipof_catalog_087",
        help="EXP-01 pilotu icin 087 katalog yetkisi olan PostgreSQL service adi",
    )
    parser.add_argument(
        "--allowed-https-domains",
        default="",
        help="Virgulle ayrilmis onayli harici HTTPS domain listesi (orn: docs.example.org,reg.example.gov.tr)",
    )
    parser.add_argument(
        "--remote-ssh-host",
        default="",
        help="Uzak uretim Linux sunucusu SSH host takma adi (preflight runbook dogrulamasi icin)",
    )
    args = parser.parse_args()
    allowed_https_domains = parse_allowed_https_domains(args.allowed_https_domains)

    if args.remote_ssh_host:
        preflight = build_remote_production_preflight(args.remote_ssh_host, allowed_https_domains)
        print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
        if args.check_only:
            return 0

    print("=== AI Proje Ofisi Baslatiliyor ===", flush=True)
    if not args.skip_wsl:
        print("[1/4] WSL2 PostgreSQL 18.6 ve systemd servisleri kontrol ediliyor...", flush=True)
        try:
            status = ensure_wsl_services(args.wsl_distro)
            print(
                f"      PostgreSQL (55490): {status['postgres_55490']} | "
                f"Worker: {status['worker_daemon']} | Yedek Timer: {status['backup_timer']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"      UYARI: {exc}", flush=True)
            print("      Web arayuzu sinirli yerel modda acilmaya devam edecek.", flush=True)

    ollama_client = OllamaClient(base_url=args.ollama_url, default_model=args.ollama_model)
    if not args.skip_ollama:
        print(f"[2/4] Yerel ucretsiz Ollama ({args.ollama_model}) kontrol ediliyor...", flush=True)
        ollama_status = ensure_local_ollama_running(
            base_url=args.ollama_url, default_model=args.ollama_model
        )
        if ollama_status.get("available"):
            started_note = " (otomatik baslatildi)" if ollama_status.get("started_by_launcher") else ""
            print(
                f"      Ollama: HAZIR{started_note} | Modeller: {', '.join(ollama_status.get('models') or [])}",
                flush=True,
            )
        else:
            print(
                f"      UYARI: Yerel Ollama erisilemedi ({ollama_status.get('error', 'UNREACHABLE')}).",
                flush=True,
            )

    if args.check_only:
        print("[OK] Kontrol tamamlandi (--check-only).", flush=True)
        return 0

    engineer_pilot_catalog = None
    if args.engineer_pilot_service:
        if sys.platform == "win32" and not args.skip_wsl:
            try:
                svc = None if args.engineer_pilot_service == "wsl-local" else args.engineer_pilot_service
                engineer_pilot_catalog = WslCatalog087Adapter(distro=args.wsl_distro, service=svc)
                seeded = engineer_pilot_catalog.seed_default_catalog_profiles(DEFAULT_TENANT_ID)
                entry = next(
                    (
                        item
                        for item in seeded
                        if item.get("kind") == "ROLE" and item.get("name") == "EXP-01"
                    ),
                    {},
                )
                if not entry.get("active"):
                    raise ValueError("ENGINEER_PILOT_CATALOG_ENTRY_INACTIVE")
            except RuntimeError as exc:
                if "InsufficientPrivilege" in str(exc):
                    print(
                        f"[UYARI] EXP-01 pilot katalog servisi yetki hatasi (InsufficientPrivilege): {exc}. "
                        "Katalog pini devre disi birakilarak devam ediliyor.",
                        file=sys.stderr,
                    )
                    engineer_pilot_catalog = None
                else:
                    print(f"[HATA] EXP-01 pilot katalog kaydi hazirlanamadi: {exc}", file=sys.stderr)
                    return 1
            except ValueError:
                print("[HATA] EXP-01 pilot katalog kaydi hazirlanamadi.", file=sys.stderr)
                return 1
        else:
            try:
                import psycopg
            except ImportError:
                print("[HATA] EXP-01 pilotu icin psycopg gerekli.", file=sys.stderr)
                return 1
            try:
                engineer_pilot_catalog = Extensions087Store(
                    lambda: psycopg.connect(service=args.engineer_pilot_service, connect_timeout=5)
                )
                seeded = engineer_pilot_catalog.seed_default_catalog_profiles(DEFAULT_TENANT_ID)
                entry = next(
                    (
                        item
                        for item in seeded
                        if item.get("kind") == "ROLE" and item.get("name") == "EXP-01"
                    ),
                    {},
                )
                if not entry.get("active"):
                    raise ValueError("ENGINEER_PILOT_CATALOG_ENTRY_INACTIVE")
            except psycopg.errors.InsufficientPrivilege as exc:
                print(
                    f"[UYARI] EXP-01 pilot katalog servisi yetki hatasi (InsufficientPrivilege): {exc}. "
                    "Katalog pini devre disi birakilarak devam ediliyor.",
                    file=sys.stderr,
                )
                engineer_pilot_catalog = None
            except (psycopg.Error, ValueError, RuntimeError):
                print("[HATA] EXP-01 pilot katalog kaydi hazirlanamadi.", file=sys.stderr)
                return 1

    allowed_webhook_hosts = frozenset({"127.0.0.1", "localhost"} | set(allowed_https_domains))
    coordinator = LiveMemoryAndBudgetCoordinator(
        tenant_id=DEFAULT_TENANT_ID,
        budget_limit_minor=1000,
        allowed_hosts=allowed_webhook_hosts,
        persist_promotion=(
            None
            if args.skip_wsl
            else (lambda rec: _persist_memory_promotion_to_wsl_pg087(args.wsl_distro, rec))
        ),
        persist_effect=(
            None
            if args.skip_wsl
            else (lambda entry: _persist_external_effect_to_wsl_pg087(args.wsl_distro, entry))
        ),
    )

    agent_registry = AgentInstanceRegistry(
        persist_agent=(
            None
            if args.skip_wsl
            else (lambda rec, tr: _persist_agent_instance_to_wsl_pg088(args.wsl_distro, rec, tr))
        )
    )
    for aid, rid, dname, wprin in DEFAULT_AGENT_SPECS:
        agent_registry.register_agent(
            agent_instance_id=aid,
            tenant_id=DEFAULT_TENANT_ID,
            project_id=DEFAULT_PROJECT_ID,
            role_id=rid,
            display_name=dname,
            worker_principal=wprin,
        )

    def _research_broker_reader(read_path: str) -> dict[str, object]:
        normalized_rel = read_path.replace("\\", "/").lstrip("/")
        target = (ROOT / normalized_rel).resolve()
        if ROOT.resolve() not in target.parents or not target.is_file():
            raise ValueError(f"RESEARCH_PATH_OUT_OF_SCOPE:{read_path}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        receipt_id = str(uuid4())
        return {
            "relative_path": normalized_rel,
            "sha256": digest,
            "receipt_id": receipt_id,
        }

    def _read_xlsx_summary(raw_bytes: bytes) -> dict[str, object]:
        import io
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root_ss.iter():
                    if si.tag.endswith("}t") or si.tag == "t":
                        shared.append(si.text or "")
            sheet_name = next(
                (n for n in sorted(zf.namelist()) if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
                None,
            )
            if sheet_name is None:
                raise ValueError("SPREADSHEET_XLSX_MISSING_WORKSHEET")
            root_sh = ET.fromstring(zf.read(sheet_name))
            cells: list[str] = []
            for c in root_sh.iter():
                if not (c.tag.endswith("}c") or c.tag == "c"):
                    continue
                ctype = c.attrib.get("t")
                v_elem = next((ch for ch in c if ch.tag.endswith("}v") or ch.tag == "v"), None)
                if v_elem is None or v_elem.text is None:
                    continue
                val = v_elem.text
                if ctype == "s" and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
                cells.append(val)
        return {"sheet": sheet_name, "cell_count": len(cells), "sample_cells": cells[:10]}

    def _spreadsheet_broker_reader(read_path: str) -> dict[str, object]:
        normalized_rel = read_path.replace("\\", "/").lstrip("/")
        target = (ROOT / normalized_rel).resolve()
        if ROOT.resolve() not in target.parents or not target.is_file():
            raise ValueError(f"SPREADSHEET_PATH_OUT_OF_SCOPE:{read_path}")
        raw_bytes = target.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        suffix = target.suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise ValueError(f"SPREADSHEET_UNSUPPORTED_FORMAT:{suffix}")
        extra = _read_xlsx_summary(raw_bytes) if suffix == ".xlsx" else {}
        return {
            "relative_path": normalized_rel,
            "format": suffix.lstrip("."),
            "sha256": digest,
            "receipt_id": str(uuid4()),
            **extra,
        }

    def _obligation_web_reader(read_path: str) -> dict[str, object]:
        if read_path.startswith("https://"):
            import urllib.parse
            import urllib.request

            if not allowed_https_domains:
                raise PermissionError("OBLIGATION_EXTERNAL_HOST_ALLOWLIST_REQUIRED")
            parsed = urllib.parse.urlparse(read_path)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not host or host not in allowed_https_domains:
                raise PermissionError(f"OBLIGATION_EXTERNAL_HOST_NOT_ALLOWED:{host or read_path}")
            req = urllib.request.Request(read_path, headers={"User-Agent": "AI-Proje-Ofisi-Verifier/1.0"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=10.0) as resp:
                raw_bytes = resp.read(131072)
            return {
                "source": read_path,
                "host": host,
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "receipt_id": str(uuid4()),
            }
        normalized_rel = read_path.replace("\\", "/").lstrip("/")
        target = (ROOT / normalized_rel).resolve()
        if ROOT.resolve() not in target.parents or not target.is_file():
            raise PermissionError(f"OBLIGATION_SOURCE_OUT_OF_SCOPE:{read_path}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return {
            "source": normalized_rel,
            "sha256": digest,
            "receipt_id": str(uuid4()),
        }

    runner = LiveOfficeTaskRunner(
        tenant_id="t1",
        ollama_client=ollama_client,
        research_broker_reader=_research_broker_reader if args.skip_wsl else None,
        kernel_research_read=(
            (lambda scope: _kernel_research_readback(args.wsl_distro, args.research_readback_service, scope))
            if args.research_readback_service and not args.skip_wsl else None
        ),
        research_receipt_readback=(
            (lambda scope, receipt: _kernel_research_readback(
                args.wsl_distro, args.research_readback_service, scope, receipt
            )) if args.research_readback_service and not args.skip_wsl else None
        ),
        spreadsheet_broker_reader=_spreadsheet_broker_reader,
        obligation_web_reader=_obligation_web_reader,
        persist_submission=(
            None
            if args.skip_wsl
            else (
                lambda spec, bearer: _persist_submission_via_wsl_kernel(
                    args.wsl_distro,
                    spec,
                    bearer,
                    require_session_token=args.require_session_token,
                )
            )
        ),
        persist_result=(
            None if args.skip_wsl else (lambda rec: _persist_validation_to_wsl_pg087(args.wsl_distro, rec))
        ),
        on_task_accepted=coordinator.on_task_verified,
        on_task_settled=lambda _rec: _evaluate_ceo_improvement(),
        agent_registry=agent_registry,
        registry_tenant_id=DEFAULT_TENANT_ID,
        engineer_pilot_catalog=engineer_pilot_catalog,
        project_id=DEFAULT_PROJECT_ID,
        poll_interval_seconds=0.4,
    )
    ceo_engine = CeoContinuousImprovementEngine(
        task_submitter=lambda payload, bearer: runner.submit_task(payload, bearer_token=bearer),
    )

    def _improvement_state_context() -> dict:
        return {
            "runs": runner.list_runs(limit=25),
            "memory_promotions": coordinator.list_promotions(),
            "budget": coordinator.budget_summary(),
            "external_effects": coordinator.list_effects(),
        }

    def _evaluate_ceo_improvement() -> dict:
        ctx = _improvement_state_context()
        return ceo_engine.evaluate_company_state(
            runs=ctx["runs"],
            memory_promotions=ctx["memory_promotions"],
            budget=ctx["budget"],
            external_effects=ctx["external_effects"],
        )

    _evaluate_ceo_improvement()
    runner.start_background()
    print("[3/4] AutonomousWorkerDaemon + yerel Ollama + AgentInstance + hafiza/butce hazir.", flush=True)

    allowed_projects = frozenset({DEFAULT_PROJECT_ID})

    def _live_snapshot() -> dict:
        snap = (
            {"mode": "LOCAL_OFFICE_ONLY", "connected": True, "counts": {}, "tasks": [], "approvals": [], "outbox": []}
            if args.skip_wsl
            else fetch_live_office_snapshot(args.wsl_distro)
        )
        snap["command_enabled"] = True
        snap["lifecycle_enabled"] = True
        snap["require_session_token"] = bool(args.require_session_token)
        snap["ollama"] = ollama_client.check_health(timeout=1.5)
        snap["worker_runner"] = runner.status_summary()
        snap["office_runs"] = runner.list_runs(limit=30)
        snap["memory_promotions"] = coordinator.list_promotions()
        snap["budget"] = coordinator.budget_summary()
        snap["external_effects"] = coordinator.list_effects()
        snap["ceo_improvement"] = _evaluate_ceo_improvement()
        if not snap.get("agent_instances"):
            snap["agent_instances"] = agent_registry.list_authorized(
                tenant_id=DEFAULT_TENANT_ID,
                project_id=DEFAULT_PROJECT_ID,
                allowed_tenant_id=DEFAULT_TENANT_ID,
                allowed_project_ids=allowed_projects,
            )
        return snap

    event_replay = OfficeEventReplay("t1", unordered_sources=frozenset({"outbox"}))

    def _live_events(tenant_id: str, last_event_id: int) -> list[str]:
        if tenant_id != "t1":
            return []
        snap = fetch_live_office_snapshot(args.wsl_distro) if not args.skip_wsl else {}
        outbox = [
            ProjectionEvent(
                item["event_id"], "t1", item["kind"], {"created_at": item["created_at"]}
            )
            for item in reversed(snap.get("outbox") or [])
        ]
        lifecycle = [
            ProjectionEvent(event.sequence, "t1", event.event_type, event.payload)
            for event in coordinator.recent_events()
            if event.tenant_id == DEFAULT_TENANT_ID
        ]
        return event_replay.read(tenant_id, last_event_id, {
            "ready": (1, [ProjectionEvent(1, "t1", "OfficeLiveReady", {"model": args.ollama_model})]),
            "outbox": (12, outbox),
            "runner": (200, runner.recent_events()),
            "lifecycle": (200, lifecycle),
        })

    app = make_wsgi_app(
        event_replay_provider=_live_events,
        catalog_provider=(
            None
            if engineer_pilot_catalog is None
            else (lambda tid: engineer_pilot_catalog.list_catalog_entries(tid))
        ),
        promotions_provider=lambda _tid: coordinator.list_promotions(),
        effects_provider=lambda _tid: coordinator.list_effects(),
        live_snapshot_provider=_live_snapshot,
        office_task_submitter=lambda payload, bearer: runner.submit_task(payload, bearer_token=bearer),
        office_tasks_provider=lambda: runner.list_runs(limit=20),
        memory_action_handler=lambda payload: dispatch_memory_action(coordinator, payload),
        external_effect_handler=lambda payload: dispatch_external_effect_action(coordinator, payload),
        agent_instances_provider=lambda tid, pid: agent_registry.list_authorized(
            tenant_id=tid,
            project_id=pid,
            allowed_tenant_id=DEFAULT_TENANT_ID,
            allowed_project_ids=allowed_projects,
        ),
        ceo_improvement_provider=_evaluate_ceo_improvement,
        ceo_improvement_handler=lambda payload, bearer: ceo_engine.handle_action(
            payload,
            bearer_token=bearer,
            state_provider=_improvement_state_context,
        ),
    )
    url_office = f"http://{args.host}:{args.port}/"
    url_events = f"http://{args.host}:{args.port}/live-events"

    print(f"[4/4] Canli Ofis ve SSE sunucusu aciliyor: {url_office}", flush=True)
    print(f"      Canli Olay Paneli: {url_events}", flush=True)
    print("      Kapatmak icin Ctrl+C tuslarina basin.", flush=True)

    if not args.no_browser:
        def _open_browser():
            time.sleep(1.0)
            webbrowser.open(url_office)

        threading.Thread(target=_open_browser, daemon=True).start()

    with make_server(args.host, args.port, app) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nAI Proje Ofisi sunucusu durduruldu.", flush=True)
        finally:
            runner.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
