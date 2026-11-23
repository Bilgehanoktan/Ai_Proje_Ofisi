"""Bind moved metadata; preserve historical evidence and authority records."""
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
mapping = json.loads((ROOT/'docs/migration/SOURCE_TO_TARGET.json').read_text('utf-8'))
if mapping['status'] == 'COMPLETE_SOURCE_LAYOUT':
    raise SystemExit('Migration finalized. Metadata rebinding is disabled.')
paths = {row['source']: row['target'] for row in mapping['files']}
paths.update({key.removeprefix('AiProjeOfisi/'): value for key, value in list(paths.items())})

# Oracle bytes are protocol pins, including line endings; never normalize them.
with zipfile.ZipFile(ROOT/'evidence/runs/layout-migration-20261114/before.zip') as archive:
    for row in mapping['files']:
        if '/fixtures/' in row['source']:
            (ROOT/row['target']).write_bytes(archive.read(row['source']))

assembly_path = ROOT/'database/assembly/assembly.json'
assembly = json.loads(assembly_path.read_text('utf-8'))
for row in assembly['order']:
    row['path'] = paths.get(row['path'], row['path'])
assembly_path.write_text(json.dumps(assembly, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

progress_path = ROOT/'progress/ILERLEME_TABLOSU.json'
progress = json.loads(progress_path.read_text('utf-8'))
for area in progress['areas']:
    area['evidence'] = [paths.get(path, path) for path in area['evidence']]
progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

# Active instructions/guides receive relative links to each relocated target.
# Historical handovers and raw evidence stay byte-exact and carry old paths.
active_docs = ['product/AGENTS.md', 'BAKIM_VE_DEGISIKLIK_REHBERI.md',
               'docs/developer-guides/TASK_SCREEN.md', 'docs/developer-guides/OFIS_TASARIM_KAYNAKLARI.md',
               'docs/operations/YEREL_VERITABANI.md', 'database/README.md', 'config/README.md']
import re
for name in active_docs:
    file = ROOT/name
    text = file.read_text('utf-8')
    def link(match):
        label, value = match.groups()
        if value.startswith(('http:', 'https:', '#')):
            return match.group()
        anchor = ''
        if '#' in value:
            value, anchor = value.split('#', 1)
            anchor = '#'+anchor
        # Original links were relative to application root or presentation/.
        old_parent = 'presentation/' if '/developer-guides/' in name else ('sql/' if name.startswith('database/') else 'config/' if name.startswith('config/') else '')
        old_value = os.path.normpath(old_parent+value).replace('\\', '/')
        target = paths.get(old_value)
        if target is None and old_value.startswith('../GUNCEL/'):
            target = old_value[3:]
        if target:
            return '['+label+']('+os.path.relpath(ROOT/target, file.parent).replace('\\','/')+anchor+')'
        return match.group()
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    file.write_text(text, encoding='utf-8')

# Non-Python control scripts and explicit legacy absolute tool paths.
for row in mapping['files']:
    file = ROOT/row['target']
    if row['immutable'] or '/fixtures/' in row['source'] or file.suffix not in {'.py', '.ps1'}:
        continue
    text = file.read_text('utf-8')
    for old, new in sorted(paths.items(), key=lambda pair: len(pair[0]), reverse=True):
        if old.startswith('AiProjeOfisi/'):
            text = text.replace('/'+old, '/'+new)
    # The two old trial scripts were also executable by absolute path.
    if file.name == 'disposable_session_check.py':
        text = text.replace('sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/\'docs/migration/SOURCE_TO_TARGET.json\').is_file())))',
            "ROOT=next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())\nsys.path[:0]=[str(ROOT),str(ROOT/'product/backend'),str(ROOT/'contracts/source/python'),str(ROOT/'verifier/src')]")
    file.write_text(text, encoding='utf-8')

# Source provenance pin now resolves from its new location. Trust declarations
# remain unchanged; moving a file does not authorize a new installation root.
pin_file = ROOT/'docs/architecture/architecture-source.json'
pin = json.loads(pin_file.read_text('utf-8'))
pin['source'] = '../../GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md'
pin['source'] = os.path.relpath(ROOT/'GUNCEL/dokumanlar/hedef-mimari-v1/PROJE_TASARIM_DOKUMANI.md', pin_file.parent).replace('\\','/')
pin_file.write_text(json.dumps(pin, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('SQL paths, progress evidence links, pinned fixture bytes and active guide links bound')
