"""Browser checks: live unconfigured page; explicitly mocked transport cases.

No real token/DB/worker is used. Screenshots are the live unconfigured screen.
"""
import json
import argparse
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:raise ValueError('LOCAL_TEST_PORT_REQUIRED')
    EVIDENCE=ROOT/'evidence/runs'/('browser-'+uuid4().hex[:8])
    EVIDENCE.mkdir(parents=True,exist_ok=False)
    report={'scope':'LIVE_UNCONFIGURED_UI_AND_MOCK_HTTP_NOT_RUNTIME_ACCEPTANCE'}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:'+str(args.port),wait_until='networkidle')
        assert page.get_by_role('heading',name='Birlikte yapacağımız iş').is_visible()
        assert page.locator('#connection').inner_text()=='Görev altyapısı bağlı değil'
        assert page.get_by_role('button',name='İş isteğini gönder').is_disabled()
        page.screenshot(path=str(EVIDENCE/'TASK_SCREEN_20261114_desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(EVIDENCE/'TASK_SCREEN_20261114_mobile.png'),full_page=True)
        report['live_unconfigured_desktop_mobile']='PASS'
        page.set_viewport_size({'width':1440,'height':1050})
        page.get_by_role('link',name='Sanal ofis önizlemesi').click()
        page.wait_for_selector('#role-list button',state='attached')
        page.get_by_role('tab',name='Ajanlar',exact=True).click()
        page.locator('#role-list button').filter(has_text='Research').click()
        assert page.locator('#role-title').inner_text()=='Research'
        page.get_by_role('link',name='Görevler',exact=True).click()
        report['existing_office_navigation_and_script']='PASS'
        page.route('**/api/connection', lambda route: route.fulfill(json={
            'configured': True, 'execution_verified': False,
            'can_create_objective': False, 'create_operations': [], 'detail_resources': ['attempts']}))
        page.reload(wait_until='networkidle')
        assert page.get_by_role('button', name='İş isteğini gönder').is_disabled()
        assert page.get_by_role('button', name='Kaydı getir').is_enabled()
        assert page.locator('#resource option[value="acceptance_decisions"]').evaluate("option => option.disabled")
        report['mock_readonly_binding_disables_mutations'] = 'PASS'
        page.unroute('**/api/connection')
        page.route('**/api/connection',lambda route:route.fulfill(json={'configured':True,'execution_verified':False,'can_create_objective':True,'create_operations':['objectives.create','plans.create','tasks.create'],'detail_resources':['attempts','agent_runs','evidence','acceptance_decisions']}))
        calls=[]
        def unknown(route):
            calls.append(route.request.post_data_json)
            route.fulfill(status=409,json={'error':'OUTCOME_UNKNOWN_DO_NOT_RESUBMIT'})
        page.route('**/api/objectives',unknown)
        page.reload(wait_until='networkidle')
        page.locator('#goal').fill('Normalize title in the specified file only')
        page.locator('#constraints').fill('Do not change other files')
        page.locator('#outputs').fill('Corrected file and verification result')
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.get_by_role('button',name='İş isteğini gönder').click()
        expect(page.locator('#feedback')).to_contain_text('henüz bilinmiyor')
        assert page.get_by_role('button',name='İş isteğini gönder').is_disabled()
        assert page.locator('#session').input_value()==''
        identifier=page.locator('#request-ref').inner_text()
        page.reload(wait_until='networkidle')
        assert page.locator('#request-ref').inner_text()==identifier
        assert page.get_by_role('button',name='İş isteğini gönder').is_disabled()
        assert page.locator('#session').is_enabled()
        assert len(calls)==1
        assert calls[0]['request_id'] in identifier
        report['mock_unknown_commit_reload_no_resubmit']='PASS'
        # A failed read must keep the unknown request locked; a matching
        # native receipt may reconcile it without resubmitting the constructor.
        page.locator('#receipt-command').fill('fixture-recovered-command')
        page.route('**/api/receipts', lambda route: route.fulfill(status=403, json={'error':'REJECTED'}))
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.get_by_role('button', name='Makbuzu yeniden oku').click()
        expect(page.locator('#receipt-feedback')).to_contain_text('doğrulanamadı')
        assert page.get_by_role('button', name='İş isteğini gönder').is_disabled()
        page.unroute('**/api/receipts')
        def recovered(route):
            body = route.request.post_data_json
            route.fulfill(json={'semantics':'AUTHORIZED_FACT_NOT_CURRENT_STATE', 'result':{},
                'command_receipt':{'command_id':body['command_id'], 'state':'SUCCEEDED',
                    'result_ref':'fixture-recovered-objective', 'correlation_id':body['request_id']}})
        page.route('**/api/receipts', recovered)
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.get_by_role('button', name='Makbuzu yeniden oku').click()
        expect(page.locator('#receipt-feedback')).to_contain_text('Yeni komut gönderilmedi')
        assert page.get_by_role('button', name='İş isteğini gönder').is_enabled()
        assert len(calls)==1
        report['mock_pending_reconciliation_requires_matching_receipt'] = 'PASS'
        page.unroute('**/api/receipts')
        page.evaluate('sessionStorage.clear()')
        page.unroute('**/api/objectives')
        def accepted(route):
            calls.append(route.request.post_data_json)
            route.fulfill(json={'semantics':'AUTHORIZED_FACT_NOT_CURRENT_STATE',
                'result':{'id':'fixture-objective'},'command_receipt':{'command_id':'fixture-command','state':'SUCCEEDED','result_ref':'fixture-objective','correlation_id':route.request.post_data_json['request_id']}})
        page.route('**/api/objectives',accepted)
        page.reload(wait_until='networkidle')
        page.locator('#goal').fill('Normalize title in the specified file only')
        page.locator('#constraints').fill('Do not change other files')
        page.locator('#outputs').fill('Corrected file and verification result')
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.get_by_role('button',name='İş isteğini gönder').click()
        page.wait_for_selector('#receipt:visible')
        assert page.locator('#receipt-id').inner_text()=='fixture-command'
        assert 'henüz gösterilmedi' in page.locator('#request-state').inner_text()
        assert page.evaluate('sessionStorage.getItem("aipof.pending-objective")') is None
        report['mock_receipt_does_not_claim_agent_execution']='PASS'
        page.route('**/api/details',lambda route:route.fulfill(json={
            'semantics':'AUTHORIZED_FACT_NOT_CURRENT_STATE',
            'result':{'record':{'state':'RUNNING','title':'<img src=x onerror=alert(1)>'}}}))
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.locator('#task-id').fill('00000000-0000-4000-8000-000000000001')
        page.locator('#record-id').fill('00000000-0000-4000-8000-000000000002')
        page.get_by_role('button',name='Kaydı getir').click()
        expect(page.locator('#record-state')).to_have_text('Çalışıyor')
        assert page.locator('#record-title').inner_text()=='<img src=x onerror=alert(1)>'
        assert page.locator('#record img').count()==0
        report['mock_record_plain_language_and_escaped_text']='PASS'
        # Real UI, explicit HTTP doubles: no model/DB acceptance claimed.
        for operation, path in [('plans.create','/api/plans'), ('tasks.create','/api/tasks')]:
            page.route('**'+path, accepted)
            page.locator('#operation').select_option(operation)
            page.locator('#session').fill('fixture-session-not-a-real-secret')
            if operation == 'plans.create':
                page.locator('#objective-id').fill('00000000-0000-4000-8000-000000000001')
                page.locator('#project-revision').fill('1')
                page.locator('#plan-criteria').fill('Correct title\nIndependent check')
            else:
                page.locator('#plan-id').fill('00000000-0000-4000-8000-000000000002')
                page.locator('#task-title').fill('Normalize title')
                page.locator('#role-id').fill('EXP-01')
                page.locator('#task-criteria').fill('Correct title')
            page.get_by_role('button',name='İş isteğini gönder').click()
            expect(page.locator('#feedback')).to_contain_text('kaydedildi')
            assert calls[-1].get('project_id') is None
            assert page.locator('#session').input_value()==''
        report['mock_plan_and_task_forms_exact_scope'] = 'PASS'
        metadata = page.evaluate('JSON.parse(sessionStorage.getItem("aipof.last-command"))')
        page.reload(wait_until='networkidle')
        assert page.locator('#receipt-command').input_value() == metadata['command_id']
        def reread(route):
            body = route.request.post_data_json
            assert set(body) == {'operation','command_id','request_id'}
            route.fulfill(json={'semantics':'AUTHORIZED_FACT_NOT_CURRENT_STATE',
                'result':{'id':'fixture-objective'}, 'command_receipt':{
                    'command_id':body['command_id'], 'correlation_id':body['request_id'],
                    'state':'SUCCEEDED', 'result_ref':'fixture-objective'}})
        page.route('**/api/receipts',reread)
        page.locator('#session').fill('fixture-session-not-a-real-secret')
        page.get_by_role('button',name='Makbuzu yeniden oku').click()
        expect(page.locator('#receipt-feedback')).to_contain_text('Yeni komut gönderilmedi')
        assert page.locator('#session').input_value()==''
        assert len(calls) == 4  # one uncertain objective, one success, plan, task
        report['mock_receipt_reload_read_without_constructor_replay'] = 'PASS'
        assert not errors, errors
        report['browser_page_errors']=errors
        report['status']='PASS'
        browser.close()
    (EVIDENCE/'TASK_SCREEN_20261114_browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(report,evidence_directory=str(EVIDENCE)),indent=2))


if __name__=='__main__':main()
