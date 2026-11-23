"""HTTP/adapter behavior; fake backend results are not runtime evidence."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from company_os.kernel import command_host
from company_os.api.http.task_http import create_server, create_project_backend, KernelTaskBackend, BadRequest, SessionRequired, decode_body


class TaskHttpTests(unittest.TestCase):
    def setUp(self):
        self.server=create_server(port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        connection.request(method,path,body,headers or {})
        response=connection.getresponse();result=(response.status,dict(response.getheaders()),response.read())
        connection.close();return result
    def test_page_and_explicit_unconfigured_state_no_fake_tasks(self):
        status,headers,body=self.request('GET','/tasks')
        self.assertEqual(status,200);self.assertIn('Yeni iş isteği',body.decode())
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        status,_,raw=self.request('GET','/api/connection')
        self.assertEqual(json.loads(raw),dict(configured=False,execution_verified=False))
        status,_,raw=self.request('GET','/progress')
        self.assertEqual(status,200)
        self.assertIn('Güvenlik (Security)',raw.decode())
        status,_,_=self.request('POST','/api/objectives','{}',{'Origin':f'http://127.0.0.1:{self.port}'})
        self.assertEqual(status,503)
    def test_foreign_origin_and_host_are_rejected(self):
        self.assertEqual(self.request('POST','/api/objectives','{}',{'Origin':'http://foreign.test'})[0],403)
        self.assertEqual(self.request('GET','/api/connection',headers={'Host':'foreign.test'})[0],403)
    def test_moved_frontend_assets_are_served_without_exposing_source(self):
        for path, kind in [('/tasks.js','text/javascript'),('/tasks.css','text/css'),('/progress.css','text/css')]:
            with self.subTest(path=path):
                status, headers, body = self.request('GET', path)
                self.assertEqual(status, 200)
                self.assertTrue(headers['Content-Type'].startswith(kind))
                self.assertTrue(body)
        self.assertEqual(self.request('GET','/../../product/backend/company_os/kernel/command_host.py')[0],404)
    def test_office_keeps_inline_hash_csp_and_task_link(self):
        status,headers,raw=self.request('GET','/office')
        self.assertEqual(status,200);self.assertIn("'sha256-",headers['Content-Security-Policy'])
        self.assertIn('href="/tasks"',raw.decode())


class KernelTaskBackendTests(unittest.TestCase):
    def setUp(self):
        self.project=str(uuid4());self.request_id=str(uuid4())
        self.auth=dict(token='fixture-only',project_id=self.project,grant_id=str(uuid4()),kind='PROJECT',resource_id=self.project)
        self.backend=KernelTaskBackend(connect=lambda:'dedicated-fixture-connection',
            resolve_session=lambda bearer,op:self.auth,emission_timeout=1)
        self.body=dict(goal='Fix the title normalization function',constraints=['Only the specified file'],
            expected_outputs=['Corrected file and independent check'],request_id=self.request_id)
    def test_objective_uses_server_scope_exact_contract_and_stable_idempotency(self):
        envelope=dict(operation='objectives.create',result={'id':'fixture'},command_receipt={'command_id':'fixture'},snapshot={})
        with patch.object(command_host,'execute',return_value=envelope) as execute:
            auth,result=self.backend.prepare('fixture-session','/api/objectives',self.body)
            args=execute.call_args.args
            self.assertEqual(args[2],'objectives.create')
            native=json.loads(args[3][0]);self.assertEqual(native['project_id'],self.project)
            self.assertEqual(native['idempotency_key'],'ui-objective-'+self.request_id)
            self.assertEqual(native['correlation_id'],self.request_id)
            self.assertEqual(result,envelope)
        with patch.object(command_host,'emit',return_value={}) as emit:
            socket=object();self.backend.emit((auth,result),socket)
            self.assertIs(emit.call_args.args[3],socket)
            self.assertEqual(emit.call_args.args[4],1)
    def test_scope_injection_and_invalid_contract_block_before_db(self):
        for body in (dict(self.body,project_id=str(uuid4())),dict(self.body,constraints=[]),dict(self.body,request_id='wrong')):
            with self.subTest(body=body),patch.object(command_host,'execute') as execute,self.assertRaises(BadRequest):
                self.backend.prepare('fixture-session','/api/objectives',body)
            execute.assert_not_called()
    def test_unknown_commit_never_retries(self):
        with patch.object(command_host,'execute',side_effect=command_host.UnknownCommitOutcome()) as execute:
            with self.assertRaises(command_host.UnknownCommitOutcome):
                self.backend.prepare('fixture-session','/api/objectives',self.body)
            self.assertEqual(execute.call_count,1)
    def test_detail_reenters_kernel_with_task_scope_and_requires_canonical_record(self):
        task=str(uuid4());record=str(uuid4())
        body=dict(resource='attempts',task_id=task,record_id=record,attempt_id=None,expected_digest=None,ui_generation=0)
        result=dict(record={},source_digest='a'*64,project_sequence=1,authority_epoch=1,access_audit_correlation='fixture')
        with patch.object(command_host,'execute',return_value={'result':result}) as execute:
            self.backend.prepare('fixture','/api/details',body)
            auth=execute.call_args.args[1]
            self.assertEqual((auth['kind'],auth['resource_id']),('TASK',task))
            self.assertEqual(execute.call_args.args[2],'candidate.r54.attempts.read')
        with patch.object(command_host,'execute',return_value={'result':{}}),self.assertRaises(command_host.Blocked):
            self.backend.prepare('fixture','/api/details',body)
    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for raw in (b'{"goal":"a","goal":"b"}',b'{"x":NaN}',b'[]'):
            with self.subTest(raw=raw),self.assertRaises(BadRequest):decode_body(raw)

    def test_project_binding_passes_token_to_native_without_minting_session(self):
        grants={'objectives.create':self.auth['grant_id']}
        backend=create_project_backend(connect=lambda:None,project_id=self.project,
            grant_ids=grants,emission_timeout=1)
        grants['objectives.create']=str(uuid4())
        auth=backend.resolve_session('fixture-native-token','objectives.create')
        self.assertEqual(auth['token'],'fixture-native-token')
        self.assertEqual(auth['grant_id'],self.auth['grant_id'])
        with self.assertRaises(SessionRequired):
            backend.resolve_session('fixture-native-token','candidate.r54.attempts.read')


class TransportTests(unittest.TestCase):
    def test_unknown_commit_is_409_and_partial_emission_never_retries(self):
        class FixtureBackend:
            def __init__(self):self.unknown=True;self.emits=0
            def prepare(self,*args):
                if self.unknown:raise command_host.UnknownCommitOutcome()
                return None
            def emit(self,prepared,socket):
                self.emits+=1;socket.sendall(b'{"partial":');raise OSError('fixture interruption')
        backend=FixtureBackend()
        with create_server(port=0,backend=backend) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def request():
                    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                    c.request('POST','/api/objectives','{}',{'Origin':f'http://127.0.0.1:{server.server_port}',
                        'Authorization':'Bearer fixture','Content-Type':'application/json'})
                    response=c.getresponse();result=(response.status,response.read());c.close();return result
                status,raw=request();self.assertEqual(status,409)
                self.assertEqual(json.loads(raw)['error'],'OUTCOME_UNKNOWN_DO_NOT_RESUBMIT')
                backend.unknown=False
                status,raw=request();self.assertEqual(status,200)
                self.assertEqual(raw,b'{"partial":');self.assertEqual(backend.emits,1)
            finally:server.shutdown();thread.join()

class NativeHttpChainTests(unittest.TestCase):
    """Real HTTP and command host, scripted DB-API boundary; not live DB acceptance."""

    def test_configuration_exposes_only_bound_routes(self):
        project = str(uuid4())
        for grants, writable, resources in [
            ({'objectives.create': str(uuid4())}, True, []),
            ({'candidate.r54.attempts.read': str(uuid4())}, False, ['attempts']),
        ]:
            backend = create_project_backend(
                connect=lambda: self.fail('Metadata must not open a DB connection'),
                project_id=project, grant_ids=grants, emission_timeout=1,
            )
            state = backend.connection_state()
            self.assertEqual(state['can_create_objective'], writable)
            self.assertEqual(state['detail_resources'], resources)
            self.assertFalse(state['execution_verified'])

    def test_http_runs_native_commit_then_fresh_authorized_emission(self):
        from types import SimpleNamespace

        command_id = str(uuid4())
        objective_id = str(uuid4())
        events = []
        connections = []

        class Connection:
            def __init__(self):
                self.info = SimpleNamespace(transaction_status=0)
                self.index = len(connections)
                self.closed = False
                self.last = ''
                connections.append(self)

            def cursor(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, args=()):
                self.last = sql
                events.append((self.index, sql, args))

            def fetchone(self):
                if 'r54_context_enter(' in self.last:
                    return ('fixture-nonce',)
                if 'r58_emission_snapshot(' in self.last:
                    return ({'epoch': 1},)
                if 'r58_emission_check(' in self.last:
                    return (True,)
                if 'r63_constructor_result(' in self.last:
                    return ({'command_id': command_id, 'state': 'SUCCEEDED',
                             'result_ref': objective_id,
                             'result_payload': {'id': objective_id}},)
                return ({'command_id': command_id, 'state': 'SUCCEEDED'},)

            def commit(self):
                events.append((self.index, 'COMMIT', ()))

            def rollback(self):
                events.append((self.index, 'ROLLBACK', ()))

            def close(self):
                self.closed = True

        backend = create_project_backend(
            connect=Connection, project_id=str(uuid4()),
            grant_ids={'objectives.create': str(uuid4())}, emission_timeout=2,
        )
        body = dict(goal='Normalize the title of the requested file',
                    constraints=['Only one file'], expected_outputs=['Corrected file'],
                    request_id=str(uuid4()))
        with create_server(port=0, backend=backend) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    client.request('POST', '/api/objectives', json.dumps(body), {
                        'Origin': f'http://127.0.0.1:{server.server_port}',
                        'Authorization': 'Bearer fixture-only', 'Content-Type': 'application/json',
                    })
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    payload = json.loads(response.read())
                finally:
                    client.close()
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual(payload['semantics'], 'AUTHORIZED_FACT_NOT_CURRENT_STATE')
        self.assertEqual(payload['command_receipt']['command_id'], command_id)
        self.assertEqual(payload['result']['id'], objective_id)
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(connection.closed for connection in connections))
        commit_index = next(i for i, event in enumerate(events) if event[:2] == (0, 'COMMIT'))
        emission_index = next(i for i, event in enumerate(events) if event[0] == 1)
        self.assertLess(commit_index, emission_index)
        self.assertTrue(any('r58_emission_check(' in sql for index, sql, _ in events if index == 1))
        creates = [args for _, sql, args in events if 'r53_objectives_create(' in sql]
        self.assertEqual(len(creates), 1)
        self.assertEqual(json.loads(creates[0][0])['idempotency_key'], 'ui-objective-' + body['request_id'])

class ConstructorPanelTests(unittest.TestCase):
    def setUp(self):
        self.project = str(uuid4())
        self.request_id = str(uuid4())
        self.backend = create_project_backend(
            connect=lambda: 'fixture-connection', project_id=self.project,
            grant_ids={op: str(uuid4()) for op in command_host.CONSTRUCTOR_OPERATIONS},
            emission_timeout=1,
        )

    def test_plan_and_task_use_exact_contracts_and_server_scope(self):
        cases = [
            ('/api/plans', 'plans.create', dict(objective_id=str(uuid4()), expected_revision=1,
                assumptions=[], acceptance_criteria=['Correct title'])),
            ('/api/tasks', 'tasks.create', dict(plan_id=str(uuid4()), title='Normalize title',
                role_id='EXP-01', acceptance_criteria=['Correct title'], depends_on=[])),
        ]
        for path, operation, fields in cases:
            with self.subTest(operation=operation), patch.object(command_host, 'execute', return_value={}) as execute:
                self.backend.prepare('fixture-session', path, dict(fields, request_id=self.request_id))
                _, auth, actual_operation, args = execute.call_args.args
                payload = json.loads(args[0])
                self.assertEqual(actual_operation, operation)
                self.assertEqual(auth['kind'], 'PROJECT')
                self.assertEqual(payload['project_id'], self.project)
                self.assertEqual(payload['correlation_id'], self.request_id)
                self.assertEqual(set(payload), set(fields) | {'project_id', 'idempotency_key', 'correlation_id'})
                for extra in ({'project_id': str(uuid4())}, {'grant_id': str(uuid4())}):
                    with self.assertRaises(BadRequest):
                        self.backend.prepare('fixture', path, dict(fields, request_id=self.request_id, **extra))

    def test_invalid_revision_duplicate_dependency_and_parent_rejected_before_db(self):
        dependency = str(uuid4())
        cases = [('/api/plans', dict(objective_id=str(uuid4()), expected_revision=True,
                  assumptions=[], acceptance_criteria=['Correct'])),
                 ('/api/tasks', dict(plan_id=str(uuid4()), title='Normalize title', role_id='EXP-01',
                  acceptance_criteria=['Correct'], depends_on=[dependency, dependency])),
                 ('/api/tasks', dict(plan_id='invalid', title='Normalize title', role_id='EXP-01',
                  acceptance_criteria=['Correct'], depends_on=[]))]
        for path, body in cases:
            with self.subTest(path=path), patch.object(command_host, 'execute') as execute:
                with self.assertRaises(BadRequest):
                    self.backend.prepare('fixture', path, dict(body, request_id=self.request_id))
                execute.assert_not_called()

    def test_receipt_query_never_replays_constructor_and_binds_request(self):
        command_id = str(uuid4())
        body = dict(operation='tasks.create', command_id=command_id, request_id=self.request_id)
        receipt = dict(command_id=command_id, state='SUCCEEDED', correlation_id=self.request_id)
        with patch.object(command_host, 'execute', return_value={'command_receipt': receipt}) as execute:
            self.backend.prepare('fixture', '/api/receipts', body)
            self.assertEqual(execute.call_args.args[2:], ('tasks.create', []))
            self.assertEqual(execute.call_args.kwargs, {'read_command_id': command_id})
        with patch.object(command_host, 'execute', return_value={}), self.assertRaises(command_host.Blocked):
            self.backend.prepare('fixture', '/api/receipts', body)
        with patch.object(command_host, 'execute') as execute, self.assertRaises(BadRequest):
            self.backend.prepare('fixture', '/api/receipts', dict(body, operation='worker.claim'))
        execute.assert_not_called()

    def test_unbound_constructor_never_connects(self):
        backend = create_project_backend(connect=lambda: self.fail('DB must not open'),
            project_id=self.project, grant_ids={'objectives.create': str(uuid4())}, emission_timeout=1)
        with self.assertRaises(SessionRequired):
            backend.prepare('fixture', '/api/receipts', dict(operation='plans.create',
                command_id=str(uuid4()), request_id=self.request_id))
