"""Existing native schema/ACL precheck in a NEW private test cluster only.

Fixture logins/membership are synthetic. No session, project or grant is minted.
This demonstrates metadata and safe denial, not an approved real HTTP binding.
"""
import http.client
import json
import threading
from uuid import uuid4

from company_os.api.http.kernel_binding import check_connection, BindingBlocked
from company_os.api.http.task_http import create_project_backend, create_server


def probe_http_binding(admin,connect):
    role='aipof_http_binding_fixture'
    admin.execute('CREATE ROLE '+role+' LOGIN INHERIT NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION')
    admin.execute('GRANT company_transport_r54 TO '+role)
    pins=dict(expected_login=role,database=admin.info.dbname,socket_directory=admin.info.host,
        grant_ids={'objectives.create':str(uuid4())})
    connection=connect(role)
    metadata=check_connection(connection,pins)
    if int(connection.info.transaction_status)!=0:raise RuntimeError('binding precheck left active transaction')
    connection.close()
    report=dict(scope='SYNTHETIC_NATIVE_HTTP_BINDING_NOT_ENROLLMENT',metadata_precheck=metadata,
        rollback_idle='PASS')
    def checked():
        connection=connect(role);check_connection(connection,pins);return connection
    backend=create_project_backend(connect=checked,project_id=str(uuid4()),
        grant_ids=pins['grant_ids'],emission_timeout=1)
    with create_server(port=0,backend=backend) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            body=dict(goal='Synthetic request without an enrolled session',constraints=['No real authority'],
                expected_outputs=['Must be denied'],request_id=str(uuid4()))
            client.request('POST','/api/objectives',json.dumps(body),{
                'Origin':'http://127.0.0.1:'+str(server.server_port),
                'Authorization':'Bearer '+'f'*40,'Content-Type':'application/json'})
            response=client.getresponse();payload=json.loads(response.read());client.close()
            if response.status!=403 or payload!={'error':'ACCESS_OR_COMMAND_REJECTED'}:
                raise RuntimeError('unenrolled native HTTP request was not safely rejected')
            report['native_http_unenrolled_session_rejected']='PASS'
        finally:server.shutdown();thread.join()
    count=admin.execute('SELECT count(*) FROM company.commands').fetchone()[0]
    if count!=0:raise RuntimeError('unauthorized HTTP request wrote application commands')
    report['application_commands_after_denial']=count
    admin.execute('REVOKE company_transport_r54 FROM '+role)
    try:check_connection(connect(role),pins)
    except BindingBlocked:report['revoked_transport_membership_rejected']='PASS'
    else:raise RuntimeError('stale transport membership accepted by new connection')
    super_connection=connect('aipof-dbtest')
    try:check_connection(super_connection,dict(pins,expected_login='aipof-dbtest'))
    except BindingBlocked:report['superuser_binding_rejected']='PASS'
    else:raise RuntimeError('superuser accepted as application login')
    return report
