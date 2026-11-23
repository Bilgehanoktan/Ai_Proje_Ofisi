from playwright.sync_api import sync_playwright
from pathlib import Path
with sync_playwright() as p:
 print('Launching browser',flush=True)
 b=p.chromium.launch(headless=True,timeout=12000)
 page=b.new_page(viewport={'width':1600,'height':1000})
 page.goto(Path('product/frontend/previews/preview.html').resolve().as_uri(),timeout=12000)
 page.wait_for_load_state('networkidle',timeout=12000)
 assert page.locator('.hotspot').count()==4
 page.get_by_role('tab',name='Ajanlar',exact=True).click()
 page.locator('#role-list button').filter(has_text='Research').click()
 assert page.locator('#role-title').inner_text()=='Research'
 page.get_by_role('tab',name='Aktivite',exact=True).click()
 assert page.locator('#activity').is_visible()
 page.get_by_role('button',name='Yakınlaştır',exact=True).click()
 assert page.locator('#zoom-reset').inner_text()=='125%'
 page.get_by_role('button',name='Büyüt',exact=True).click()
 assert 'expanded' in page.locator('#office').get_attribute('class')
 page.keyboard.press('Escape')
 assert 'expanded' not in page.locator('#office').get_attribute('class')
 page.screenshot(path='evidence/runs/layout-migration-20261114/office_desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path='evidence/runs/layout-migration-20261114/office_mobile.png',full_page=True)
 b.close()
 print('PASS: roles, tabs, selection, zoom, expand, Escape, mobile overflow',flush=True)
