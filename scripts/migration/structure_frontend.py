"""Group existing HTML/JS assets by their approved frontend responsibility."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
mapping_path=ROOT/'docs/migration/SOURCE_TO_TARGET.json'
data=json.loads(mapping_path.read_text('utf-8'))
if data['status']=='COMPLETE_SOURCE_LAYOUT':
    raise SystemExit('Migration finalized')
moves={
    'tasks.html':'pages/tasks/index.html',
    'tasks.css':'pages/tasks/tasks.css',
    'tasks.js':'pages/tasks/tasks.js',
    'progress.css':'assets/progress.css',
    'dashboard.html':'office/scenes/dashboard.html',
    'office-preview.js':'office/engine/office-preview.js',
    'preview.html':'previews/preview.html',
    'status_dashboard.html':'previews/status_dashboard.html',
}
for old,new in moves.items():
    old='product/backend/company_os/projections/progress.css' if old=='progress.css' else 'product/frontend/'+old
    new='product/frontend/'+new
    source=ROOT/old
    target=ROOT/new
    if target.exists() and source.exists():
        raise RuntimeError('Target collision:'+new)
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.exists():
        source.rename(target)
    elif not target.is_file():
        raise RuntimeError('Neither source nor resumed target exists:'+old)
    for row in data['files']:
        if row['target']==old:
            row['target']=new
    mapping_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Existing frontend assets grouped by tasks, office and previews')
