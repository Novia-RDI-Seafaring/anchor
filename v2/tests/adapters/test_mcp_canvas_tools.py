"""MCP canvas tool handlers — call directly without MCP transport."""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.adapters.mcp import handlers_canvas

from tests.fixtures.services import make_in_memory_services


def test_canvas_create_and_add_node():
    async def run():
        s = make_in_memory_services()
        await handlers_canvas.call_tool(s.workspace, "canvas_create_workspace", {"slug": "w1"})
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "label": "A", "node_type": "concept",
        })
        out = json.loads(body)
        assert out["event"]["type"] == "NodeAdded"

    asyncio.run(run())


def test_canvas_get_state_returns_nodes_and_edges():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_get_state", {"workspace_slug": "w1"})
        state = json.loads(body)
        assert state["nodes"][0]["id"] == "a"

    asyncio.run(run())


def test_canvas_remove_node_returns_cascade():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        await s.workspace.add_node("w1", id="b")
        await s.workspace.add_edge("w1", source="a", target="b")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_remove_node", {"workspace_slug": "w1", "id": "a"},
        )
        out = json.loads(body)
        assert [e["type"] for e in out["events"]] == ["EdgeRemoved", "NodeRemoved"]

    asyncio.run(run())


def test_unknown_tool_returns_json_error():
    async def run():
        s = make_in_memory_services()
        body = await handlers_canvas.call_tool(s.workspace, "canvas_bogus", {})
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_invalid_command_returns_json_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_edge", {
            "workspace_slug": "w1", "source": "ghost", "target": "ghost",
        })
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_tool_definitions_have_required_fields():
    defs = handlers_canvas.tool_definitions()
    assert all("name" in d and "description" in d and "inputSchema" in d for d in defs)
    names = {d["name"] for d in defs}
    assert "canvas_get_state" in names and "canvas_add_node" in names
    # New: organize-subtree tool ships in this PR.
    assert "canvas_organize_subtree" in names


def test_canvas_organize_subtree_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="r")
        await s.workspace.add_node("w1", id="a", x=-99, y=-99)
        await s.workspace.add_node("w1", id="b", x=99, y=99)
        await s.workspace.add_edge("w1", source="a", target="r")
        await s.workspace.add_edge("w1", source="b", target="r")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_organize_subtree",
            {"workspace_slug": "w1", "root_id": "r"},
        )
        out = json.loads(body)
        assert out["event_count"] == 2
        assert {m["id"] for m in out["moves"]} == {"a", "b"}

    asyncio.run(run())
