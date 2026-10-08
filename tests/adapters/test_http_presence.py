"""HTTP presence surface — GET /presence + the SSE presence feed wiring."""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.adapters.http.routers import sse
from anchor.infra.presence import PresenceTracker
from tests.fixtures.services import make_in_memory_services


def _app():
    s = make_in_memory_services()
    return build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    ), s


def test_presence_endpoint_empty_roster():
    app, _ = _app()
    client = TestClient(app)
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.get("/api/workspaces/w1/presence")
    assert rsp.status_code == 200
    assert rsp.json() == {"workspace": "w1", "present": []}


def test_presence_endpoint_unknown_workspace_is_empty():
    # Workspaces auto-create on first touch (same as the SSE stream), so an
    # unknown slug is simply a canvas nobody is on.
    app, _ = _app()
    client = TestClient(app)
    rsp = client.get("/api/workspaces/nope/presence")
    assert rsp.status_code == 200
    assert rsp.json() == {"workspace": "nope", "present": []}


def test_agent_write_shows_in_presence_roster():
    # End to end: an HTTP write carrying an agent actor is published on the
    # bus, the startup presence feed notes it, and GET /presence lists the
    # agent as present via "writes".
    app, _ = _app()
    with TestClient(app) as client:  # context manager runs startup/shutdown
        client.post("/api/workspaces", json={"slug": "w1"})
        client.post(
            "/api/workspaces/w1/nodes",
            json={"id": "a", "actor": {"kind": "agent", "label": "claude-code"}},
        )
        # The feed task consumes the bus on the app's loop; give it a few
        # scheduler turns before asserting (no fixed sleeps beyond polling).
        present: list = []
        for _ in range(50):
            rsp = client.get("/api/workspaces/w1/presence")
            assert rsp.status_code == 200
            present = rsp.json()["present"]
            if present:
                break
            time.sleep(0.01)
        assert len(present) == 1
        assert present[0]["kind"] == "agent"
        assert present[0]["label"] == "claude-code"
        assert present[0]["via"] == "writes"


def test_human_write_does_not_show_in_presence_roster():
    app, _ = _app()
    with TestClient(app) as client:
        client.post("/api/workspaces", json={"slug": "w1"})
        client.post("/api/workspaces/w1/nodes", json={"id": "a"})  # human/browser
        assert client.get("/api/workspaces/w1/presence").json()["present"] == []


# ── The stream generator itself ─────────────────────────────────────────────
#
# An infinite SSE response can't be cleanly consumed through TestClient, so
# these tests drive the module-level `_event_stream` generator directly with
# a fake Request that carries the app state (tracker, no tailer).


class _FakeRequest:
    def __init__(self, tracker):
        self.app = SimpleNamespace(
            state=SimpleNamespace(tailer_registry=None, presence=tracker)
        )

    async def is_disconnected(self) -> bool:
        return False


def _stream(tracker, s, label: str, kind: str = "human"):
    return sse._event_stream(
        _FakeRequest(tracker), "w1", kind, label, s.bus, s.workspace
    )


async def _read(gen, expected: str) -> dict:
    msg = await asyncio.wait_for(anext(gen), timeout=2.0)
    assert msg["event"] == expected, msg
    return json.loads(msg["data"])


async def test_sse_stream_sends_snapshot_then_roster_with_you_marker():
    s = make_in_memory_services()
    tracker = PresenceTracker()
    gen = _stream(tracker, s, "monitor")
    try:
        await _read(gen, "snapshot")
        presence = await _read(gen, "presence")
        assert presence["workspace"] == "w1"
        assert len(presence["present"]) == 1
        entry = presence["present"][0]
        assert entry["kind"] == "human"
        assert entry["label"] == "monitor"
        assert entry["via"] == "sse"
        assert presence["you"] == entry["client_id"]
    finally:
        await gen.aclose()
    # Closing the stream leaves the roster (disconnect ran in finally).
    assert tracker.roster("w1") == []


async def test_sse_stream_broadcasts_join_and_leave():
    s = make_in_memory_services()
    tracker = PresenceTracker()
    first = _stream(tracker, s, "browser")
    try:
        await _read(first, "snapshot")
        await _read(first, "presence")

        # A second viewer joins: the first stream gets the two-entry roster.
        second = _stream(tracker, s, "monitor")
        try:
            await _read(second, "snapshot")
            you2 = await _read(second, "presence")
            assert len(you2["present"]) == 2
            joined = await _read(first, "presence")
            assert {e["label"] for e in joined["present"]} == {"browser", "monitor"}
        finally:
            await second.aclose()

        # ... and the shrunken roster when it leaves.
        left = await _read(first, "presence")
        assert [e["label"] for e in left["present"]] == ["browser"]
    finally:
        await first.aclose()


def test_sse_rejects_unknown_actor_kind():
    app, _ = _app()
    client = TestClient(app)
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.get("/api/workspaces/w1/events?actor_kind=robot")
    assert rsp.status_code == 400
    assert "actor_kind" in rsp.json()["detail"]
