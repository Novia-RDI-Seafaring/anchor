"""End-to-end test for WorkspaceService.organize_subtree.

Builds a small org-chart-style workspace, runs organize, and asserts the
emitted events + final state. The fixture mirrors the shape of the
acme-org canvas the spec calls out, but stays small enough to assert
exact positions on. Acme-org itself is exercised by hand in the dev loop;
the parity rule guarantees the UI, MCP, and CLI all walk the same path
this test does.
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.workspace.workspace import CommandError

from tests.fixtures.services import make_in_memory_services


async def _seed_org_chart(s):
    """ceo at (0,0); two managers each with two reports.

    Edges follow the acme-org convention: source = child, target = parent
    (the `reports to` direction). The organizer is direction-agnostic so
    flipping these would yield the same result."""
    await s.workspace.create_workspace("acme")
    await s.workspace.add_node("acme", id="ceo", label="CEO", x=0, y=0)
    await s.workspace.add_node("acme", id="m1", label="Mgr1", x=-99, y=-99)
    await s.workspace.add_node("acme", id="m2", label="Mgr2", x=999, y=999)
    await s.workspace.add_node("acme", id="r1", label="Rep1", x=42, y=42)
    await s.workspace.add_node("acme", id="r2", label="Rep2", x=-7, y=33)
    await s.workspace.add_node("acme", id="r3", label="Rep3", x=11, y=22)
    await s.workspace.add_node("acme", id="r4", label="Rep4", x=88, y=88)
    await s.workspace.add_edge("acme", source="m1", target="ceo")
    await s.workspace.add_edge("acme", source="m2", target="ceo")
    await s.workspace.add_edge("acme", source="r1", target="m1")
    await s.workspace.add_edge("acme", source="r2", target="m1")
    await s.workspace.add_edge("acme", source="r3", target="m2")
    await s.workspace.add_edge("acme", source="r4", target="m2")


def test_organize_emits_one_move_per_descendant():
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        before = await s.workspace.get_state("acme")
        v_before = before["version"]
        state, envelopes = await s.workspace.organize_subtree("acme", "ceo")
        # 6 descendants, all initially at junk positions, so all 6 move.
        assert len(envelopes) == 6
        assert all(env.type == "NodeMoved" for env in envelopes)
        ids_moved = {env.payload["id"] for env in envelopes}
        assert ids_moved == {"m1", "m2", "r1", "r2", "r3", "r4"}
        # Root stays anchored at (0, 0).
        ceo = state.nodes["ceo"]
        assert (ceo.x, ceo.y) == (0.0, 0.0)
        # All causation_ids are the same — one logical org operation.
        cause = {env.causation_id for env in envelopes}
        assert len(cause) == 1
        # Version moves by exactly len(envelopes).
        assert state.version == v_before + 6

    asyncio.run(run())


def test_organize_unknown_root_raises():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("acme")
        await s.workspace.add_node("acme", id="ceo")
        with pytest.raises(CommandError):
            await s.workspace.organize_subtree("acme", "ghost")

    asyncio.run(run())


def test_organize_unknown_algo_raises():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("acme")
        await s.workspace.add_node("acme", id="ceo")
        with pytest.raises(ValueError):
            await s.workspace.organize_subtree("acme", "ceo", algo="elk")  # type: ignore[arg-type]

    asyncio.run(run())


def test_organize_horizontal_orientation():
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        state, envelopes = await s.workspace.organize_subtree(
            "acme", "ceo", orientation="horizontal",
        )
        assert len(envelopes) == 6
        # Horizontal: descendants spread out along y, root.y is 0, so
        # at least one manager has x > 0 (to the right of the root).
        m1 = state.nodes["m1"]
        m2 = state.nodes["m2"]
        assert m1.x > 0 or m2.x > 0

    asyncio.run(run())


def test_organize_idempotent_when_already_tidy():
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        # First pass moves everything.
        _, first = await s.workspace.organize_subtree("acme", "ceo")
        assert len(first) == 6
        # Second pass: layout is now tidy, so nothing should move.
        _, second = await s.workspace.organize_subtree("acme", "ceo")
        assert second == []

    asyncio.run(run())


def test_organize_leaf_root_returns_no_events():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("acme")
        await s.workspace.add_node("acme", id="lonely")
        state, envelopes = await s.workspace.organize_subtree("acme", "lonely")
        assert envelopes == []
        assert state.nodes["lonely"].x == 0

    asyncio.run(run())
