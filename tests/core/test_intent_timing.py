"""An intent's cost, from its thread and the activity log."""
from __future__ import annotations

from anchor.core.events.actor import Actor
from anchor.core.intents.intent import Intent, ThreadItem
from anchor.core.intents.timing import intent_timing

AGENT = Actor(kind="agent", label="claude")
HUMAN = Actor(kind="human", label="browser")


def _intent(created=1000.0, resolved=None, items=()):
    it = Intent(id="i1", kind="user_request", created_at=created, resolved_at=resolved)
    it.items = list(items)
    return it


def _item(type_, at, author=AGENT):
    return ThreadItem(type=type_, text="x", author=author, created_at=at)


def test_gaps_from_the_thread():
    it = _intent(
        resolved=1100.0,
        items=[
            _item("message", 1038.0),
            _item("suggestion", 1060.0),
            _item("question", 1061.0),
            _item("message", 1090.0, author=HUMAN),
        ],
    )
    t = intent_timing(it)
    assert t["pickup_s"] == 38.0
    assert t["first_suggestion_s"] == 60.0
    assert t["last_agent_item_s"] == 61.0
    assert t["resolved_s"] == 100.0
    assert t["agent_items"] == 3
    assert t["calls"] == 0 and t["calls_by_kind"] == {}


def test_nothing_yet_is_none_not_zero():
    t = intent_timing(_intent())
    assert t["pickup_s"] is None and t["first_suggestion_s"] is None and t["resolved_s"] is None


def test_calls_in_the_window_counted_by_kind_and_name():
    it = _intent(resolved=1100.0, items=[_item("message", 1038.0), _item("suggestion", 1060.0)])
    calls = [
        {"ts": 990.0, "kind": "http", "name": "GET /api/intents", "ms": 1},        # before the ask
        {"ts": 1005.0, "kind": "http", "name": "GET /api/workspaces/{}/state", "ms": 3},
        {"ts": 1010.0, "kind": "http", "name": "GET /api/documents/{}/regions", "ms": 9},
        {"ts": 1012.0, "kind": "http", "name": "GET /api/documents/{}/regions", "ms": 8},
        {"ts": 1038.0, "kind": "http", "name": "POST /api/intents/{}/items", "ms": 2, "intent": "i1"},
        {"ts": 1040.0, "kind": "mcp", "name": "intent_act", "ms": 20, "intent": "other"},  # another thread
        {"ts": 1060.0, "kind": "http", "name": "POST /api/intents/{}/act", "ms": 15, "intent": "i1"},
        {"ts": 1200.0, "kind": "http", "name": "GET /api/intents", "ms": 1},        # after resolution
    ]
    t = intent_timing(it, calls)
    assert t["calls"] == 5
    assert t["calls_by_kind"] == {"http": 5}
    assert t["calls_by_name"]["GET /api/documents/{}/regions"] == 2
    assert t["server_busy_ms"] == 37.0


def test_open_thread_window_ends_at_the_last_agent_item():
    it = _intent(items=[_item("message", 1038.0)])
    calls = [{"ts": 1030.0, "kind": "http", "name": "a", "ms": 1}, {"ts": 1500.0, "kind": "http", "name": "b", "ms": 1}]
    assert intent_timing(it, calls)["calls"] == 1
