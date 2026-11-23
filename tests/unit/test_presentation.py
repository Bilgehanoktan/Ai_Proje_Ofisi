import unittest
from types import SimpleNamespace
from uuid import uuid4
from company_os.kernel.command_host import Blocked
from company_os.api.http.app import AuthenticatedReadbackApp, render_workflow_html


class ReadCursor:
    def __init__(self, conn):
        self.c = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=()):
        self.c.h.calls.append((sql, args))
        self.c.last = sql
        self.c.args = args

    def fetchone(self):
        sql = self.c.last
        if 'r54_context_enter' in sql:
            return ('nonce',)
        if 'r58_emission_snapshot' in sql:
            return ({'project_epoch': 1},)
        if 'r54_tasks_read' in sql:
            return ({
                'id': self.c.h.task_id,
                'project_id': self.c.h.project_id,
                'title': 'MGT-TITLE-NORMALIZATION-01',
                'state': 'ACCEPTED',
                'revision': 3,
                'active_attempt_id': self.c.h.attempt_id,
            },)
        for name, kind, record in [
            ('r54_attempts_read', 'Attempt', {'id': self.c.h.attempt_id, 'state': 'PRODUCED', 'fencing_epoch': 1}),
            ('r54_qualifications_read', 'Qualification', {'id': self.c.h.qualification_id, 'role_id': 'EXP-001'}),
            ('r54_agent_runs_read', 'AgentRun', {'id': self.c.h.process_id, 'state': 'STOPPED', 'revision': 4}),
            ('r54_tool_requests_read', 'ToolRequest', {'request_id': self.c.h.tool_request_id, 'receipt_id': 'r1'}),
            ('r54_evidence_read', 'Evidence', {'id': self.c.h.evidence_id, 'artifact_id': 'art1'}),
            ('r54_acceptance_decisions_read', 'AcceptanceDecision', {'id': self.c.h.acceptance_id, 'accepted_by': 'human1'}),
        ]:
            if name in sql:
                expected_digest = self.c.args[3]
                digest = kind.lower()[0] * 64
                if expected_digest is not None and expected_digest != digest:
                    raise RuntimeError('STALE_SOURCE_DIGEST')
                return ({
                    'kind': kind,
                    'record': record,
                    'source_digest': digest,
                    'project_sequence': 12,
                    'event_writer_generation': 54,
                    'authority_epoch': 1,
                    'ui_generation': self.c.args[4],
                    'pagination': None,
                    'command_receipt_ref': None,
                    'access_audit_correlation': str(uuid4()),
                },)
        return ({},)


class ReadConn:
    def __init__(self, h):
        self.h = h
        self.info = SimpleNamespace(transaction_status=0)
        self.last = ''
        self.args = ()

    def cursor(self):
        return ReadCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.project_id = str(uuid4())
        self.task_id = str(uuid4())
        self.attempt_id = str(uuid4())
        self.qualification_id = str(uuid4())
        self.process_id = str(uuid4())
        self.tool_request_id = str(uuid4())
        self.evidence_id = str(uuid4())
        self.acceptance_id = str(uuid4())
        self.app = AuthenticatedReadbackApp(connect=lambda: ReadConn(self))
        base_auth = {'token': 'x' * 32, 'project_id': self.project_id, 'grant_id': str(uuid4())}
        self.auth_by_op = {
            op: dict(base_auth)
            for op in (
                'attempts.read',
                'qualifications.read',
                'agent_runs.read',
                'tool_requests.read',
                'evidence.read',
                'acceptance_decisions.read',
            )
        }

    def test_load_and_render_committed_workflow_view_and_reload(self):
        v1 = self.app.load_workflow_view(
            self.auth_by_op,
            task_id=self.task_id,
            attempt_id=self.attempt_id,
            qualification_id=self.qualification_id,
            process_run_id=self.process_id,
            tool_request_id=self.tool_request_id,
            evidence_id=self.evidence_id,
            acceptance_id=self.acceptance_id,
            ui_generation=1,
        )
        self.assertEqual(v1['attempt']['envelope']['record']['state'], 'PRODUCED')
        html_doc = render_workflow_html(v1)
        self.assertIn('AUTHENTICATED_COMMITTED_KERNEL_READBACK', html_doc)
        self.assertIn(self.task_id, html_doc)

        v2 = self.app.load_workflow_view(
            self.auth_by_op,
            task_id=self.task_id,
            attempt_id=self.attempt_id,
            qualification_id=self.qualification_id,
            process_run_id=self.process_id,
            tool_request_id=self.tool_request_id,
            evidence_id=self.evidence_id,
            acceptance_id=self.acceptance_id,
            ui_generation=2,
            expected_digests=v1['digests'],
        )
        self.assertEqual(v2['digests'], v1['digests'])

    def test_stale_digest_and_missing_auth_are_blocked(self):
        with self.assertRaises(Blocked):
            self.app.read_detail({}, 'attempts', task_id=self.task_id, record_id=self.attempt_id)
        with self.assertRaises(Blocked):
            self.app.read_detail(
                self.auth_by_op['attempts.read'],
                'attempts',
                task_id=self.task_id,
                record_id=self.attempt_id,
                attempt_id=self.attempt_id,
                expected_digest='0' * 64,
                ui_generation=1,
            )


    def test_wsgi_endpoints(self):
        from company_os.api.http.app import make_wsgi_app
        wsgi_app = make_wsgi_app()

        # Test GET /
        status_box = []
        headers_box = []
        def start_response(status, headers):
            status_box.append(status)
            headers_box.extend(headers)

        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/'}
        res = wsgi_app(environ, start_response)
        self.assertEqual(status_box[0], '200 OK')
        body = b''.join(res).decode('utf-8')
        self.assertIn('AI Proje Ofisi', body)
        self.assertIn('MOD-011', body)

        # Test GET /api/status
        status_box.clear()
        environ = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/api/status'}
        res = wsgi_app(environ, start_response)
        self.assertEqual(status_box[0], '200 OK')
        import json
        data = json.loads(b''.join(res).decode('utf-8'))
        self.assertEqual(data['status'], 'OK')
        self.assertEqual(len(data['modules']), 16)

        # Test POST method not allowed
        status_box.clear()
        environ = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/'}
        res = wsgi_app(environ, start_response)
        self.assertEqual(status_box[0], '405 Method Not Allowed')
