"""Read the committed Kernel workspace.read witness for one exact attempt."""

from uuid import UUID


READBACK_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM company_private.r60_tool_consumptions AS c
    JOIN company_private.r60_engine_streams AS s
      USING (tenant_id, project_id, engine_session_id, process_id)
    JOIN company_private.r58_attestations AS a
      ON (a.tenant_id, a.project_id, a.id) =
         (c.tenant_id, c.project_id, c.effect_attestation_id)
    WHERE s.tenant_id = %s AND s.project_id = %s
      AND s.task_id = %s AND s.attempt_id = %s AND a.id = %s
      AND c.state = 'SUCCEEDED' AND a.profile = 'r60.tool-effect.v1'
      AND a.payload->>'consume_id' = c.id::text
      AND a.payload->>'frame_digest' = c.frame_digest
      AND a.payload->>'process_id' = c.process_id::text
      AND a.payload->>'outcome' = 'SUCCEEDED'
      AND a.payload->'effect'->>'kind' = 'READ'
      AND convert_from(c.frame_bytes, 'UTF8')::jsonb #>> '{call,tool_id}' = 'workspace.read'
      AND convert_from(c.frame_bytes, 'UTF8')::jsonb #>> '{call,arguments,relative_path}' = %s
)
"""


def confirm_receipt(connect, scope, receipt_id, *, require_current=False):
    """Open a fresh read-only transaction. No cache and no mutable office state."""
    try:
        ids = [UUID(str(scope[key])) for key in ('tenant_id', 'project_id', 'task_id', 'attempt_id')]
        receipt = UUID(str(receipt_id))
        path = scope['read_path']
    except (KeyError, TypeError, ValueError):
        return False
    if not isinstance(path, str) or not path or '\x00' in path:
        return False
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        sql = READBACK_SQL
        if require_current:
            sql += """ AND EXISTS (
                SELECT 1 FROM company.tasks
                WHERE tenant_id=%s AND project_id=%s AND id=%s AND active_attempt_id=%s
            )"""
        params = (*ids, receipt, path)
        cur.execute(sql, params + tuple(ids) if require_current else params)
        return cur.fetchone() == (True,)


def current_read(connect, scope):
    """Collect a completed Broker read only for the task's Kernel-selected attempt."""
    query = """
        SELECT s.attempt_id, c.effect_attestation_id, a.payload->>'effect_digest'
        FROM company.tasks t
        JOIN company_private.r60_engine_streams s
          ON (s.tenant_id,s.project_id,s.task_id,s.attempt_id,s.fence)
           = (t.tenant_id,t.project_id,t.id,t.active_attempt_id,t.fencing_epoch)
        JOIN company_private.r60_tool_consumptions c
          ON (c.tenant_id,c.project_id,c.engine_session_id,c.process_id)
           = (s.tenant_id,s.project_id,s.engine_session_id,s.process_id)
        JOIN company_private.r58_attestations a
          ON (a.tenant_id,a.project_id,a.id) = (c.tenant_id,c.project_id,c.effect_attestation_id)
        WHERE t.tenant_id=%s AND t.project_id=%s AND t.id=%s
          AND c.state='SUCCEEDED' AND a.profile='r60.tool-effect.v1'
          AND convert_from(c.frame_bytes,'UTF8')::jsonb #>> '{call,tool_id}'='workspace.read'
          AND convert_from(c.frame_bytes,'UTF8')::jsonb #>> '{call,arguments,relative_path}'=%s
        ORDER BY c.sequence DESC LIMIT 2
    """
    ids = [UUID(str(scope[key])) for key in ('tenant_id', 'project_id', 'task_id')]
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY')
        cur.execute(query, (*ids, scope['read_path']))
        rows = cur.fetchall()
    if len(rows) != 1:
        raise ValueError('UNIQUE_KERNEL_RESEARCH_READ_REQUIRED')
    attempt, receipt, digest = rows[0]
    return {'attempt_id': str(attempt), 'receipt_id': str(receipt),
            'relative_path': scope['read_path'], 'sha256': digest}
