"""An intent records the first time an agent's inbox read returned it.

The asker cannot otherwise tell "nobody is listening" from "seen, still
working". Only agent reads count: the browser refetches the same routes to
draw the board.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from anchor.core.clock import FixedClock
from anchor.core.events.actor import Actor, actor_scope
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_intent_store import MemoryIntentStore
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from intent_layer.adapters.http import create_router
from intent_layer.adapters.mcp import call_tool
from intent_layer.models import Intent

HUMAN = Actor(kind="human", label="browser")
AGENT = Actor(kind="agent", label="claude-code")


async def _setup():
    bus = MemoryEventBus()
    clock = FixedClock(ts=100.0)
    ws = WorkspaceService(MemoryWorkspaceStore(), bus, clock=clock)
    svc = IntentService(MemoryIntentStore(), bus, now=clock.now, workspace=ws)
    await ws.create_workspace("cv")
    with actor_scope(HUMAN):
        intent = await svc.enqueue("user_request", origin_canvas_id="cv", payload={"text": "specs"})
    return svc, clock, intent


async def test_an_unread_intent_carries_no_seen():
    svc, _, intent = await _setup()
    await svc.list_pending()
    stored = await svc.get(intent.id)
    assert stored.seen_at is None and stored.seen_by is None
    assert "seen_at" not in stored.to_dict()


async def test_the_first_agent_read_is_recorded_and_kept():
    svc, clock, intent = await _setup()
    clock.advance(30.0)
    await svc.list_pending(reader=AGENT)
    clock.advance(370.0)
    await svc.list_pending(reader=Actor(kind="agent", label="other"))
    stored = await svc.get(intent.id)
    assert stored.seen_at == 130.0
    assert stored.seen_by == AGENT
    assert stored.to_dict()["seen_by"] == {"kind": "agent", "id": None, "label": "claude-code"}
    assert Intent.from_dict(stored.to_dict()).seen_at == 130.0


async def test_next_and_get_count_as_reads():
    svc, _, intent = await _setup()
    assert (await svc.next(reader=AGENT)).id == intent.id
    assert (await svc.get(intent.id)).seen_by == AGENT
    svc2, _, other = await _setup()
    await svc2.get(other.id, reader=AGENT)
    assert (await svc2.get(other.id)).seen_by == AGENT


async def test_a_resolved_intent_is_not_marked_seen():
    svc, _, intent = await _setup()
    await svc.resolve(intent.id, {"withdrawn": True})
    await svc.get(intent.id, reader=AGENT)
    assert (await svc.get(intent.id)).seen_at is None


def test_mcp_reads_are_agent_reads():
    svc, _, intent = asyncio.run(_setup())
    asyncio.run(call_tool(svc, "list_pending_intents", {}, actor=AGENT))
    got = json.loads(asyncio.run(call_tool(svc, "get_intent", {"id": intent.id}, actor=AGENT)))
    assert got["intent"]["seen_by"]["label"] == "claude-code"


def test_the_browser_refetch_is_not_a_read_but_an_agent_over_http_is():
    svc, _, intent = asyncio.run(_setup())
    app = FastAPI()
    app.include_router(create_router(lambda: svc, lambda: None, prefix="/api/intents"))
    client = TestClient(app)
    assert client.get("/api/intents").status_code == 200
    assert "seen_at" not in client.get(f"/api/intents/{intent.id}").json()["intent"]
    with actor_scope(AGENT):
        client.get("/api/intents")
    assert asyncio.run(svc.get(intent.id)).seen_by == AGENT
