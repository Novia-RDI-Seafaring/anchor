"""The browser receives canvas and project updates over one SSE connection."""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.adapters.http.routers import realtime
from anchor.infra.presence import PresenceTracker
from tests.fixtures.services import make_in_memory_services


class Request:
    def __init__(self, tracker, tailers=None):
        self.app = SimpleNamespace(
            state=SimpleNamespace(presence=tracker, tailer_registry=tailers)
        )

    async def is_disconnected(self):
        return False


def stream(services, tracker, canvas="alpha", label="browser", tailers=None):
    return realtime._event_stream(
        Request(tracker, tailers), canvas, "human", label,
        services.bus, services.workspace, services.intents, services.doc_store,
    )


async def read(generator, name):
    async with asyncio.timeout(2):
        while True:
            event = await anext(generator)
            if event["event"] == name:
                return json.loads(event["data"])


async def initial(generator):
    snapshot = await read(generator, "snapshot")
    presence = await read(generator, "presence")
    count = await read(generator, "intent_pending")
    ingests = await read(generator, "ingests")
    return snapshot, presence, count, ingests


async def test_multiplexed_snapshots_preserve_monitor_presence_and_cleanup():
    services = make_in_memory_services()
    tracker = PresenceTracker()
    tailers = SimpleNamespace(ensure=AsyncMock())
    generator = stream(services, tracker, label="monitor", tailers=tailers)
    try:
        snapshot, presence, count, ingests = await initial(generator)
        assert snapshot["version"] == 0
        assert presence["workspace"] == "alpha"
        assert presence["you"] == presence["present"][0]["client_id"]
        assert presence["present"][0]["label"] == "monitor"
        assert count == {"count": 0}
        assert ingests == []
        tailers.ensure.assert_awaited_once_with("alpha", replay_after_version=0)
        assert len(services.bus._subscribers) == 1
    finally:
        await generator.aclose()
    assert tracker.roster("alpha") == []
    assert services.bus._subscribers == []


async def test_two_tabs_receive_only_their_canvas_and_all_project_notifications():
    services = make_in_memory_services()
    tracker = PresenceTracker()
    first = stream(services, tracker, "alpha")
    second = stream(services, tracker, "beta", "monitor")
    try:
        await initial(first)
        await initial(second)
        await services.workspace.add_node("beta", id="b", node_type="concept")
        intent = await services.intents.enqueue(
            "user_request", origin_canvas_id="beta", payload={"text": "private request"}
        )
        # The first stream skips beta's canvas patch, but receives its project signal.
        assert await read(first, "intent_pending") == {"count": 1}
        patch = await read(second, "patch")
        assert patch["workspace_id"] == "beta"
        assert await read(second, "intent_pending") == {"count": 1}
        await services.intents.resolve(intent.id, {"note": "handled"})
        assert await read(first, "intent_pending") == {"count": 0}
        assert await read(second, "intent_pending") == {"count": 0}
        assert len(services.bus._subscribers) == 2
    finally:
        await first.aclose()
        await second.aclose()
    assert services.bus._subscribers == []
    assert tracker.roster("alpha") == tracker.roster("beta") == []


async def test_activity_poll_observes_durable_writes_without_a_bus_event(monkeypatch):
    monkeypatch.setattr(realtime, "_POLL_SECONDS", 0.01)
    services = make_in_memory_services()
    tracker = PresenceTracker()
    generator = stream(services, tracker)
    try:
        await initial(generator)
        await services.doc_store.write_ingest_activity("pump", {
            "slug": "pump", "filename": "pump.pdf", "stage": "silver_extract",
            "current": 1, "total": 2, "status": "running",
            "started_at": time.time(), "updated_at": time.time(),
        })
        ingests = await read(generator, "ingests")
        assert ingests[0]["slug"] == "pump"
        assert ingests[0]["pct"] == 50
    finally:
        await generator.aclose()


async def test_project_only_stream_does_not_register_canvas_presence():
    services = make_in_memory_services()
    tracker = PresenceTracker()
    generator = stream(services, tracker, canvas=None)
    try:
        assert await read(generator, "intent_pending") == {"count": 0}
        assert await read(generator, "ingests") == []
        assert await services.workspace.list_workspaces() == []
    finally:
        await generator.aclose()
    assert services.bus._subscribers == []


async def test_snapshot_failure_releases_subscription():
    services = make_in_memory_services()
    services.workspace.get_state = AsyncMock(side_effect=RuntimeError("unavailable"))
    generator = stream(services, PresenceTracker())
    with pytest.raises(RuntimeError, match="unavailable"):
        await anext(generator)
    assert services.bus._subscribers == []


def test_realtime_route_validates_canvas_and_actor_before_streaming():
    services = make_in_memory_services()
    client = TestClient(build_app(
        workspace_service=services.workspace, ingest_service=services.ingest,
        doc_store=services.doc_store, bus=services.bus, intent_service=services.intents,
    ))
    assert client.get("/api/events?canvas=alpha&actor_kind=robot").status_code == 400
    assert client.get("/api/events?canvas=../outside").status_code == 400
