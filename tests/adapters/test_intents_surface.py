"""Adapter parity for the agent intent queue (issue #148): the HTTP list /
enqueue / resolve endpoints + the intent_pending SSE signal, and the MCP
list_pending_intents / next_intent / resolve_intent tools -- advertised in the
core set and dispatching against the same project-level store.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest

from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import tiering
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project
from tests.fixtures.services import make_in_memory_services

_CLEAR = ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR")


# -- HTTP -------------------------------------------------------------------- #
def _client():
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
        intent_service=s.intents,
    )
    return TestClient(app), s


def test_http_enqueue_list_resolve():
    client, _s = _client()
    assert client.get("/api/intents").json() == {"intents": [], "count": 0}

    enq = client.post(
        "/api/intents",
        json={
            "kind": "drop_to_ingest",
            "origin_canvas_id": "canvas-a",
            "payload": {"slug": "pump"},
        },
    ).json()
    intent_id = enq["intent"]["id"]
    assert enq["intent"]["status"] == "pending"

    listed = client.get("/api/intents").json()
    assert listed["count"] == 1
    assert listed["intents"][0]["payload"]["slug"] == "pump"

    resolved = client.post(
        f"/api/intents/{intent_id}/resolve", json={"result": {"ok": True}}
    ).json()
    assert resolved["resolved"]["status"] == "resolved"
    assert resolved["resolved"]["result"] == {"ok": True}
    assert client.get("/api/intents").json()["count"] == 0


def test_http_cross_canvas_filter():
    client, _s = _client()
    client.post(
        "/api/intents",
        json={"kind": "drop_to_ingest", "origin_canvas_id": "a", "target": "b"},
    )
    assert client.get("/api/intents", params={"canvas": "a"}).json()["count"] == 1
    assert client.get("/api/intents", params={"canvas": "b"}).json()["count"] == 1
    assert client.get("/api/intents", params={"canvas": "z"}).json()["count"] == 0


def test_http_unknown_kind_rejected():
    client, _s = _client()
    out = client.post("/api/intents", json={"kind": "teleport"}).json()
    assert out["error"] == "unknown_kind"


def test_http_resolve_missing_is_not_found():
    client, _s = _client()
    out = client.post("/api/intents/ghost/resolve", json={}).json()
    assert out == {"error": "not_found", "id": "ghost"}


async def test_http_intent_pending_sse_emits_count():
    """Drive the SSE route generator directly: it emits an immediate snapshot
    ``intent_pending {count}`` then re-emits on each IntentPending bus event.

    Called as a coroutine (not via the threaded TestClient) so the long-lived
    stream is stepped one event at a time without blocking on keep-alives.
    """
    from types import SimpleNamespace

    from anchor.adapters.http.routers.intents import events as events_route

    s = make_in_memory_services()
    await s.intents.enqueue("drop_to_ingest", origin_canvas_id="a")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(bus=s.bus)),
        is_disconnected=lambda: _false(),
    )
    resp = await events_route(request, canvas=None, intents=s.intents)
    gen = resp.body_iterator

    # First yield is the immediate snapshot.
    first = await gen.__anext__()
    assert json.loads(first["data"]) == {"count": 1}

    # A second enqueue fires another IntentPending -> the stream re-emits.
    await s.intents.enqueue("drop_to_ingest", origin_canvas_id="a")
    second = await gen.__anext__()
    assert json.loads(second["data"]) == {"count": 2}
    await gen.aclose()


async def _false() -> bool:
    return False


# -- MCP --------------------------------------------------------------------- #
@pytest.fixture
def _home(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy")
    return tmp_path


async def _advertised(server) -> list[str]:
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    return sorted(t.name for t in result.root.tools)


async def _call(server, name: str, **arguments) -> str:
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(req)
    return result.root.content[0].text


def test_intent_tools_are_in_core():
    assert {"list_pending_intents", "next_intent", "resolve_intent"} <= tiering.CORE_NAMES


async def test_mcp_intent_tools_advertised_in_core(_home):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    server = build_mcp_server(router=ProjectRouter(env_arg="local"))
    names = await _advertised(server)
    for tool in ("list_pending_intents", "next_intent", "resolve_intent"):
        assert tool in names


async def test_mcp_intent_enqueue_list_resolve_dispatch(_home):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    router = ProjectRouter(env_arg="local")
    server = build_mcp_server(router=router)

    # Enqueue directly through the project's service (UI/HTTP normally does
    # this); the MCP tools are the agent's read/resolve half.
    bundle = router.bundle_for("pumps")
    intent = await bundle.intents.enqueue(
        "drop_to_ingest", origin_canvas_id="cv", payload={"slug": "pump"}
    )

    listed = json.loads(await _call(server, "list_pending_intents", project="pumps"))
    assert [i["id"] for i in listed["intents"]] == [intent.id]

    nxt = json.loads(await _call(server, "next_intent", project="pumps"))
    assert nxt["intent"]["id"] == intent.id

    resolved = json.loads(
        await _call(server, "resolve_intent", project="pumps", id=intent.id,
                    result={"produced_slug": "pump"})
    )
    assert resolved["resolved"]["status"] == "resolved"
    after = json.loads(await _call(server, "list_pending_intents", project="pumps"))
    assert after["intents"] == []


async def test_mcp_resolve_missing_intent(_home):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    server = build_mcp_server(router=ProjectRouter(env_arg="local"))
    out = json.loads(await _call(server, "resolve_intent", project="pumps", id="ghost"))
    assert out["error"] == "not_found"
