"""WorkspaceService.create_sub_canvas — end-to-end against in-memory stores.

The composite must:
  - Provision the child workspace (visible in `list_workspaces`).
  - Drop a `canvas`-typed linking node onto the parent with
    `data.canvas_slug` pointing at the child.
  - Publish a single `NodeAdded` envelope so SSE consumers can reconcile.
  - Reject invalid inputs (empty slug, self-link).
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.workspace.workspace import CommandError

from tests.fixtures.services import make_in_memory_services


def test_create_sub_canvas_provisions_child_and_links():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("parent", title="Parent")
        out = await s.workspace.create_sub_canvas(
            "parent", "child", title="Child Canvas", x=120.0, y=80.0,
        )
        # Child workspace exists.
        slugs = {w["slug"] for w in await s.workspace.list_workspaces()}
        assert {"parent", "child"} <= slugs
        # Linking node landed on the parent.
        state = await s.workspace.get_state("parent")
        canvas_nodes = [n for n in state["nodes"] if n["node_type"] == "canvas"]
        assert len(canvas_nodes) == 1
        node = canvas_nodes[0]
        assert node["data"]["canvas_slug"] == "child"
        assert node["data"]["title"] == "Child Canvas"
        assert node["x"] == 120.0
        assert node["y"] == 80.0
        # Result envelope is consistent with the state.
        assert out["child"]["slug"] == "child"
        assert out["event"]["type"] == "NodeAdded"
        assert out["node"]["data"]["canvas_slug"] == "child"

    asyncio.run(run())


def test_create_sub_canvas_rejects_self_link():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        with pytest.raises(CommandError):
            await s.workspace.create_sub_canvas("plant", "plant")

    asyncio.run(run())


def test_create_sub_canvas_rejects_empty_slug():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        with pytest.raises(CommandError):
            await s.workspace.create_sub_canvas("plant", "")

    asyncio.run(run())


def test_create_sub_canvas_publishes_node_added_event():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("parent")
        out: list = []

        async def collect():
            async for evt in s.bus.subscribe("parent"):
                out.append(evt)
                if len(out) >= 1:
                    return out
            return out

        task = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await s.workspace.create_sub_canvas("parent", "child")
        events = await asyncio.wait_for(task, timeout=1.0)
        assert events[0].type == "NodeAdded"
        assert events[0].payload["node_type"] == "canvas"
        assert events[0].payload["data"]["canvas_slug"] == "child"

    asyncio.run(run())
