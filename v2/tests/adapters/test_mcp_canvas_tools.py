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


def test_tool_definitions_include_align_and_distribute():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_align" in names
    assert "canvas_distribute" in names


def test_canvas_align_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0,  y=0,  width=100, height=100)
        await s.workspace.add_node("w1", id="b", x=50, y=30, width=100, height=100)
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_align",
            {"workspace_slug": "w1", "ids": ["a", "b"], "anchor": "top"},
        )
        out = json.loads(body)
        assert out["event_count"] == 1
        assert {m["id"] for m in out["moves"]} == {"b"}

    asyncio.run(run())


def test_canvas_distribute_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0,   y=0, width=100, height=100)
        await s.workspace.add_node("w1", id="b", x=120, y=0, width=100, height=100)
        await s.workspace.add_node("w1", id="c", x=300, y=0, width=100, height=100)
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_distribute",
            {"workspace_slug": "w1", "ids": ["a", "b", "c"], "axis": "horizontal"},
        )
        out = json.loads(body)
        assert out["event_count"] == 1
        assert {m["id"] for m in out["moves"]} == {"b"}

    asyncio.run(run())


def test_canvas_align_unknown_node_returns_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_align",
            {"workspace_slug": "w1", "ids": ["a", "ghost"], "anchor": "top"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


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


def test_canvas_create_sub_canvas_tool_is_registered():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_create_sub_canvas" in names


def test_canvas_create_sub_canvas_provisions_child_and_links():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_create_sub_canvas",
            {
                "parent_slug": "plant",
                "slug": "pump-loop",
                "title": "Pump Loop",
                "x": 10,
                "y": 20,
            },
        )
        out = json.loads(body)
        assert out["child"]["slug"] == "pump-loop"
        assert out["node"]["node_type"] == "canvas"
        assert out["node"]["data"]["canvas_slug"] == "pump-loop"
        assert out["event"]["type"] == "NodeAdded"
        state = await s.workspace.get_state("plant")
        canvas_nodes = [n for n in state["nodes"] if n["node_type"] == "canvas"]
        assert len(canvas_nodes) == 1

    asyncio.run(run())


def test_canvas_create_sub_canvas_rejects_self_link():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_create_sub_canvas",
            {"parent_slug": "plant", "slug": "plant"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_canvas_update_node_with_parent_dispatches_reparent():
    """`canvas_update_node {parent: <id>}` emits `NodeReparented`, mirroring HTTP."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="area", node_type="area")
        await s.workspace.add_node("w1", id="child", node_type="concept")
        body = await handlers_canvas.call_tool(
            s.workspace,
            "canvas_update_node",
            {"workspace_slug": "w1", "id": "child", "parent": "area"},
        )
        out = json.loads(body)
        assert out["event"]["type"] == "NodeReparented"
        assert out["event"]["payload"]["parent"] == "area"

    asyncio.run(run())


def test_canvas_update_node_rejects_self_parent():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(
            s.workspace,
            "canvas_update_node",
            {"workspace_slug": "w1", "id": "a", "parent": "a"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())
