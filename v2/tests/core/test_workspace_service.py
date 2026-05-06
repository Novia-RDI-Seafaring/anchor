"""End-to-end tests for WorkspaceService against in-memory stores + bus."""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.workspace.workspace import CommandError

from tests.fixtures.services import make_in_memory_services


async def _collect(bus, slug: str, n: int):
    out = []
    async for evt in bus.subscribe(slug):
        out.append(evt)
        if len(out) >= n:
            return out
    return out


def test_add_node_emits_event_and_persists():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1", title="One")
        events_task = asyncio.create_task(_collect(s.bus, "w1", 1))
        await asyncio.sleep(0)
        state, env = await s.workspace.add_node("w1", node_type="concept", label="A")
        events = await asyncio.wait_for(events_task, timeout=1.0)
        assert env.version == 1
        assert env.workspace_id == "w1"
        assert env.type == "NodeAdded"
        assert events[0].id == env.id
        assert "A" in {n.label for n in state.nodes.values()}

    asyncio.run(run())


def test_remove_node_cascades_edges():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", label="A")
        await s.workspace.add_node("w1", id="b", label="B")
        await s.workspace.add_edge("w1", id="e1", source="a", target="b")
        state, envelopes = await s.workspace.remove_node("w1", "a")
        types = [e.type for e in envelopes]
        assert types == ["EdgeRemoved", "NodeRemoved"]
        assert "a" not in state.nodes
        assert "e1" not in state.edges

    asyncio.run(run())


def test_idempotent_event_id_returns_same_version():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        _, env = await s.workspace.add_node("w1", id="x", label="X")
        v1 = env.version
        v2 = await s.workspace_store.append_event("w1", env)
        assert v1 == v2

    asyncio.run(run())


def test_command_validation_blocks_orphan_edge():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        with pytest.raises(CommandError):
            await s.workspace.add_edge("w1", source="a", target="ghost")

    asyncio.run(run())


def test_move_node_increments_version_and_records_position():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        _, e1 = await s.workspace.add_node("w1", id="a")
        state, e2 = await s.workspace.move_node("w1", "a", x=100, y=200)
        assert e2.version == e1.version + 1
        assert state.nodes["a"].x == 100

    asyncio.run(run())


def test_event_envelope_carries_clock_timestamp():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        _, env = await s.workspace.add_node("w1", id="a")
        assert env.ts == 1700000000.0

    asyncio.run(run())
