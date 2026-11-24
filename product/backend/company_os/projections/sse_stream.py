"""MOD-011: Read-only Server-Sent Events (SSE) projection stream formatter for live office UI."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from secrets import randbits
from threading import Lock
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ProjectionEvent:
    sequence: int
    tenant_id: str
    event_type: str
    payload: Mapping[str, Any]


class OfficeEventReplay:
    """Merge bounded source windows into one replay window for a local server."""

    def __init__(
        self,
        tenant_id: str,
        *,
        capacity: int = 512,
        unordered_sources: frozenset[str] = frozenset(),
    ) -> None:
        if capacity < 1:
            raise ValueError("Replay capacity must be positive")
        self._tenant_id = tenant_id
        self._latest = (1 + randbits(32)) << 20
        self._events: deque[ProjectionEvent] = deque(maxlen=capacity)
        self._source_cursors: dict[str, int] = {}
        self._unordered_sources = unordered_sources
        self._seen_source_ids: dict[str, set[int]] = {}
        self._lock = Lock()

    def _append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self._latest += 1
        self._events.append(
            ProjectionEvent(self._latest, self._tenant_id, event_type, payload)
        )

    def read(
        self,
        tenant_id: str,
        last_event_id: int,
        sources: Mapping[str, tuple[int, Sequence[ProjectionEvent]]],
    ) -> list[str]:
        if tenant_id != self._tenant_id:
            return []
        with self._lock:
            for source, (source_capacity, window) in sources.items():
                events = [event for event in window if event.tenant_id == tenant_id]
                previous = self._source_cursors.get(source, 0)
                if not events or events[-1].sequence < previous:
                    continue
                unordered = source in self._unordered_sources
                seen = self._seen_source_ids.get(source, set())
                if (
                    previous
                    and len(events) == source_capacity
                    and events[0].sequence > previous + 1
                ):
                    self._append("resync_required", {"reason": "source_window_advanced"})
                for event in events:
                    if (event.sequence not in seen if unordered else event.sequence > previous):
                        self._append(event.event_type, event.payload)
                if unordered:
                    # PostgreSQL identity allocation can precede the commit of a later ID.
                    self._seen_source_ids[source] = {event.sequence for event in events}
                self._source_cursors[source] = events[-1].sequence

            frames = []
            if last_event_id and self._events:
                oldest = self._events[0].sequence
                if not oldest - 1 <= last_event_id <= self._latest:
                    last_event_id = oldest - 1
                    frames.append(format_sse_frame(ProjectionEvent(
                        last_event_id, tenant_id, "resync_required",
                        {"reason": "cursor_outside_replay_window"},
                    )))
            return frames + stream_tenant_events(
                self._events, tenant_id=tenant_id, last_event_id=last_event_id
            )


def format_sse_frame(event: ProjectionEvent) -> str:
    """Format a single projection event as a standard SSE frame."""
    data = json.dumps(
        {
            "sequence": event.sequence,
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "payload": dict(event.payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"


def stream_tenant_events(
    events: Iterable[ProjectionEvent], *, tenant_id: str, last_event_id: int = 0
) -> list[str]:
    """Filter projection events strictly by tenant_id and cursor (last_event_id)."""
    if not tenant_id:
        raise ValueError("tenant_id is required")
    frames: list[str] = []
    for ev in events:
        if ev.tenant_id != tenant_id:
            continue
        if ev.sequence <= last_event_id:
            continue
        frames.append(format_sse_frame(ev))
    return frames
