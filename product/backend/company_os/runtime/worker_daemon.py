"""MOD-002 / MOD-003: Fail-closed autonomous worker daemon loop.

Processes claimed tasks sequentially via injected claim, execute, and verify
ports without bypassing Kernel authority or falling back on errors. Halts
fail-closed when consecutive errors exceed the configured circuit-breaker limit.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class DaemonState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    HALTED_ON_ERRORS = "HALTED_ON_ERRORS"


@dataclass(frozen=True)
class TaskRunSummary:
    task_id: str
    outcome: str  # ACCEPTED | REJECTED | ERROR
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DaemonStats:
    cycles: int = 0
    processed: int = 0
    accepted: int = 0
    rejected: int = 0
    errors: int = 0
    consecutive_errors: int = 0
    state: DaemonState = DaemonState.IDLE
    history: list[TaskRunSummary] = field(default_factory=list)


class AutonomousWorkerDaemon:
    """Bounded or continuous worker loop with fail-closed circuit breaker."""

    def __init__(
        self,
        *,
        claim_next: Callable[[], dict[str, Any] | None],
        execute_task: Callable[[dict[str, Any]], dict[str, Any]],
        verify_task: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        poll_interval_seconds: float = 0.25,
        max_consecutive_errors: int = 3,
        stop_event: threading.Event | None = None,
    ) -> None:
        if poll_interval_seconds < 0:
            raise ValueError("POLL_INTERVAL_NEGATIVE")
        if max_consecutive_errors < 1:
            raise ValueError("MAX_CONSECUTIVE_ERRORS_MIN_1")
        self._claim_next = claim_next
        self._execute_task = execute_task
        self._verify_task = verify_task
        self._on_event = on_event
        self._poll_interval = poll_interval_seconds
        self._max_consecutive_errors = max_consecutive_errors
        self._stop_event = stop_event or threading.Event()
        self.stats = DaemonStats()

    def request_stop(self) -> None:
        self._stop_event.set()

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        if self._on_event is not None:
            self._on_event(kind, payload)

    def run_once(self) -> TaskRunSummary | None:
        """Run a single claim -> execute -> verify cycle."""
        self.stats.cycles += 1
        task = self._claim_next()
        if task is None:
            return None
        task_id = str(task.get("task_id") or task.get("id") or "")
        if not task_id:
            raise ValueError("CLAIMED_TASK_ID_REQUIRED")

        self.stats.processed += 1
        self._emit("WorkerTaskClaimed", {"task_id": task_id})
        try:
            exec_result = self._execute_task(task)
            verify_result = self._verify_task(task, exec_result)
            accepted = bool(verify_result.get("accepted"))
            outcome = "ACCEPTED" if accepted else "REJECTED"
            if accepted:
                self.stats.accepted += 1
            else:
                self.stats.rejected += 1
            self.stats.consecutive_errors = 0
            summary = TaskRunSummary(
                task_id=task_id,
                outcome=outcome,
                detail={"exec": exec_result, "verify": verify_result},
            )
            self.stats.history.append(summary)
            self._emit(f"WorkerTask{outcome.title()}", {"task_id": task_id, "outcome": outcome})
            return summary
        except Exception as exc:  # noqa: BLE001 — circuit breaker records and halts fail-closed
            self.stats.errors += 1
            self.stats.consecutive_errors += 1
            summary = TaskRunSummary(
                task_id=task_id,
                outcome="ERROR",
                detail={"error_type": type(exc).__name__, "message": str(exc)},
            )
            self.stats.history.append(summary)
            self._emit(
                "WorkerTaskError",
                {
                    "task_id": task_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc).strip()[:300],
                },
            )
            if self.stats.consecutive_errors >= self._max_consecutive_errors:
                self.stats.state = DaemonState.HALTED_ON_ERRORS
                self._stop_event.set()
            return summary

    def run_forever(self, *, max_cycles: int | None = None) -> DaemonStats:
        """Run until stop_event is set, circuit breaker trips, or max_cycles is reached."""
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("MAX_CYCLES_MIN_1")
        self.stats.state = DaemonState.RUNNING
        completed = 0
        while not self._stop_event.is_set():
            if max_cycles is not None and completed >= max_cycles:
                break
            summary = self.run_once()
            completed += 1
            if self.stats.state == DaemonState.HALTED_ON_ERRORS:
                break
            if summary is None and not self._stop_event.is_set():
                if max_cycles is not None and completed >= max_cycles:
                    break
                if self._poll_interval > 0:
                    self._stop_event.wait(self._poll_interval)
        if self.stats.state != DaemonState.HALTED_ON_ERRORS:
            self.stats.state = DaemonState.STOPPED
        return self.stats

    def health_snapshot(self) -> dict[str, Any]:
        """Return a structured observability snapshot for multi-node / production monitoring."""
        return {
            "state": self.stats.state.value,
            "healthy": self.stats.state != DaemonState.HALTED_ON_ERRORS,
            "cycles": self.stats.cycles,
            "processed": self.stats.processed,
            "accepted": self.stats.accepted,
            "rejected": self.stats.rejected,
            "errors": self.stats.errors,
            "consecutive_errors": self.stats.consecutive_errors,
            "max_consecutive_errors": self._max_consecutive_errors,
            "stop_requested": self._stop_event.is_set(),
        }
