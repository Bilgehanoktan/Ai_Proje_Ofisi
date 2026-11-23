"""MOD-011: Read-only Server-Sent Events (SSE) projection stream formatter for live office UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ProjectionEvent:
    sequence: int
    tenant_id: str
    event_type: str
    payload: Mapping[str, Any]


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
