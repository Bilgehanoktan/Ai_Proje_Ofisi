"""Finalize the authorized migration once; do not use as a release updater."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write(name, text):
    path = ROOT/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip()+'\n', encoding='utf-8')


def main():
    map_path = ROOT/'docs/migration/SOURCE_TO_TARGET.json'
    mapping = json.loads(map_path.read_text('utf-8'))
    if mapping['status'] == 'COMPLETE_SOURCE_LAYOUT':
        raise RuntimeError('Migration already finalized; do not silently refresh integrity pins.')
    for row in mapping['files']:
        target = ROOT/row['target']
        assert target.is_file(), row['target']
        assert not (ROOT/row['source']).exists(), row['source']
        row['target_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        if row['immutable']:
            assert row['target_sha256'] == row['source_sha256'], row['target']
        row['content_changed_for_binding'] = row['target_sha256'] != row['source_sha256']
        row['status'] = 'DEDUPLICATED_VERIFIED' if row['status'] == 'DEDUPLICATED' else 'MOVED_VERIFIED'
    mapping['status'] = 'COMPLETE_SOURCE_LAYOUT'
    mapping['rollback_archive'] = 'evidence/runs/layout-migration-20261114/before.zip'
    mapping['acceptance'] = dict(G0='OPEN', first13='0/13', runtime='NOT_ACCEPTED')
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    prefixes = ['product', 'contracts', 'database', 'workers', 'verifier', 'integrations', 'tests',
                'infrastructure', 'config', 'scripts', 'docs', 'catalog', 'decisions', 'handover',
                'progress', 'security', 'releases', 'examples', '.github']
    files = {}
    for prefix in prefixes:
        directory = ROOT/prefix
        for path in directory.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            if path.name.startswith('.env') and path.name != '.env.example':
                raise RuntimeError('Private environment file must not enter source manifest')
            files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ['README.md', 'AGENTS.md', '.gitignore', '.gitattributes', '.env.example',
                 'pyproject.toml', 'DOGRULA.bat', 'PROTOTIP_BASLAT.bat', 'PROTOTIP_BASLAT.ps1',
                 'CHANGELOG.md', 'ROADMAP.md', 'SECURITY.md', 'CONTRIBUTING.md', 'BAKIM_VE_DEGISIKLIK_REHBERI.md',
                 'GUNCEL_DURUM.json', 'SOURCE_LOCK.json']:
        files[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    manifest = dict(version=1, canonical_workspace=str(ROOT), date='2026-11-14',
        scope='CURRENT_APPLICATION_LAYOUT_ONLY_NOT_GUNCEL_REFERENCE_OR_RUNTIME_DATA',
        excluded=['GUNCEL', 'ARSIV', '.runtime', 'runtime', '.tools', '.ai-brain-outbox', 'evidence/runs', '__pycache__', 'SOURCE_MANIFEST.json'],
        policy='Source changes require an explicit reviewed manifest refresh; verification never rewrites pins.',
        source_directories=prefixes,
        files=dict(sorted(files.items())))
    write('SOURCE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(dict(status=mapping['status'], manifest_files=len(files))))


if __name__ == '__main__':
    main()
