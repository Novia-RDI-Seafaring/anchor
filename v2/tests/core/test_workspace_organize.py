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


# ── direction-aware acme-org scenario ─────────────────────────────────
#
# Acme-org reports-to convention: subordinate node points AT its boss
# (edge.source = report, edge.target = manager). Organising from the CEO:
#
#   - direction="incoming" walks subordinate → boss arrows backward, so
#     the whole reports-to tree is reachable. This is the intended behaviour.
#   - direction="outgoing" walks arrows forward; the CEO has no outgoing
#     edges so the walk yields zero descendants.
#   - direction="any" (default) reproduces the original undirected walk.
#
# The bug this test guards is the inverse: organising from a mid-tree node
# like a CFO with "incoming" must NOT drag the CEO in.

def test_organize_incoming_walks_reports_to_subtree():
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        state, envelopes = await s.workspace.organize_subtree(
            "acme", "ceo", direction="incoming",
        )
        # Same six descendants as the default — reports-to convention
        # plus "incoming" gives the same scope as undirected for a root.
        assert len(envelopes) == 6
        assert {env.payload["id"] for env in envelopes} == {
            "m1", "m2", "r1", "r2", "r3", "r4",
        }
        ceo = state.nodes["ceo"]
        assert (ceo.x, ceo.y) == (0.0, 0.0)

    asyncio.run(run())


def test_organize_outgoing_from_ceo_in_reports_to_chart_is_noop():
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        state, envelopes = await s.workspace.organize_subtree(
            "acme", "ceo", direction="outgoing",
        )
        # CEO has zero outgoing edges in the reports-to convention.
        assert envelopes == []
        # State is untouched — version hasn't budged either.
        # (No NodeMoved emitted → store didn't snapshot a new version.)
        assert state.nodes["ceo"].x == 0

    asyncio.run(run())


def test_organize_incoming_from_midtree_scopes_to_strict_descendants():
    """The actual user-reported bug.

    On acme-org, selecting "CFO" (mid-tree manager) and organising should
    NOT drag the CEO in. With direction="incoming" the BFS only follows
    reports-to arrows backward, so the manager's subordinates move and the
    CEO stays put."""
    async def run():
        s = make_in_memory_services()
        await _seed_org_chart(s)
        # Pin the CEO's pre-organise position so we can detect any spurious
        # NodeMoved event hitting it.
        before = await s.workspace.get_state("acme")
        ceo_node_before = next(n for n in before["nodes"] if n["id"] == "ceo")
        ceo_xy_before = (ceo_node_before["x"], ceo_node_before["y"])

        state, envelopes = await s.workspace.organize_subtree(
            "acme", "m1", direction="incoming",
        )
        moved_ids = {env.payload["id"] for env in envelopes}
        # Only m1's reports move; m2/its reports/the CEO are untouched.
        assert moved_ids == {"r1", "r2"}
        # CEO position unchanged.
        assert (state.nodes["ceo"].x, state.nodes["ceo"].y) == ceo_xy_before

    asyncio.run(run())


def test_organize_any_default_matches_undirected_v1():
    """`direction="any"` (the default) must reproduce the original
    undirected walk byte-for-byte. Guards the no-surprise UX contract."""
    async def run():
        s_default = make_in_memory_services()
        s_explicit = make_in_memory_services()
        await _seed_org_chart(s_default)
        await _seed_org_chart(s_explicit)
        _, env_default = await s_default.workspace.organize_subtree(
            "acme", "m1",
        )
        _, env_explicit = await s_explicit.workspace.organize_subtree(
            "acme", "m1", direction="any",
        )
        # Same id set, same payload positions.
        ids_default = {(e.payload["id"], e.payload["x"], e.payload["y"]) for e in env_default}
        ids_explicit = {(e.payload["id"], e.payload["x"], e.payload["y"]) for e in env_explicit}
        assert ids_default == ids_explicit

    asyncio.run(run())


def test_organize_unsupported_direction_raises():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("acme")
        await s.workspace.add_node("acme", id="ceo")
        with pytest.raises(ValueError):
            await s.workspace.organize_subtree(
                "acme", "ceo", direction="sideways",  # type: ignore[arg-type]
            )

    asyncio.run(run())
