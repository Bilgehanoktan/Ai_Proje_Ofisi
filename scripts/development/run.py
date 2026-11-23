"""Workspace launcher: only current product sources, never legacy trees."""

import argparse
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = [
    ROOT,
    ROOT / "product/backend",
    ROOT / "contracts/source/python",
    ROOT / "verifier/src",
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI Proje Ofisi yerel araçları")
    parser.add_argument(
        "action",
        choices=["tasks", "kernel", "doctor", "progress", "preview", "verify", "preflight"],
    )
    args, remaining = parser.parse_known_args(argv)
    sys.path[:0] = [str(path) for path in SOURCE_ROOTS]
    modules = {
        "tasks": "company_os.api.http.task_http",
        "kernel": "company_os.api.http.kernel_binding",
        "doctor": "scripts.database.audit_local_state",
        "progress": "company_os.projections.progress",
        "preview": "company_os.projections.preview_generator",
        "verify": "scripts.verification.verify_source",
        "preflight": "scripts.verification.workflow_preflight",
    }
    sys.argv = [modules[args.action], *remaining]
    runpy.run_module(modules[args.action], run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
