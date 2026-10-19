"""An unnamed inbox read is scoped to the canvas open in the browser."""
from __future__ import annotations

import asyncio
import json

from anchor.adapters.mcp.server import _scoped_inbox
from anchor.infra.presence import PresenceTracker


def test_viewing_lists_canvases_a_person_has_open_latest_first():
    now = [0.0]
    tracker = PresenceTracker(clock=lambda: now[0])
    tracker.connect("pumps")
    now[0] = 5.0
    tracker.connect("test")
    tracker.connect("pumps", kind="agent", label="monitor-bot")
    assert tracker.viewing() == ["test", "pumps"]
    tracker.close()


def test_agents_alone_are_not_viewing():
    tracker = PresenceTracker(clock=lambda: 0.0)
    tracker.connect("pumps", kind="agent", label="bot")
    assert tracker.viewing() == []
    tracker.close()


class _Intent:
    def __init__(self, id, canvas):
        self.id, self.origin_canvas_id, self.target = id, canvas, None


class _Intents:
    async def list_pending(self):
        return [_Intent("a", "pumps"), _Intent("b", "test"), _Intent("c", "test")]


def test_scoped_inbox_names_the_canvas_and_counts_the_rest():
    text = json.dumps({"intents": [{"id": "a"}]})
    out = json.loads(asyncio.run(_scoped_inbox(_Intents(), "pumps", text)))
    assert out["canvas"] == "pumps"
    assert out["intents"] == [{"id": "a"}]
    assert out["elsewhere"] == {"test": 2}
    assert "open in the browser" in out["why"]
