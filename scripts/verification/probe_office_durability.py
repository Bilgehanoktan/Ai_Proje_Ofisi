"""Exercise local queue claims and the SSE cursor against a rotating fixture."""

import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from wsgiref.util import setup_testing_defaults


def run_multi_worker_and_persistent_sse_soak() -> dict:
    """Exercise concurrent AutonomousWorkerDaemon threads + persistent JSONL SSE replay across restart."""
    from company_os.api.http.app import make_wsgi_app
    from company_os.projections.sse_stream import OfficeEventReplay, ProjectionEvent
    from company_os.runtime.worker_daemon import AutonomousWorkerDaemon

    tenant_id = "t-soak-1"
    worker_count = 4
    sse_client_count = 8
    total_tasks = 480

    queue_lock = threading.Lock()
    pending_tasks = [
        {"task_id": f"soak-task-{idx:04d}", "seq": idx + 1}
        for idx in range(total_tasks)
    ]
    claim_cursor = 0
    emitted_lock = threading.Lock()
    emitted_events: list[ProjectionEvent] = []
    event_seq = 0

    def claim_next():
        nonlocal claim_cursor
        with queue_lock:
            if claim_cursor >= len(pending_tasks):
                return None
            item = pending_tasks[claim_cursor]
            claim_cursor += 1
            return item

    def execute_task(task: dict) -> dict:
        threading.Event().wait(0.0001)
        return {"task_id": task["task_id"], "status": "DONE"}

    def verify_task(task: dict, exec_res: dict) -> dict:
        return {"accepted": exec_res.get("status") == "DONE", "task_id": task["task_id"]}

    def on_event(kind: str, payload: dict) -> None:
        nonlocal event_seq
        if kind == "WorkerTaskAccepted":
            with emitted_lock:
                event_seq += 1
                emitted_events.append(
                    ProjectionEvent(event_seq, tenant_id, kind, dict(payload))
                )

    daemons = [
        AutonomousWorkerDaemon(
            claim_next=claim_next,
            execute_task=execute_task,
            verify_task=verify_task,
            on_event=on_event,
            poll_interval_seconds=0.0,
            max_consecutive_errors=3,
        )
        for _ in range(worker_count)
    ]
    start_barrier = Barrier(worker_count)

    def run_daemon_worker(daemon: AutonomousWorkerDaemon) -> int:
        start_barrier.wait(timeout=10)
        count = 0
        while daemon.run_once() is not None:
            count += 1
        return count

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(run_daemon_worker, d) for d in daemons]
        per_worker_counts = [f.result() for f in futures]

    claimed_ids = [
        summary.task_id
        for d in daemons
        for summary in d.stats.history
    ]
    total_accepted = sum(d.stats.accepted for d in daemons)
    total_errors = sum(d.stats.errors for d in daemons)
    workers_passed = (
        len(claimed_ids) == total_tasks
        and len(set(claimed_ids)) == total_tasks
        and total_accepted == total_tasks
        and total_errors == 0
        and len(emitted_events) == total_tasks
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "sse_soak_replay.jsonl"
        replay_first = OfficeEventReplay(
            tenant_id,
            capacity=total_tasks + 64,
            journal_path=journal_path,
        )
        half = total_tasks // 2
        first_half = emitted_events[:half]
        second_half = emitted_events[half:]

        app_first = make_wsgi_app(
            event_replay_provider=lambda t_id, cur: replay_first.read(
                t_id, cur, {"daemon": (total_tasks + 64, first_half)}
            )
        )

        def fetch_sse(wsgi_app, cursor: int) -> list[dict]:
            environ: dict = {}
            setup_testing_defaults(environ)
            environ["PATH_INFO"] = "/api/events"
            environ["QUERY_STRING"] = f"tenant_id={tenant_id}"
            environ["HTTP_LAST_EVENT_ID"] = str(cursor)
            statuses: list[str] = []
            resp = wsgi_app(environ, lambda status, _headers: statuses.append(status))
            try:
                body = b"".join(resp)
            finally:
                if hasattr(resp, "close"):
                    resp.close()
            if statuses != ["200 OK"]:
                raise RuntimeError(f"Unexpected SSE status: {statuses}")
            return [
                json.loads(line[6:])
                for line in body.splitlines()
                if line.startswith(b"data: ")
            ]

        first_frames = fetch_sse(app_first, 0)
        mid_cursor = first_frames[-1]["sequence"] if first_frames else 0

        # Simulate server restart by constructing a new OfficeEventReplay reading from journal_path
        replay_restarted = OfficeEventReplay(
            tenant_id,
            capacity=total_tasks + 64,
            journal_path=journal_path,
        )
        # Prime the second half into the restarted replay journal
        replay_restarted.read(
            tenant_id, mid_cursor, {"daemon": (total_tasks + 64, second_half)}
        )
        app_restarted = make_wsgi_app(
            event_replay_provider=lambda t_id, cur: replay_restarted.read(
                t_id, cur, {}
            )
        )

        client_barrier = Barrier(sse_client_count)

        def run_sse_client() -> tuple[int, int, bool]:
            client_barrier.wait(timeout=10)
            part1 = fetch_sse(app_restarted, 0)
            if len(part1) != total_tasks:
                return len(part1), 0, False
            resumed = fetch_sse(app_restarted, mid_cursor)
            no_dup = fetch_sse(app_restarted, resumed[-1]["sequence"]) == []
            task_ids = [f["payload"]["task_id"] for f in part1[:half]] + [
                f["payload"]["task_id"] for f in resumed
            ]
            ok = (
                len(resumed) == total_tasks - half
                and len(task_ids) == total_tasks
                and len(set(task_ids)) == total_tasks
                and no_dup
            )
            return len(part1), len(resumed), ok

        with ThreadPoolExecutor(max_workers=sse_client_count) as pool:
            client_results = list(pool.map(lambda _: run_sse_client(), range(sse_client_count)))

        journal_exists = journal_path.is_file() and journal_path.stat().st_size > 0

    sse_clients_passed = all(ok for _, _, ok in client_results) and journal_exists
    return {
        "passed": workers_passed and sse_clients_passed,
        "workers": worker_count,
        "per_worker_processed": per_worker_counts,
        "total_tasks": total_tasks,
        "unique_claimed": len(set(claimed_ids)),
        "accepted": total_accepted,
        "errors": total_errors,
        "sse_clients": sse_client_count,
        "journal_restart_recovery_passed": sse_clients_passed,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "product/backend"), str(root / "contracts/source/python")]
    from company_os.api.http.app import make_wsgi_app
    from company_os.projections.sse_stream import OfficeEventReplay, ProjectionEvent
    from company_os.runtime.live_task_runner import LiveOfficeTaskRunner

    workers = 8
    task_count = 1_600
    runner = LiveOfficeTaskRunner()
    submitted = {
        runner.submit_task(
            {"title": f"Queue task {number}", "goal": "Synthetic queue contention test"}
        )["task_id"]
        for number in range(task_count)
    }
    barrier = Barrier(workers)

    def claim_batch() -> list[str]:
        barrier.wait(timeout=10)
        return [task["task_id"] for task in iter(runner._claim_next, None)]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        batches = [pool.submit(claim_batch) for _ in range(workers)]
        claimed = [task_id for batch in batches for task_id in batch.result()]
    queue_passed = len(claimed) == task_count and set(claimed) == submitted

    window_size = 200
    replay = OfficeEventReplay("t1")
    events: list[ProjectionEvent] = []
    app = make_wsgi_app(
        event_replay_provider=lambda tenant_id, cursor: replay.read(
            tenant_id, cursor, {"fixture": (window_size, events)}
        )
    )

    def receive(cursor: int, tenant_id: str = "t1") -> list[dict]:
        environ: dict = {}
        setup_testing_defaults(environ)
        environ["PATH_INFO"] = "/api/events"
        environ["QUERY_STRING"] = f"tenant_id={tenant_id}"
        environ["HTTP_LAST_EVENT_ID"] = str(cursor)
        statuses: list[str] = []
        response = app(environ, lambda status, _headers: statuses.append(status))
        try:
            body = b"".join(response)
        finally:
            if hasattr(response, "close"):
                response.close()
        if statuses != ["200 OK"]:
            raise RuntimeError(f"Unexpected SSE response: {statuses}")
        return [
            json.loads(line[6:]) for line in body.splitlines() if line.startswith(b"data: ")
        ]

    reconnects = 999
    cursor = 0
    seen_source_ids: list[int] = []
    for offset in range(reconnects + 1):
        events[:] = [
            ProjectionEvent(index, "t1", "SyntheticEvent", {"source_id": index})
            for index in range(offset + 1, offset + window_size + 1)
        ]
        received = receive(cursor)
        if received:
            cursor = received[-1]["sequence"]
            seen_source_ids.extend(event["payload"]["source_id"] for event in received)

    expected_events = window_size + reconnects
    replay_passed = seen_source_ids == list(range(1, expected_events + 1))
    stale = receive(1)
    future = receive(cursor + 1)
    cursor_reset = all(
        frames and frames[0]["event_type"] == "resync_required"
        and frames[-1]["sequence"] == cursor
        for frames in (stale, future)
    )
    no_duplicate = receive(cursor) == []
    tenant_isolated = receive(0, "other") == []
    events[:] = [
        ProjectionEvent(index, "t1", "SyntheticEvent", {"source_id": index})
        for index in range(expected_events + 2, expected_events + window_size + 2)
    ]
    after_gap = receive(cursor)
    gap_signalled = (
        len(after_gap) == window_size + 1
        and after_gap[0]["event_type"] == "resync_required"
    )
    outbox_replay = OfficeEventReplay("t1", unordered_sources=frozenset({"outbox"}))
    high = ProjectionEvent(2, "t1", "SecondCommitted", {})
    low = ProjectionEvent(1, "t1", "FirstCommittedLate", {})
    first_read = outbox_replay.read("t1", 0, {"outbox": (12, [high])})
    outbox_cursor = int(first_read[0].splitlines()[0].removeprefix("id: "))
    late_read = outbox_replay.read("t1", outbox_cursor, {"outbox": (12, [low, high])})
    late_commit_replayed = len(late_read) == 1 and "event: FirstCommittedLate\n" in late_read[0]
    multi_worker_soak = run_multi_worker_and_persistent_sse_soak()
    print(json.dumps({
        "local_queue_claim": {
            "passed": queue_passed, "threads": workers, "submitted": task_count,
            "claimed": len(claimed), "unique_claims": len(set(claimed)),
        },
        "rotating_sse_fixture": {
            "passed": replay_passed, "reconnects": reconnects,
            "expected": expected_events, "received": len(seen_source_ids),
            "cursor_reset": cursor_reset, "source_gap_signalled": gap_signalled,
            "no_duplicate": no_duplicate, "tenant_isolated": tenant_isolated,
            "late_outbox_commit_replayed": late_commit_replayed,
        },
        "multi_worker_and_persistent_sse_soak": multi_worker_soak,
    }))
    return 0 if all((
        queue_passed, replay_passed, cursor_reset, gap_signalled, no_duplicate, tenant_isolated,
        late_commit_replayed, multi_worker_soak["passed"],
    )) else 1


if __name__ == "__main__":
    raise SystemExit(main())
