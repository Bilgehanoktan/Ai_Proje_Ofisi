"""Read-only CLI entry. Enrolled supervisor owns environment preparation.

No synthetic SQL bootstrap, DB startup, mount, role deletion or fallback worker.
Call disposable_e2e_workflow_trial.main with enrolled in-memory ports from the
trusted supervisor to execute; standalone CLI only reports missing inputs.
"""
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())
if str(ROOT) not in sys.path:
    sys.path[:0] = [str(ROOT), str(ROOT/'product/backend'), str(ROOT/'contracts/source/python'), str(ROOT/'verifier/src')]
from scripts.verification import disposable_e2e_workflow_trial as trial


def main():
    return trial.main()


if __name__ == '__main__':
    raise SystemExit(main())
