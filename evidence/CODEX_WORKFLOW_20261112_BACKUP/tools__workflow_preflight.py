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
    path = ROOT / 'tools/disposable_e2e_workflow_trial.py' if path is None else Path(path)
    raw = path.read_bytes()
    tree = ast.parse(raw.decode('utf-8-sig'))
    bindings = {}
    findings = []
    checked = 0
    skipped = 0
    source_pins = {str(path.relative_to(ROOT)): hashlib.sha256(raw).hexdigest()}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('company_os.'):
            try:
                module = importlib.import_module(node.module)
            except ImportError as exc:
                findings.append(dict(line=node.lineno, symbol=node.module, error=type(exc).__name__))
                continue
            file = Path(module.__file__)
            source_pins[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
            for alias in node.names:
                if not hasattr(module, alias.name):
                    findings.append(dict(line=node.lineno, symbol=alias.name, error='MISSING_IMPORT'))
                else:
                    bindings[alias.asname or alias.name] = getattr(module, alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        target = bindings.get(node.func.id)
        if target is None or not callable(target):
            continue
        if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
            skipped += 1
            continue
        try:
            signature = inspect.signature(target)
        except (ValueError, TypeError):
            skipped += 1
            continue
        checked += 1
        try:
            signature.bind(*[None for _ in node.args], **{k.arg: None for k in node.keywords})
        except TypeError as exc:
            findings.append(dict(line=node.lineno, symbol=node.func.id, signature=str(signature), error=str(exc)))
    return dict(status='BLOCKED' if findings else 'SOURCE_CALLS_COMPATIBLE',
                scope='AST_SIGNATURE_ONLY_NOT_RUNTIME_ACCEPTANCE', checked_calls=checked,
                skipped_dynamic_calls=skipped, findings=findings, source_sha256=source_pins,
                runtime_ready=False,
                runtime_blockers=['ENROLLED_ISOLATED_VERIFIER_REQUIRED',
                                  'TRUSTED_OWNER_CLOCK_AND_PROFILE_BINDINGS_NOT_VERIFIED'])


def main():
    result = check_workflow()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
