"""Adapter parity for scoped-ask threads (#343): every thread operation over
HTTP, MCP, and the CLI, each attributing item ``author`` to its adapter's
actor and applying suggestions through the same core path."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import handlers_intents, tiering
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project
from tests.fixtures.services import make_in_memory_services

_CLEAR = ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR")

RENAME = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "Pump A"}}}]


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
    client = TestClient(app)
    client.post("/api/workspaces", json={"slug": "cv"})
    client.post("/api/workspaces/cv/nodes", json={"id": "n1", "label": "N1"})
    client.post("/api/workspaces/cv/nodes", json={"id": "n2", "label": "N2"})
    return client, s


def _ask(client):
    enq = client.post(
        "/api/intents",
        json={
            "kind": "user_request",
            "origin_canvas_id": "cv",
            "payload": {"text": "make sense of this"},
            "targets": [
                {"workspace_id": "cv", "node_id": "n1"},
                {"workspace_id": "cv", "node_id": "n2"},
            ],
        },
    )
    assert enq.status_code == 200, enq.text
    return enq.json()["intent"]


def test_http_create_thread_records_targets_and_base_version():
    client, _s = _client()
    intent = _ask(client)
    assert intent["targets"] == [
        {"workspace_id": "cv", "node_id": "n1"},
        {"workspace_id": "cv", "node_id": "n2"},
    ]
    assert intent["base_version"] == 2
    assert intent["items"] == []
    # base_version is server-recorded; a client-supplied one is ignored.
    other = client.post(
        "/api/intents",
        json={"kind": "user_request", "origin_canvas_id": "cv", "base_version": 99},
    ).json()["intent"]
    assert other["base_version"] == 2
    # Pending list + full read carry the thread fields.
    listed = next(
        i for i in client.get("/api/intents").json()["intents"] if i["id"] == intent["id"]
    )
    assert listed["targets"] == intent["targets"] and listed["base_version"] == 2
    full = client.get(f"/api/intents/{intent['id']}")
    assert full.status_code == 200
    assert full.json()["intent"]["id"] == intent["id"]
    assert client.get("/api/intents/ghost").status_code == 404
    bad = client.post("/api/intents", json={"kind": "user_request", "targets": [{"x": 1}]})
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_targets"


def test_http_add_item_author_is_request_actor_never_body():
    client, _s = _client()
    intent = _ask(client)
    rsp = client.post(
        f"/api/intents/{intent['id']}/items",
        json={"type": "message", "text": "hello", "author": {"kind": "agent", "label": "spoof"}},
    )
    assert rsp.status_code == 200, rsp.text
    item = rsp.json()["item"]
    assert item["author"] == {"kind": "human", "id": None, "label": "browser"}
    assert item["state"] is None
    # The #322 body `actor` override applies, as on canvas writes.
    rsp = client.post(
        f"/api/intents/{intent['id']}/items",
        json={
            "type": "suggestion", "text": "rename", "ops": RENAME,
            "actor": {"kind": "agent", "label": "claude"},
        },
    )
    assert rsp.status_code == 200
    assert rsp.json()["item"]["author"]["label"] == "claude"
    assert rsp.json()["item"]["state"] == "pending"
    assert [i["type"] for i in rsp.json()["intent"]["items"]] == ["message", "suggestion"]
    # Validation surfaces as 400 with a stable code.
    bad = client.post(f"/api/intents/{intent['id']}/items", json={"type": "suggestion", "ops": []})
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_ops"
    assert client.post("/api/intents/ghost/items", json={"type": "message", "text": "x"}).status_code == 404


def test_http_question_answer():
    client, _s = _client()
    intent = _ask(client)
    q = client.post(
        f"/api/intents/{intent['id']}/items",
        json={"type": "question", "text": "which?", "actor": {"kind": "agent"}},
    ).json()["item"]
    assert q["state"] == "open"
    ans = client.post(
        f"/api/intents/{intent['id']}/items/{q['id']}/answer", json={"text": "left"},
    )
    assert ans.status_code == 200
    assert ans.json()["item"]["state"] == "answered" and ans.json()["item"]["answer"] == "left"
    missing = client.post(f"/api/intents/{intent['id']}/items/ghost/answer", json={"text": "x"})
    assert missing.status_code == 404 and missing.json()["error"] == "item_not_found"


def test_http_apply_and_decline():
    client, s = _client()
    intent = _ask(client)
    sug = client.post(
        f"/api/intents/{intent['id']}/items",
        json={
            "type": "suggestion", "text": "add + link",
            "ops": [
                {"type": "NodeAdded", "payload": {"id": "c1", "node_type": "spec", "label": "S"}},
                {"type": "EdgeAdded", "payload": {"source": "n1", "target": "c1"}},
            ],
            "actor": {"kind": "agent", "label": "claude"},
        },
    ).json()["item"]
    rsp = client.post(f"/api/intents/{intent['id']}/items/{sug['id']}/apply")
    assert rsp.status_code == 200, rsp.text
    body = rsp.json()
    assert body["item"]["state"] == "applied"
    assert body["item"]["applied_versions"] == [3, 4]
    assert body["applied"]["versions"] == [3, 4]
    real = body["applied"]["id_map"]["c1"]
    assert [e["actor"]["label"] for e in body["applied"]["events"]] == ["claude", "claude"]
    assert all(e["causation_id"] == sug["id"] for e in body["applied"]["events"])
    state = client.get("/api/workspaces/cv/state").json()
    node = next(n for n in state["nodes"] if n["id"] == real)
    assert node["data"]["review"]["state"] == "accepted"
    assert node["data"]["review"]["by"] == {"kind": "human", "label": "browser"}
    # A second apply is a 409 state conflict.
    again = client.post(f"/api/intents/{intent['id']}/items/{sug['id']}/apply")
    assert again.status_code == 409 and again.json()["error"] == "not_pending"

    # A stale suggestion applies nothing and says which op failed.
    stale = client.post(
        f"/api/intents/{intent['id']}/items",
        json={
            "type": "suggestion", "text": "stale",
            "ops": [
                {"type": "NodeUpdated", "payload": {"id": "n2", "fields": {"label": "Z"}}},
                {"type": "NodeRemoved", "payload": {"id": "ghost"}},
            ],
        },
    ).json()["item"]
    version_before = client.get("/api/workspaces/cv/state").json()["version"]
    failed = client.post(f"/api/intents/{intent['id']}/items/{stale['id']}/apply")
    assert failed.status_code == 409
    assert failed.json()["error"] == "apply_failed"
    assert failed.json()["failing_index"] == 1 and failed.json()["stale"] is True
    assert client.get("/api/workspaces/cv/state").json()["version"] == version_before
    assert client.get(f"/api/intents/{intent['id']}").json()["intent"]["items"][-1]["state"] == "pending"

    # Decline with a comment records a message item by the request actor.
    dec = client.post(
        f"/api/intents/{intent['id']}/items/{stale['id']}/decline",
        json={"comment": "not this one"},
    )
    assert dec.status_code == 200
    assert dec.json()["item"]["state"] == "declined"
    last = dec.json()["intent"]["items"][-1]
    assert last["type"] == "message" and last["text"] == "not this one"
    assert last["author"]["kind"] == "human"


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


async def _call(server, name: str, **arguments) -> dict:
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(req)
    return json.loads(result.root.content[0].text)


def test_mcp_thread_tools_tiering():
    names = {d["name"] for d in handlers_intents.tool_definitions()}
    assert names == handlers_intents.TOOL_NAMES
    assert "intent_add_item" in tiering.CORE_NAMES
    gated = {"get_intent", "intent_ask", "intent_answer", "intent_apply", "intent_decline"}
    assert not (gated & tiering.CORE_NAMES)
    group = next(g for g in tiering._CAPABILITY_GROUPS if g["capability"] == "intent_threads")
    assert set(group["names"]) == gated


async def test_mcp_thread_round_trip(_home):
    create_env("local")
    create_project(env_mod.resolve_environment("local"), "pumps")
    router = ProjectRouter(env_arg="local")
    server = build_mcp_server(router=router)
    bundle = router.bundle_for("pumps")
    await bundle.workspace.create_workspace("cv")
    await bundle.workspace.add_node("cv", id="n1", label="N1", x=0, y=0)

    assert "intent_add_item" in await _advertised(server)

    asked = await _call(server, "intent_ask", project="pumps", workspace_slug="cv",
                        text="name this", targets=["n1"])
    intent = asked["intent"]
    assert intent["targets"] == [{"workspace_id": "cv", "node_id": "n1"}]
    assert intent["base_version"] == 1

    nxt = await _call(server, "next_intent", project="pumps")
    assert nxt["intent"]["targets"] == intent["targets"] and nxt["intent"]["items"] == []

    added = await _call(
        server, "intent_add_item", project="pumps", id=intent["id"],
        type="suggestion", text="rename", ops=RENAME,
    )
    item = added["item"]
    assert item["author"]["kind"] == "agent"  # the MCP client's actor, never the body
    assert item["state"] == "pending"

    q = (await _call(server, "intent_add_item", project="pumps", id=intent["id"],
                     type="question", text="sure?"))["item"]
    ans = await _call(server, "intent_answer", project="pumps", id=intent["id"],
                      item_id=q["id"], text="yes")
    assert ans["item"]["state"] == "answered"

    applied = await _call(server, "intent_apply", project="pumps", id=intent["id"],
                          item_id=item["id"])
    assert applied["item"]["state"] == "applied"
    assert applied["applied"]["versions"] == [2]
    assert applied["applied"]["events"][0]["causation_id"] == item["id"]
    state = await bundle.workspace.get_state("cv")
    assert state["nodes"][0]["label"] == "Pump A"

    full = await _call(server, "get_intent", project="pumps", id=intent["id"])
    assert [i["type"] for i in full["intent"]["items"]] == ["suggestion", "question"]

    second = (await _call(server, "intent_add_item", project="pumps", id=intent["id"],
                          type="suggestion", text="again", ops=RENAME))["item"]
    declined = await _call(server, "intent_decline", project="pumps", id=intent["id"],
                           item_id=second["id"], comment="no")
    assert declined["item"]["state"] == "declined"
    assert declined["intent"]["items"][-1]["text"] == "no"

    # Errors are structured, never tracebacks.
    missing = await _call(server, "get_intent", project="pumps", id="ghost")
    assert missing["error"] == "not_found"
    bad = await _call(server, "intent_add_item", project="pumps", id=intent["id"],
                      type="suggestion", text="x", ops=[])
    assert bad["error"] == "invalid_ops"
    stale = (await _call(server, "intent_add_item", project="pumps", id=intent["id"],
                         type="suggestion", text="stale",
                         ops=[{"type": "NodeRemoved", "payload": {"id": "ghost"}}]))["item"]
    failed = await _call(server, "intent_apply", project="pumps", id=intent["id"],
                         item_id=stale["id"])
    assert failed["error"] == "apply_failed" and failed["stale"] is True
    assert failed["failing_index"] == 0


# -- CLI --------------------------------------------------------------------- #
runner = CliRunner()


def _cli(args, data_dir):
    result = runner.invoke(cli_app, [*args, "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_cli_thread_round_trip(tmp_path):
    from anchor.adapters.cli.services import _build_canvas_runtime

    runtime = _build_canvas_runtime(tmp_path)
    asyncio.run(runtime.workspace.create_workspace("cv"))
    asyncio.run(runtime.workspace.add_node("cv", id="n1", label="N1", x=0, y=0))

    asked = _cli(["intent", "ask", "cv", "--text", "name this", "--target", "n1"], tmp_path)
    intent = asked["intent"]
    assert intent["targets"] == [{"workspace_id": "cv", "node_id": "n1"}]
    assert intent["base_version"] == 1

    shown = _cli(["intent", "show", intent["id"]], tmp_path)
    assert shown["intent"]["id"] == intent["id"]

    ops_file = tmp_path / "ops.json"
    ops_file.write_text(json.dumps(RENAME))
    added = _cli(
        ["intent", "--actor", "agent:claude", "add-item", intent["id"],
         "--type", "suggestion", "--text", "rename", "--ops", f"@{ops_file}"],
        tmp_path,
    )
    item = added["item"]
    assert item["author"] == {"kind": "agent", "id": None, "label": "claude"}
    assert item["state"] == "pending"

    q = _cli(["intent", "add-item", intent["id"], "--type", "question", "--text", "ok?"], tmp_path)["item"]
    assert q["author"]["label"] == "cli"
    ans = _cli(["intent", "answer", intent["id"], q["id"], "--text", "yes"], tmp_path)
    assert ans["item"]["state"] == "answered"

    applied = _cli(["intent", "apply", intent["id"], item["id"]], tmp_path)
    assert applied["item"]["state"] == "applied"
    assert applied["applied"]["versions"] == [2]
    ev = applied["applied"]["events"][0]
    assert ev["actor"]["label"] == "claude" and ev["causation_id"] == item["id"]
    state = asyncio.run(_build_canvas_runtime(tmp_path).workspace.get_state("cv"))
    assert state["nodes"][0]["label"] == "Pump A"

    second = _cli(
        ["intent", "add-item", intent["id"], "--type", "suggestion", "--text", "v2",
         "--ops", json.dumps(RENAME)],
        tmp_path,
    )["item"]
    declined = _cli(["intent", "decline", intent["id"], second["id"], "--comment", "no"], tmp_path)
    assert declined["item"]["state"] == "declined"
    assert declined["intent"]["items"][-1]["text"] == "no"

    # Failures exit 1 with a JSON error on stderr.
    bad = runner.invoke(
        cli_app,
        ["intent", "apply", intent["id"], second["id"], "--data-dir", str(tmp_path)],
    )
    assert bad.exit_code == 1
    assert "not_pending" in bad.output
    missing = runner.invoke(cli_app, ["intent", "show", "ghost", "--data-dir", str(tmp_path)])
    assert missing.exit_code == 1 and "not_found" in missing.output
