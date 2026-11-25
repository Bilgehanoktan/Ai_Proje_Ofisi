"""Cold-restart test of the readback predicate against synthetic rows on isolated PG."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verifier/src'))
from independent_verifier.research_readback import confirm_receipt, current_read


def main():
    pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
    env = dict(os.environ, LD_LIBRARY_PATH=str(pg / 'lib/x86_64-linux-gnu'))
    with tempfile.TemporaryDirectory(prefix='research-readback-') as tmp:
        data = Path(tmp) / 'pgdata'
        def run(name, *args):
            subprocess.run([pg / 'lib/postgresql/18/bin' / name, *args], env=env,
                           capture_output=True, check=True, timeout=45)

        def connect():
            return psycopg.connect(host=tmp, dbname='postgres', connect_timeout=4)

        run('initdb', '-D', data, '--auth=peer', '--encoding=UTF8', '--locale=C')
        opts = f"-k {tmp} -c listen_addresses='' -c unix_socket_permissions=0700"
        run('pg_ctl', '-D', data, '-l', Path(tmp) / 'server.log', '-o', opts, '-w', 'start')
        try:
            scope = {key: str(uuid4()) for key in ('tenant_id', 'project_id', 'task_id', 'attempt_id')}
            scope['read_path'] = 'task_title.py'
            receipt, stream, process, consume = (uuid4() for _ in range(4))
            frame = json.dumps({'call': {'tool_id': 'workspace.read',
                                         'arguments': {'relative_path': scope['read_path']}}}).encode()
            digest = hashlib.sha256(frame).hexdigest()
            binding = {'consume_id': str(consume), 'process_id': str(process), 'frame_digest': digest,
                       'outcome': 'SUCCEEDED', 'effect': {'kind': 'READ'}, 'effect_digest': digest}
            with connect() as conn, conn.cursor() as cur:
                cur.execute('CREATE SCHEMA company_private')
                cur.execute('CREATE SCHEMA company')
                cur.execute('''CREATE TABLE company.tasks
                    (tenant_id uuid, project_id uuid, id uuid, active_attempt_id uuid, fencing_epoch bigint)''')
                cur.execute('''CREATE TABLE company_private.r60_engine_streams
                    (tenant_id uuid, project_id uuid, task_id uuid, attempt_id uuid,
                     engine_session_id uuid, process_id uuid, fence bigint default 1)''')
                cur.execute('''CREATE TABLE company_private.r60_tool_consumptions
                    (tenant_id uuid, project_id uuid, engine_session_id uuid, process_id uuid,
                     effect_attestation_id uuid, id uuid, state text, frame_digest text, frame_bytes bytea,
                     sequence bigint default 1)''')
                cur.execute('''CREATE TABLE company_private.r58_attestations
                    (tenant_id uuid, project_id uuid, id uuid, profile text, payload jsonb)''')
                tenant, project = scope['tenant_id'], scope['project_id']
                cur.execute('INSERT INTO company.tasks VALUES (%s,%s,%s,%s,1)',
                            (tenant, project, scope['task_id'], scope['attempt_id']))
                cur.execute('INSERT INTO company_private.r60_engine_streams VALUES (%s,%s,%s,%s,%s,%s)',
                            (tenant, project, scope['task_id'], scope['attempt_id'], stream, process))
                cur.execute('INSERT INTO company_private.r60_tool_consumptions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                            (tenant, project, stream, process, receipt, consume, 'SUCCEEDED', digest, frame))
                cur.execute('INSERT INTO company_private.r58_attestations VALUES (%s,%s,%s,%s,%s)',
                            (tenant, project, receipt, 'r60.tool-effect.v1', Jsonb(binding)))
            run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'restart', '-l', Path(tmp) / 'server.log')
            assert confirm_receipt(connect, scope, receipt)
            assert current_read(connect, scope) == {
                'receipt_id': str(receipt), 'attempt_id': scope['attempt_id'],
                'relative_path': scope['read_path'], 'sha256': digest,
            }
            for key in ('tenant_id', 'project_id', 'task_id', 'attempt_id'):
                assert not confirm_receipt(connect, dict(scope, **{key: str(uuid4())}), receipt), key
            assert not confirm_receipt(connect, dict(scope, read_path='different.py'), receipt)
            assert not confirm_receipt(connect, scope, uuid4())
            assert confirm_receipt(connect, scope, receipt, require_current=True)
            with connect() as conn:
                conn.execute('UPDATE company.tasks SET active_attempt_id=%s, fencing_epoch=2', (uuid4(),))
            assert not confirm_receipt(connect, scope, receipt, require_current=True)
            assert confirm_receipt(connect, scope, receipt)
            print('PASS: cold restart, scoped receipt selection, six mismatches and superseded attempt (synthetic rows)')
        finally:
            run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')


if __name__ == '__main__':
    main()
