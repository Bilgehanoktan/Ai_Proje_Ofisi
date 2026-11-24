"""Exercise local queue claims and the SSE cursor against a rotating fixture."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from wsgiref.util import setup_testing_defaults


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
    }))
    return 0 if all((
        queue_passed, replay_passed, cursor_reset, gap_signalled, no_duplicate, tenant_isolated,
        late_commit_replayed,
    )) else 1


if __name__ == "__main__":
    raise SystemExit(main())
