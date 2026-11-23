"""Read-only current-layout integrity, import and migration coverage checks."""
import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import pkgutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = [ROOT, ROOT/'product/backend', ROOT/'contracts/source/python', ROOT/'verifier/src']
sys.path[:0] = [str(path) for path in SOURCE_ROOTS]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    mapping = json.loads((ROOT/'docs/migration/SOURCE_TO_TARGET.json').read_text('utf-8'))
    failures = []
    unique_targets = set()
    for row in mapping['files']:
        path = ROOT/row['target']
        unique_targets.add(row['target'])
        if not path.is_file():
            failures.append('MISSING_TARGET:'+row['target'])
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            failures.append('UNSAFE_TARGET:'+row['target'])
        if row.get('target_sha256') and sha(path) != row['target_sha256']:
            failures.append('TARGET_CHANGED:'+row['target'])
        if row['immutable'] and sha(path) != row['source_sha256']:
            failures.append('HISTORICAL_EVIDENCE_CHANGED:'+row['target'])
        if (ROOT/row['source']).exists():
            failures.append('OLD_SOURCE_STILL_ACTIVE:'+row['source'])
    with zipfile.ZipFile(ROOT/mapping['rollback_archive']) as archive:
        if archive.testzip() is not None:
            failures.append('ROLLBACK_ARCHIVE_CRC')
        for row in mapping['files']:
            if hashlib.sha256(archive.read(row['source'])).hexdigest() != row['source_sha256']:
                failures.append('ROLLBACK_SOURCE_HASH:'+row['source'])
    manifest = json.loads((ROOT/'SOURCE_MANIFEST.json').read_text('utf-8'))
    for name, expected in manifest['files'].items():
        path = ROOT/name
        if not path.is_file() or sha(path) != expected:
            failures.append('MANIFEST_MISMATCH:'+name)
    for prefix in manifest['source_directories']:
        for path in (ROOT/prefix).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                if path.relative_to(ROOT).as_posix() not in manifest['files']:
                    failures.append('UNMANIFESTED_SOURCE:'+path.relative_to(ROOT).as_posix())
    imports = 0
    for package in ('company_os', 'packages.contracts', 'independent_verifier'):
        module = importlib.import_module(package)
        for item in pkgutil.walk_packages(module.__path__, module.__name__+'.'):
            # Standalone candidate runner has a __main__ guard; import is inert.
            importlib.import_module(item.name)
            imports += 1
    syntax = 0
    for directory in ['product/backend', 'contracts/source/python', 'verifier/src', 'scripts', 'tests']:
        for path in (ROOT/directory).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            tree = ast.parse(path.read_text('utf-8-sig'), filename=str(path))
            syntax += 1
            if directory in ['product/backend', 'contracts/source/python', 'verifier/src']:
                for node in ast.walk(tree):
                    names = [node.module or ''] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names] if isinstance(node, ast.Import) else []
                    if any(name.split('.')[0] in {'AiProjeOfisi', 'GUNCEL', 'ARSIV', 'compatibility'} for name in names):
                        failures.append('LEGACY_RUNTIME_IMPORT:'+str(path.relative_to(ROOT)))
    return dict(status='PASS' if not failures else 'FAIL', mapped_files=len(mapping['files']),
        unique_targets=len(unique_targets), manifest_files=len(manifest['files']),
        imported_modules=imports, parsed_python_files=syntax, failures=failures,
        scope='LAYOUT_SOURCE_INTEGRITY_NOT_RUNTIME_ACCEPTANCE', G0='OPEN', first13='0/13')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    result = verify()
    raw = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    if args.output:
        destination = Path(args.output).resolve()
        if not destination.is_relative_to((ROOT/'evidence/runs').resolve()):
            raise ValueError('EVIDENCE_OUTPUT_OUTSIDE_RUNS')
        destination.write_text(raw, encoding='utf-8')
    print(raw)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
