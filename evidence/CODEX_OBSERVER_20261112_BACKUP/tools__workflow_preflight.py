"""Read-only owning-API checks. Does not import/execute the workflow or start DB/OS."""
import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_workflow(path=None):
    paths = ([ROOT / 'tools/disposable_e2e_workflow_trial.py',
              ROOT / 'company_os/workflow.py', ROOT / 'company_os/workflow_trust.py']
             if path is None or Path(path) == ROOT / 'tools/disposable_e2e_workflow_trial.py'
             else [Path(path)])
    findings = []
    checked = 0
    skipped = 0
    uninspectable = 0
    source_pins = {}
    for path in paths:
        raw = path.read_bytes()
        tree = ast.parse(raw.decode('utf-8-sig'))
        bindings = {}
        source_pins[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module_name = node.module or ''
            if node.level and path.parent.name == 'company_os':
                module_name = importlib.util.resolve_name('.'*node.level + module_name, 'company_os')
            if module_name != 'company_os' and not module_name.startswith('company_os.'):
                continue
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                findings.append(dict(file=str(path.relative_to(ROOT)), line=node.lineno,
                                     symbol=module_name, error=type(exc).__name__))
                continue
            file = Path(module.__file__)
            source_pins[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
            for alias in node.names:
                target = getattr(module, alias.name, None)
                if target is None:
                    findings.append(dict(file=str(path.relative_to(ROOT)), line=node.lineno,
                                         symbol=alias.name, error='MISSING_IMPORT'))
                else:
                    bindings[alias.asname or alias.name] = target
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = None
            symbol = None
            if isinstance(node.func, ast.Name):
                symbol = node.func.id
                target = bindings.get(symbol)
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                owner = bindings.get(node.func.value.id)
                if owner is not None:
                    symbol = node.func.value.id + '.' + node.func.attr
                    target = getattr(owner, node.func.attr, None)
            if target is None or not callable(target):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                skipped += 1
                continue
            try:
                signature = inspect.signature(target)
            except (ValueError, TypeError):
                uninspectable += 1
                continue
            checked += 1
            try:
                signature.bind(*[None for _ in node.args], **{k.arg: None for k in node.keywords})
            except TypeError as exc:
                findings.append(dict(file=str(path.relative_to(ROOT)), line=node.lineno,
                                     symbol=symbol, signature=str(signature), error=str(exc)))
    return dict(status='BLOCKED' if findings else 'SOURCE_CALLS_COMPATIBLE',
                scope='AST_SIGNATURE_ONLY_NOT_RUNTIME_ACCEPTANCE', checked_calls=checked,
                scanned_files=[str(p.relative_to(ROOT)) for p in paths],
                coverage_limits=['INSTANCE_METHODS_AND_DYNAMIC_ARGUMENT_VALUES_REQUIRE_BEHAVIOR_TESTS'],
                skipped_dynamic_calls=skipped, findings=findings, source_sha256=source_pins,
                uninspectable_calls=uninspectable,
                runtime_ready=False,
                runtime_blockers=['ENROLLED_ISOLATED_VERIFIER_REQUIRED',
                                  'TRUSTED_OWNER_CLOCK_AND_PROFILE_BINDINGS_NOT_VERIFIED'])


def main():
    result = check_workflow()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
