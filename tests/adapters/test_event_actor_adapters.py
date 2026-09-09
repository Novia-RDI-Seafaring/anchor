"""Per-adapter actor defaults (#322): HTTP → human/browser, MCP → agent,
CLI → human/cli (or agent via --actor / ANCHOR_AGENT). Cascades → system."""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import handlers_canvas
from anchor.core.events.actor import Actor
from tests.fixtures.services import make_in_memory_services


def _http_client():
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app), s


# ── HTTP ────────────────────────────────────────────────────────────────────

def test_http_write_defaults_to_human_browser():
    client, _ = _http_client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post("/api/workspaces/w1/nodes", json={"id": "a", "label": "A"})
    assert rsp.status_code == 201
    actor = rsp.json()["event"]["actor"]
    assert actor == {"kind": "human", "id": None, "label": "browser"}


def test_http_body_actor_overrides_default():
    client, _ = _http_client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post(
        "/api/workspaces/w1/nodes",
        json={"id": "a", "actor": {"kind": "agent", "label": "copilot"}},
    )
    assert rsp.status_code == 201
    actor = rsp.json()["event"]["actor"]
    assert actor == {"kind": "agent", "id": None, "label": "copilot"}
    # PATCH override too, and the actor field must not leak into node fields.
    upd = client.patch(
        "/api/workspaces/w1/nodes/a",
        json={"label": "renamed", "actor": {"kind": "agent", "label": "copilot"}},
    )
    assert upd.status_code == 200
    assert upd.json()["event"]["actor"]["label"] == "copilot"
    assert "actor" not in upd.json()["event"]["payload"].get("fields", {})
    node = next(n for n in client.get("/api/workspaces/w1/state").json()["nodes"] if n["id"] == "a")
    assert node["label"] == "renamed"
    assert "actor" not in (node.get("data") or {})


def test_http_edge_writes_carry_actor():
    client, _ = _http_client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    client.post("/api/workspaces/w1/nodes", json={"id": "b"})
    rsp = client.post("/api/workspaces/w1/edges", json={"source": "a", "target": "b"})
    assert rsp.status_code == 201
    assert rsp.json()["event"]["actor"] == {"kind": "human", "id": None, "label": "browser"}


def test_http_remove_cascade_is_system_command_is_human():
    client, _ = _http_client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    client.post("/api/workspaces/w1/nodes", json={"id": "b"})
    client.post("/api/workspaces/w1/edges", json={"id": "e1", "source": "a", "target": "b"})
    rsp = client.delete("/api/workspaces/w1/nodes/a")
    assert rsp.status_code == 200
    by_type = {e["type"]: e for e in rsp.json()["events"]}
    assert by_type["EdgeRemoved"]["actor"] == {"kind": "system", "id": None, "label": None}
    assert by_type["NodeRemoved"]["actor"] == {"kind": "human", "id": None, "label": "browser"}


def test_http_sse_patch_serializes_actor():
    # The SSE stream sends `evt.model_dump_json()`; assert the wire JSON of
    # a published envelope carries the actor without the route re-shaping it.
    client, s = _http_client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})

    async def head():
        async for evt in s.bus.subscribe("w1"):
            return evt
        return None

    async def run():
        task = asyncio.create_task(head())
        await asyncio.sleep(0)
        client.post("/api/workspaces/w1/nodes", json={"id": "b"})
        evt = await asyncio.wait_for(task, timeout=1.0)
        wire = json.loads(evt.model_dump_json())
        assert wire["actor"] == {"kind": "human", "id": None, "label": "browser"}

    asyncio.run(run())


# ── MCP ─────────────────────────────────────────────────────────────────────

def test_mcp_write_defaults_to_generic_agent():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "label": "A",
        })
        actor = json.loads(body)["event"]["actor"]
        assert actor == {"kind": "agent", "id": None, "label": "mcp-agent"}

    asyncio.run(run())


def test_mcp_server_supplied_client_actor_wins():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_add_node",
            {"workspace_slug": "w1", "id": "a"},
            actor=Actor(kind="agent", label="claude-code"),
        )
        actor = json.loads(body)["event"]["actor"]
        assert actor == {"kind": "agent", "id": None, "label": "claude-code"}

    asyncio.run(run())


def test_mcp_remove_cascade_is_system_command_is_agent():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        await s.workspace.add_node("w1", id="b")
        await s.workspace.add_edge("w1", id="e1", source="a", target="b")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_remove_node", {"workspace_slug": "w1", "id": "a"},
        )
        by_type = {e["type"]: e for e in json.loads(body)["events"]}
        assert by_type["EdgeRemoved"]["actor"]["kind"] == "system"
        assert by_type["NodeRemoved"]["actor"] == {
            "kind": "agent", "id": None, "label": "mcp-agent",
        }

    asyncio.run(run())


# ── CLI ─────────────────────────────────────────────────────────────────────

def _last_event(data_dir, slug: str) -> dict:
    lines = (data_dir / "canvases" / slug / "events.jsonl").read_text().splitlines()
    return json.loads(lines[-1])


def test_cli_write_defaults_to_human_cli(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_AGENT", raising=False)
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(cli_app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(cli_app, ["canvas", "add-node", "w1", "concept", "--label", "A", "--data-dir", str(data_dir)])
    assert r.exit_code == 0, r.output
    assert _last_event(data_dir, "w1")["actor"] == {
        "kind": "human", "id": None, "label": "cli",
    }


def test_cli_actor_flag_sets_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_AGENT", raising=False)
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(cli_app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(cli_app, [
        "canvas", "--actor", "agent:claude-code",
        "add-node", "w1", "concept", "--data-dir", str(data_dir),
    ])
    assert r.exit_code == 0, r.output
    assert _last_event(data_dir, "w1")["actor"] == {
        "kind": "agent", "id": None, "label": "claude-code",
    }


def test_cli_anchor_agent_env_sets_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_AGENT", "claude-code")
    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(cli_app, ["canvas", "create", "w1", "--data-dir", str(data_dir)])
    r = runner.invoke(cli_app, ["canvas", "add-node", "w1", "concept", "--data-dir", str(data_dir)])
    assert r.exit_code == 0, r.output
    assert _last_event(data_dir, "w1")["actor"] == {
        "kind": "agent", "id": None, "label": "claude-code",
    }


def test_cli_rejects_unknown_actor_kind(tmp_path):
    r = CliRunner().invoke(cli_app, [
        "canvas", "--actor", "robot:c3po",
        "add-node", "w1", "concept", "--data-dir", str(tmp_path / "anchor-data"),
    ])
    assert r.exit_code == 2
