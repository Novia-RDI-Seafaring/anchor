"""How long an intent took, and how many calls it cost.

The thread records when each item was posted; a host's activity log, when
it keeps one, records every adapter call with its duration. Together they
say where the time went between a reader sending an ask and the result
being on the board: how long before the agent showed up, how long it spent
reading before it wrote, how many calls that took. Measured, so the loop can be made faster
on evidence rather than impression.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from intent_layer.models import Intent


def _agent_items(intent: Intent) -> list[Any]:
    return sorted(
        (i for i in intent.items if i.author.kind == "agent" and i.created_at),
        key=lambda i: i.created_at,
    )


def intent_timing(intent: Intent, calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A timing summary for one intent.

    ``calls`` are activity entries (``{ts, kind, name, ms, intent?}``); those
    inside the intent's window are counted, by kind and by name. The window
    runs from the intent's creation to its resolution, or to its last agent
    item while it is open. An entry naming another intent is left out; one
    naming none is counted by time alone, which is right while one agent
    works one intent at a time and an estimate otherwise.
    """
    items = _agent_items(intent)
    created = intent.created_at
    first = items[0].created_at if items else None
    suggestions = [i for i in items if i.type == "suggestion"]
    first_suggestion = suggestions[0].created_at if suggestions else None
    last = items[-1].created_at if items else None
    end = intent.resolved_at or last
    window_end = end if end is not None else None

    counted: list[dict[str, Any]] = []
    for c in calls or []:
        ts = c.get("ts")
        if not isinstance(ts, (int, float)) or ts < created:
            continue
        if window_end is not None and ts > window_end + 1.0:
            continue
        other = c.get("intent")
        if other and other != intent.id:
            continue
        counted.append(c)
    by_kind = Counter(str(c.get("kind")) for c in counted)
    by_name = Counter(str(c.get("name")) for c in counted)
    busy_ms = sum(float(c.get("ms") or 0) for c in counted)

    def gap(a: float | None, b: float | None) -> float | None:
        return round(b - a, 1) if a is not None and b is not None else None

    return {
        "id": intent.id,
        "status": intent.status,
        "pickup_s": gap(created, first),
        "first_suggestion_s": gap(created, first_suggestion),
        "last_agent_item_s": gap(created, last),
        "resolved_s": gap(created, intent.resolved_at),
        "agent_items": len(items),
        "calls": len(counted),
        "calls_by_kind": dict(by_kind),
        "calls_by_name": dict(by_name.most_common()),
        "server_busy_ms": round(busy_ms, 1),
    }
