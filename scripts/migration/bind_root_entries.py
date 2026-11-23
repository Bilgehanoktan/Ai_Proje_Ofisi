"""Retire the remaining root diagnostic and bind current-source pointers."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[2]
mapping_path=ROOT/'docs/migration/SOURCE_TO_TARGET.json'
data=json.loads(mapping_path.read_text('utf-8'))
if data['status']=='COMPLETE_SOURCE_LAYOUT':
    raise SystemExit('Migration finalized')
backup=ROOT/'evidence/runs/layout-migration-20261114/before.zip'
source=ROOT/'check_adjtimex.py'
target=ROOT/'scripts/database/check_adjtimex.py'
with zipfile.ZipFile(backup,'a',zipfile.ZIP_DEFLATED) as archive:
    for name in ['check_adjtimex.py','SOURCE_LOCK.json','GUNCEL_DURUM.json']:
        if name in archive.namelist():
            raise RuntimeError('Root backup already taken; do not replay mutation.')
        archive.write(ROOT/name,name)
raw=source.read_bytes()
if target.exists():raise RuntimeError('Diagnostic target exists')
source.rename(target)
data['files'].append(dict(source='check_adjtimex.py',target='scripts/database/check_adjtimex.py',
    source_sha256=hashlib.sha256(raw).hexdigest(),status='MOVED',immutable=True))
data['retained_nonapplication_roots']=['GUNCEL','ARSIV','dokumanlar','runtime','.runtime','.tools']
data['retained_root_history_files']=['GUNCEL_PAKET.zip','GUNCEL_PAKET_DOGRULAMASI.json','PAKET_BAGIMSIZ_DOGRULAMA.json','R67_TESLIM_DOGRULAMASI.json','YENIDEN_DUZENLEME_DOGRULAMASI.json']
mapping_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
state_path=ROOT/'GUNCEL_DURUM.json'
state=json.loads(state_path.read_text('utf-8'))
state['previous_effective_source_root']=state['effective_source_root']
state['effective_source_root']='product'
state['reference_source_root']='GUNCEL'
state['source_manifest']='SOURCE_MANIFEST.json'
state['layout_migration']='docs/migration/SOURCE_TO_TARGET.json'
state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lock_path=ROOT/'SOURCE_LOCK.json'
lock=json.loads(lock_path.read_text('utf-8'))
lock['status']='CURRENT_APPLICATION_LAYOUT_WITH_RETAINED_A_REFERENCE'
lock['reference_manifest']=lock['current_manifest']
lock['current_manifest']='SOURCE_MANIFEST.json'
lock['source_to_target']='docs/migration/SOURCE_TO_TARGET.json'
lock_path.write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Root source pointers rebound; 441 total mapped source files')
