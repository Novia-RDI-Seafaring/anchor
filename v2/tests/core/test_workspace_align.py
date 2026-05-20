"""End-to-end tests for WorkspaceService.align_nodes / distribute_nodes.

Sets up a tiny canvas, runs the op, and asserts the burst of NodeMoved
events looks right: one per moved node, shared causation_id, version
counter bumped by exactly the number of moves.
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.workspace.workspace import CommandError

from tests.fixtures.services import make_in_memory_services


async def _seed_four_corners(s):
    """Four nodes at the corners of a 200×200 square.

    Each node is 100×100 so the bounding rects of "top edge" / "left edge"
    etc. resolve to predictable numbers.
    """
    await s.workspace.create_workspace("w")
    # (x, y) is top-left in the canvas's coordinate space.
    await s.workspace.add_node("w", id="tl", x=0,   y=0,   width=100, height=100)
    await s.workspace.add_node("w", id="tr", x=200, y=10,  width=100, height=100)
    await s.workspace.add_node("w", id="bl", x=5,   y=200, width=100, height=100)
    await s.workspace.add_node("w", id="br", x=205, y=205, width=100, height=100)


def test_align_top_emits_one_move_per_node_that_actually_moves():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        before = await s.workspace.get_state("w")
        v_before = before["version"]

        _, envelopes = await s.workspace.align_nodes(
            "w", ["tl", "tr", "bl"], "top",
        )
        # tl is already at y=0, so it stays. tr (y=10) and bl (y=200) move.
        moved = {env.payload["id"] for env in envelopes}
        assert moved == {"tr", "bl"}
        assert all(env.type == "NodeMoved" for env in envelopes)
        # All causation ids match — one logical "align top" gesture.
        causes = {env.causation_id for env in envelopes}
        assert len(causes) == 1
        # Version bumps by exactly len(envelopes).
        after = await s.workspace.get_state("w")
        assert after["version"] == v_before + len(envelopes)

    asyncio.run(run())


def test_align_unknown_node_raises():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        with pytest.raises(CommandError):
            await s.workspace.align_nodes("w", ["tl", "ghost"], "top")

    asyncio.run(run())


def test_align_fewer_than_two_raises():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        with pytest.raises(CommandError):
            await s.workspace.align_nodes("w", ["tl"], "top")

    asyncio.run(run())


def test_align_unknown_anchor_raises():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        with pytest.raises(ValueError):
            await s.workspace.align_nodes("w", ["tl", "tr"], "diagonal")  # type: ignore[arg-type]

    asyncio.run(run())


def test_align_idempotent_when_already_on_line():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w")
        await s.workspace.add_node("w", id="a", x=0,  y=5, width=100, height=100)
        await s.workspace.add_node("w", id="b", x=50, y=5, width=100, height=100)
        # Both already share y=5 — align top must emit zero events.
        _, envelopes = await s.workspace.align_nodes("w", ["a", "b"], "top")
        assert envelopes == []

    asyncio.run(run())


def test_distribute_horizontal_centres_middle_node():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w")
        # Three 100-wide nodes; middle is off-centre, must be pulled in.
        await s.workspace.add_node("w", id="a", x=0,   y=0, width=100, height=100)
        await s.workspace.add_node("w", id="b", x=120, y=0, width=100, height=100)
        await s.workspace.add_node("w", id="c", x=300, y=0, width=100, height=100)
        _, envelopes = await s.workspace.distribute_nodes(
            "w", ["a", "b", "c"], "horizontal",
        )
        # Endpoints stay; only b moves to its evenly-spaced slot.
        moved = {env.payload["id"] for env in envelopes}
        assert moved == {"b"}
        assert envelopes[0].payload["x"] == 150.0

    asyncio.run(run())


def test_distribute_fewer_than_three_raises():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        with pytest.raises(CommandError):
            await s.workspace.distribute_nodes("w", ["tl", "tr"], "horizontal")

    asyncio.run(run())


def test_distribute_unknown_axis_raises():
    async def run():
        s = make_in_memory_services()
        await _seed_four_corners(s)
        with pytest.raises(ValueError):
            await s.workspace.distribute_nodes(
                "w", ["tl", "tr", "bl"], "diagonal",  # type: ignore[arg-type]
            )

    asyncio.run(run())
