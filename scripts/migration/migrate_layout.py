"""One-time, hash-checked source layout migration. Never touches runtime data."""
import argparse
import ast
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import tokenize
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / 'docs/migration/SOURCE_TO_TARGET.json'
BACKUP = ROOT / 'evidence/runs/layout-migration-20261114/before.zip'
GROUPS = {
    'kernel': ['command_host', 'kernel_adapters', 'constructors', 'execution_protocol', 'registry_preflight', 'registry_reader', 'session_provisioning'],
    'bootstrap': ['bootstrap_protocol', 'bootstrap_readback', 'bootstrap_transaction', 'bootstrap_window', 'clock_provisioning', 'consent_binding', 'provisioning'],
    'runtime/launch': ['launch_controller'],
    'runtime/observers': ['linux_observer', 'observer_profile'],
    'runtime/ipc': ['peer_rpc'],
    'runtime/supervisor': ['supervisor_service', 'supervisor_handles'],
    'engine': ['engine_bridge', 'reply_guard'],
    'broker': ['tool_broker', 'tool_executor'],
    'workspace': ['patch_pipeline'],
    'verification': ['runtime_verification'],
    'adapters/secrets': ['secret_adapter'],
    'composition': ['composition', 'workflow', 'workflow_trust'],
}
VERIFIER = {'verifier_runner', 'candidate_runner', 'bounded_candidate'}
HTTP = {'app', 'task_http', 'kernel_binding'}
TOOLS_DB = {'local_postgres', 'manage_local_postgres', 'native_bootstrap_acl_fixture',
            'native_session_guards_fixture', 'native_root_reader_fixture',
            'native_http_binding_fixture', 'probe_bootstrap_reader_pg',
            'disposable_session_check', 'disposable_compile_trial',
            'disposable_bootstrap_commit_trial', 'run_disposable_compile',
            'run_disposable_bootstrap_commit'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(relative):
    path = ROOT / relative
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError(f'Unsafe workspace path: {relative}')
    # Parent reparse points must not redirect a file outside the workspace.
    for parent in path.parents:
        if parent == ROOT:
            break
        if parent.exists() and parent.is_symlink():
            raise RuntimeError(f'Linked parent: {relative}')
    return path


def target(p):
    parts = p.parts
    name = p.name
    stem = p.stem
    base = parts[0]
    if base == 'company_os':
        if p.suffix == '.c':
            if name == 'r65_spawn_linux.c':
                return 'docs/migration/source-variants/' + name
            return 'product/backend/native/linux/' + name
        if stem in VERIFIER:
            return 'verifier/src/independent_verifier/' + name
        group = next((g for g, values in GROUPS.items() if stem in values), '')
        return 'product/backend/company_os/' + (group + '/' if group else '') + name
    if base == 'packages':
        if p.suffix == '.json':
            return 'contracts/generated/' + ('openapi/' if name == 'openapi.json' else 'jsonschema/') + name
        return 'contracts/source/python/' + p.as_posix()
    if base == 'native':
        return 'product/backend/native/linux/' + name
    if base == 'presentation':
        if stem in HTTP:
            return 'product/backend/company_os/api/http/' + name
        if stem in {'progress', 'preview_generator'}:
            return 'product/backend/company_os/projections/' + name
        if name == '__init__.py':
            return 'product/backend/company_os/api/http/__init__.py'
        if name == 'check_office_preview.py':
            return 'scripts/verification/' + name
        if p.suffix == '.md':
            return 'docs/developer-guides/' + name
        if p.suffix == '.png':
            return 'product/frontend/previews/' + name
        return 'product/frontend/' + name
    if base == 'sql':
        if name == 'assembly.json':
            return 'database/assembly/assembly.json'
        return 'database/' + ('sources/' if p.suffix == '.sql' else '') + name
    if base == 'tests':
        return p.as_posix()
    if base == 'tools':
        if name == '__init__.py':
            return 'scripts/__init__.py'
        return 'scripts/' + ('database/' if stem in TOOLS_DB else 'verification/') + name
    if base == 'fixtures':
        side = parts[2]
        return ('verifier/public-fixtures/mgt01/' if side == 'verifier' else 'tests/fixtures/producer/mgt01/') + name
    if base in {'evidence', 'config'}:
        return p.as_posix()
    if name.startswith('ILERLEME_') or name == 'UYGULAMA_DURUM_MATRISI.md':
        return 'progress/' + name
    if name == 'module-map.json':
        return 'catalog/sources/MODULE_MAP.json'
    if name == 'architecture-source.json':
        return 'docs/architecture/architecture-source.json'
    if name in {'AGENTS.md', 'BAKIM_VE_DEGISIKLIK_REHBERI.md'}:
        return 'product/' + name if name == 'AGENTS.md' else name
    if name == 'README.md':
        return 'docs/migration/PREVIOUS_APPLICATION_README.md'
    if name == 'PLAN.md':
        return 'docs/implementation-plan/PLAN.md'
    if name == 'YEREL_VERITABANI.md':
        return 'docs/operations/' + name
    if name.startswith('KALAN_ISLER'):
        return 'handover/history/' + name
    if name == 'requirements.txt':
        return 'product/backend/requirements.txt'
    if name == '.gitignore':
        return 'product/backend/.gitignore'
    return 'handover/history/' + name


def plan():
    if MAP.exists():
        raise RuntimeError('Mapping already exists; inspect it instead of overwriting.')
    rows = []
    ignored = []
    for p in sorted((ROOT / 'AiProjeOfisi').rglob('*')):
        if not p.is_file():
            continue
        if '__pycache__' in p.parts or p.suffix == '.pyc' or p.name == '.gitkeep':
            ignored.append(p.relative_to(ROOT).as_posix())
            continue
        if p.name.startswith('.env'):
            raise RuntimeError('Private environment file requires separate handling.')
        source = p.relative_to(ROOT).as_posix()
        destination = target(p.relative_to(ROOT / 'AiProjeOfisi'))
        checked(source)
        checked(destination)
        if (ROOT / destination).exists():
            raise RuntimeError(f'Target already exists: {destination}')
        rows.append(dict(source=source, target=destination, source_sha256=digest(p), status='PLANNED',
                         immutable=p.parts[len(ROOT.parts)+1] == 'evidence' or destination.startswith('handover/history/')))
    destinations = defaultdict(list)
    for row in rows:
        destinations[row['target']].append(row)
    for destination, items in destinations.items():
        if len(items) > 1 and len({r['source_sha256'] for r in items}) != 1:
            raise RuntimeError(f'Conflicting sources: {destination}')
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps(dict(canonical_workspace=str(ROOT), date='2026-11-14',
        status='PLANNED', retained_reference_roots=['GUNCEL', 'ARSIV'],
        excluded_generated_files=ignored, files=rows), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BACKUP, 'x', zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            archive.write(ROOT / row['source'], row['source'])
        for name in ['AGENTS.md', 'README.md', '.gitignore', 'PROTOTIP_BASLAT.ps1', 'PROTOTIP_BASLAT.bat']:
            archive.write(ROOT / name, name)
    with zipfile.ZipFile(BACKUP) as archive:
        assert archive.testzip() is None
        for row in rows:
            assert hashlib.sha256(archive.read(row['source'])).hexdigest() == row['source_sha256']
    print(json.dumps(dict(mapped_files=len(rows), excluded_generated=len(ignored), backup_verified=True)))


def move(section):
    data = json.loads(MAP.read_text('utf-8'))
    for row in data['files']:
        group = 'support' if not row['target'].startswith(('product/backend/', 'contracts/', 'verifier/', 'scripts/', 'tests/')) else 'sources'
        if group != section or row['status'] != 'PLANNED':
            continue
        src, dst = checked(row['source']), checked(row['target'])
        if digest(src) != row['source_sha256']:
            raise RuntimeError(f'Concurrent source change: {src}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if digest(dst) != row['source_sha256']:
                raise RuntimeError(f'Conflicting destination: {dst}')
            # Exact native C duplicate; canonical copy already verified.
            src.unlink()
            row['status'] = 'DEDUPLICATED'
        else:
            src.rename(dst)
            assert digest(dst) == row['source_sha256']
            row['status'] = 'MOVED'
        MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    data['status'] = 'SOURCES_MOVED_PENDING_BINDING_CHECKS'
    MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(section, 'hash-checked moves complete')


def module_name(path):
    p = Path(path)
    parts = list(p.with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def module_map(data):
    result = {}
    for row in data['files']:
        if not row['source'].endswith('.py') or row['immutable']:
            continue
        src = row['source'].removeprefix('AiProjeOfisi/')
        dst = row['target']
        for prefix in ['product/backend/', 'contracts/source/python/', 'verifier/src/']:
            if dst.startswith(prefix):
                dst = dst.removeprefix(prefix)
                break
        result[module_name(src)] = module_name(dst)
    return result


def rewrite_imports(text, old_module, modules):
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line))
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        original = node.module or ''
        if node.level:
            package = old_module.split('.')[:-node.level]
            original = '.'.join(package + ([original] if original else []))
        if original not in modules and not any(original + '.' + a.name in modules for a in node.names):
            continue
        groups = defaultdict(list)
        for alias in node.names:
            child = original + '.' + alias.name
            if child in modules:
                parent, name = modules[child].rsplit('.', 1)
            else:
                parent, name = modules.get(original, original), alias.name
            groups[parent].append(name + (' as ' + alias.asname if alias.asname else ''))
        indent = ' ' * node.col_offset
        new = ('\n'+indent).join('from '+parent+' import '+', '.join(names) for parent, names in groups.items())
        edits.append((offsets[node.lineno-1]+node.col_offset, offsets[node.end_lineno-1]+node.end_col_offset, new))
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start]+replacement+text[end:]
    # Also update import_module/patch strings and explicit dotted module names.
    pattern = re.compile(r'(?<![\w.])('+'|'.join(re.escape(k) for k in sorted(modules, key=len, reverse=True) if '.' in k)+r')(?![\w])')
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.STRING:
            token = token._replace(string=pattern.sub(lambda match: modules[match.group()], token.string))
        tokens.append(token)
    return tokenize.untokenize(tokens)


def bind():
    data = json.loads(MAP.read_text('utf-8'))
    modules = module_map(data)
    replacements = {}
    for row in data['files']:
        replacements[row['source']] = row['target']
        replacements[row['source'].removeprefix('AiProjeOfisi/')] = row['target']
    locator = "next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())"
    seen = set()
    for row in data['files']:
        path = ROOT / row['target']
        if row['immutable'] or path in seen or path.suffix != '.py':
            continue
        seen.add(path)
        with zipfile.ZipFile(BACKUP) as archive:
            text = archive.read(row['source']).decode('utf-8-sig').replace('\r\n', '\n')
        old_module = module_name(row['source'].removeprefix('AiProjeOfisi/'))
        text = rewrite_imports(text, old_module, modules)
        # Exact, quoted file references only, not protocol/SQL identifiers.
        for source, destination in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            for quote in ("'", '"'):
                text = text.replace(quote+source+quote, quote+destination+quote)
        text = text.replace("Path(__file__).resolve().parents[1]", locator)
        # Test roots remain workspace-relative after tests/ is moved as a unit.
        text = text.replace("ROOT / 'sql'", "ROOT / 'database/sources'").replace("ROOT/'sql'", "ROOT/'database/sources'")
        if row['target'].startswith('scripts/') and 'str(ROOT)' in text:
            text = text.replace('sys.path.insert(0, str(ROOT))',
                "sys.path[:0] = [str(ROOT), str(ROOT/'product/backend'), str(ROOT/'contracts/source/python'), str(ROOT/'verifier/src')]")
            text = text.replace('sys.path.insert(0,str(ROOT))',
                "sys.path[:0] = [str(ROOT),str(ROOT/'product/backend'),str(ROOT/'contracts/source/python'),str(ROOT/'verifier/src')]")
        path.write_text(text, encoding='utf-8')
    (ROOT/'docs/migration/MODULE_MOVES.json').write_text(json.dumps(modules, indent=2)+'\n', encoding='utf-8')
    # All existing Python source folders become real packages, without aliases.
    roots = ['product/backend/company_os', 'verifier/src/independent_verifier', 'scripts']
    for package_root in roots:
        base = ROOT / package_root
        for folder in [base] + [p for p in base.rglob('*') if p.is_dir() and '__pycache__' not in p.parts]:
            if any(folder.glob('*.py')) or any(folder.glob('*/')):
                init = folder / '__init__.py'
                if not init.exists():
                    init.write_text('', encoding='utf-8')
    print('imports and exact file references updated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('step', choices=['plan', 'support', 'sources', 'bind'])
    args = parser.parse_args()
    if MAP.exists() and json.loads(MAP.read_text('utf-8')).get('status') == 'COMPLETE_SOURCE_LAYOUT':
        raise SystemExit('Migration finalized. Do not replay mutation steps.')
    if args.step == 'plan':
        plan()
    elif args.step == 'bind':
        bind()
    else:
        move(args.step)
