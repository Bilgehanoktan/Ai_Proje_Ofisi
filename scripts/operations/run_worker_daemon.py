"""CLI entry point for AutonomousWorkerDaemon under systemd."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "product/backend"))

from company_os.runtime.worker_daemon import AutonomousWorkerDaemon  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Proje Ofisi AutonomousWorkerDaemon.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    args = parser.parse_args()

    stop_event = threading.Event()

    def _handle_signal(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    def _idle_claim():
        # Production deployments wire enrolled Kernel claim port here.
        return None

    def _noop_exec(_task):
        raise RuntimeError("ENROLLED_EXECUTOR_PORT_REQUIRED")

    def _noop_verify(_task, _res):
        raise RuntimeError("ENROLLED_VERIFIER_PORT_REQUIRED")

    daemon = AutonomousWorkerDaemon(
        claim_next=_idle_claim,
        execute_task=_noop_exec,
        verify_task=_noop_verify,
        poll_interval_seconds=args.poll_interval,
        max_consecutive_errors=args.max_consecutive_errors,
        stop_event=stop_event,
    )
    print(json.dumps({"event": "WorkerDaemonStarted", "poll_interval": args.poll_interval}), flush=True)
    stats = daemon.run_forever(max_cycles=args.max_cycles)
    print(
        json.dumps(
            {
                "event": "WorkerDaemonStopped",
                "state": stats.state.value,
                "cycles": stats.cycles,
                "processed": stats.processed,
                "errors": stats.errors,
            }
        ),
        flush=True,
    )
    return 0 if stats.state.value == "STOPPED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
