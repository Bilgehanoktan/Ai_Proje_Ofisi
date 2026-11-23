"""Binding and DB metadata doubles; no real enrollment or grants are minted."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

from company_os.api.http.kernel_binding import load_binding, make_connector, check_connection, required_functions, BindingBlocked


def profile():
    return dict(version='company.http-kernel-binding/1',canonical_workspace='E:\\Projeler\\Ai_Proje_Ofisi',
        postgres_service='fixture_service',database='fixture_db',expected_login='fixture_transport',
        socket_directory='/tmp/fixture-postgres',project_id=str(uuid4()),
        grant_ids={'objectives.create':str(uuid4())},port=8766,emission_timeout=1)


class MetadataConnection:
    def __init__(self,pins):
        self.info=SimpleNamespace(host=pins['socket_directory'],transaction_status=0)
        self.autocommit=False;self.closed=False;self.calls=[]
        self.row=(pins['expected_login'],pins['expected_login'],pins['database'],False,False,False,False)
        self.rows=[(name,True) for name in required_functions(pins)]
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args=()): self.calls.append((sql,args))
    def fetchone(self): return self.row
    def fetchall(self): return self.rows
    def rollback(self): self.calls.append(('ROLLBACK',()))
    def close(self): self.closed=True


class KernelBindingTests(unittest.TestCase):
    def load(self,data):
        raw=json.dumps(data).encode()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json';path.write_bytes(raw)
            return load_binding(path,expected_sha256=hashlib.sha256(raw).hexdigest())
    def test_external_bytes_pin_and_exact_nonsecret_profile(self):
        pins=profile();self.assertEqual(self.load(pins),pins)
        for changes in ({'password':'never-allowed'},{'socket_directory':'127.0.0.1'},
                {'port':True},{'canonical_workspace':'other'}, {'version':'TEMPLATE'},
                {'grant_ids':{'worker.claim':str(uuid4())}},{'emission_timeout':0}):
            with self.subTest(changes=changes),self.assertRaises(BindingBlocked):
                self.load(dict(pins,**changes))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json';path.write_bytes(b'{}')
            with self.assertRaises(BindingBlocked):load_binding(path,expected_sha256='a'*64)
    def test_readonly_metadata_and_access_check_leaves_connection_idle(self):
        pins=profile();connection=MetadataConnection(pins)
        result=check_connection(connection,pins)
        self.assertEqual(result['status'],'BINDINGS_PRECHECK_PASSED_NOT_ACCEPTANCE')
        self.assertEqual(connection.calls[0][0],'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertEqual(connection.calls[-1][0],'ROLLBACK')
        self.assertFalse(connection.closed)
        self.assertFalse(any(sql.startswith(('INSERT','UPDATE','CREATE','GRANT')) for sql,_ in connection.calls))
    def test_wrong_login_role_database_socket_or_function_access_closes(self):
        pins=profile()
        for mutation in ('superuser','bypassrls','createrole','login','database','socket','functions','autocommit'):
            c=MetadataConnection(pins)
            if mutation in ('superuser','bypassrls','createrole'):
                row=list(c.row);row[{'superuser':4,'bypassrls':5,'createrole':6}[mutation]]=True;c.row=tuple(row)
            elif mutation=='login':c.row=('wrong',)+c.row[1:]
            elif mutation=='database':c.row=c.row[:2]+('wrong',)+c.row[3:]
            elif mutation=='socket':c.info.host='127.0.0.1'
            elif mutation=='functions':c.rows=c.rows[:-1]
            else:c.autocommit=True
            with self.subTest(mutation=mutation),self.assertRaises(BindingBlocked):check_connection(c,pins)
            self.assertTrue(c.closed)
    def test_connector_pins_driver_arguments_and_rechecks_every_connection(self):
        pins=profile();original=json.loads(json.dumps(pins));calls=[];connections=[]
        def driver(**kwargs):
            calls.append(kwargs);c=MetadataConnection(original);connections.append(c);return c
        connect=make_connector(pins,driver_connect=driver)
        pins['database']='changed'
        for _ in range(2):connect().close()
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]['dbname'],'fixture_db')
        self.assertEqual(calls[0]['host'],'/tmp/fixture-postgres')
        self.assertTrue(all(c.calls for c in connections))
    def test_driver_error_does_not_expose_connection_secrets(self):
        def failed(**kwargs):raise RuntimeError('fixture-sensitive-driver-details')
        with self.assertRaisesRegex(BindingBlocked,'^KERNEL_CONNECTION_UNAVAILABLE$'):
            make_connector(profile(),driver_connect=failed)()


class ConstructorBindingCoverageTests(unittest.TestCase):
    def test_plan_and_task_only_profiles_require_canonical_constructor_readback(self):
        for operation in ('plans.create', 'tasks.create'):
            pins = profile()
            pins['grant_ids'] = {operation: str(uuid4())}
            functions = required_functions(pins)
            self.assertIn('company_private.r63_constructor_result(uuid)', functions)
            self.assertTrue(any(operation.split('.')[0]+'_create(' in name for name in functions))
