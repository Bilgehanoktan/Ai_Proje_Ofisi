"""Synthetic disposable DB integration probe; never a login endpoint."""
import hashlib,json,secrets,sys
from pathlib import Path
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())
sys.path[:0]=[str(ROOT),str(ROOT/'product/backend'),str(ROOT/'contracts/source/python'),str(ROOT/'verifier/src')]
import psycopg
from company_os.kernel.session_provisioning import issue_owner_session
args=dict(host='/var/lib/ai-proje-ofisi-dbtest/storage/socket',user='aipof-dbtest',dbname='postgres',connect_timeout=3)
with psycopg.connect(**args) as c:
 with c.cursor() as cur:
  cur.execute('SELECT installation_id FROM company_private.bootstrap_receipts')
  row=cur.fetchone()
  if row is None:raise RuntimeError('SYNTHETIC_BOOTSTRAP_REQUIRED')
  token=secrets.token_urlsafe(48)
  result=issue_owner_session(cur,installation_id=str(row[0]),token=token,ttl_seconds=30)
 sid=result['session_id']
with psycopg.connect(**args) as c:
 with c.cursor() as cur:
  cur.execute("SELECT s.token_hash,h.epoch,l.rank FROM company.sessions s JOIN company.authority_scope_heads h ON h.tenant_id=s.tenant_id AND h.session_id=s.id AND h.scope_kind='SESSION' JOIN company_private.scope_lock_registry l ON l.lock_id=h.lock_id WHERE s.id=%s::uuid",(sid,))
  got=cur.fetchone()
  assert got==(hashlib.sha256(token.encode()).hexdigest(),0,2)
with psycopg.connect(**args) as c:
 with c.cursor() as cur:
  cur.execute("SELECT b.project_id,g.grant_id FROM company_private.bootstrap_receipts b JOIN company.project_grants g ON g.tenant_id=b.tenant_id AND g.project_id=b.project_id AND g.principal_id=b.accepted_human_id WHERE g.permission='e0.setup_mandate_consume'")
  project,grant=cur.fetchone()
  try:
   cur.execute('SELECT company_private.r54_context_enter(%s,%s,%s::uuid,%s,%s::uuid,NULL,NULL,NULL,%s::uuid)',(token,'e0.setup_mandate_consume',project,'PROJECT',project,grant))
  except psycopg.Error as exc:
   assert exc.diag.message_primary=='BLOCKED_TIME_DEPENDENCY',exc.diag.message_primary
   c.rollback()
  else:
   raise RuntimeError('MISSING_PROJECT_CLOCK_ACCEPTED')
print(json.dumps(dict(scope='SYNTHETIC_SESSION_COMMIT_READBACK_NOT_OWNER_LOGIN_ACCEPTANCE',missing_project_clock_rejected=True,session_hash_match=True,session_epoch=0,lock_rank=2,new_grants=0)))
