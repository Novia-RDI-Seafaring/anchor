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


def test_list_workspaces_includes_counts_and_references():
    """A → B, A → C, B → A — counts + references + reverse map line up.

    The cycle (A ↔ B) is explicitly preserved as a mutual reference pair
    so the frontend can flag "↩ cycle". C is a leaf with one parent."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("a", title="A canvas")
        await s.workspace.create_workspace("b", title="B canvas")
        await s.workspace.create_workspace("c", title="C canvas")
        # A links to B and C.
        await s.workspace.add_node(
            "a", node_type="canvas", label="→B",
            data={"canvas_slug": "b", "title": "to B"},
        )
        await s.workspace.add_node(
            "a", node_type="canvas", label="→C",
            data={"canvas_slug": "c", "title": "to C"},
        )
        # Extra non-canvas node on A so counts are non-trivial.
        await s.workspace.add_node("a", id="plain", node_type="concept", label="x")
        # B links back to A (cycle).
        await s.workspace.add_node(
            "b", node_type="canvas", label="→A",
            data={"canvas_slug": "a", "title": "to A"},
        )
        items = {it["slug"]: it for it in await s.workspace.list_workspaces()}
        assert set(items.keys()) >= {"a", "b", "c"}
        # A: 3 canvas-typed/concept nodes, 0 edges, refs [b,c], refd-by [b]
        a = items["a"]
        assert a["node_count"] == 3
        assert a["edge_count"] == 0
        assert sorted(a["references"]) == ["b", "c"]
        assert a["referenced_by"] == ["b"]
        # B: 1 canvas node, refs [a], refd-by [a]
        b = items["b"]
        assert b["node_count"] == 1
        assert b["references"] == ["a"]
        assert b["referenced_by"] == ["a"]
        # C: leaf, no refs out, one parent.
        c = items["c"]
        assert c["references"] == []
        assert c["referenced_by"] == ["a"]
        assert c["node_count"] == 0
        # Meta survives.
        assert a["title"] == "A canvas"

    asyncio.run(run())


def test_list_workspaces_ignores_self_link_and_missing_target():
    """Self-links and unset canvas_slug are filtered from `references`."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("only")
        # Self-link — must not appear in references.
        await s.workspace.add_node(
            "only", node_type="canvas", label="self",
            data={"canvas_slug": "only", "title": "self"},
        )
        # Unset target — silently skipped.
        await s.workspace.add_node(
            "only", node_type="canvas", label="dangling",
            data={"title": "no slug"},
        )
        items = {it["slug"]: it for it in await s.workspace.list_workspaces()}
        assert items["only"]["references"] == []
        # referenced_by also empty (nothing else points here).
        assert items["only"]["referenced_by"] == []

    asyncio.run(run())


def test_add_edge_with_handles_persists_and_round_trips_via_replay():
    """Anchored evidence edge with sourceHandle/targetHandle + data.source_ref
    survives the workspace store's snapshot path and the EdgeAdded envelope —
    the wire+replay surfaces row-handle wiring depends on. Drag a spec row
    handle onto a document region handle → backend stores both handles +
    the source_ref, the frontend snapshot reader sees them, edge-mode can
    swap floating↔anchored on hover."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="spec", node_type="spec", label="rows")
        await s.workspace.add_node("w1", id="doc", node_type="document", label="src")
        state, env = await s.workspace.add_edge(
            "w1",
            id="e1",
            source="spec",
            target="doc",
            edge_type="anchored",
            sourceHandle="row:Max inlet pressure",
            targetHandle="region:r4",
            data={
                "kind": "evidence",
                "source_ref": {"page": 2, "region_id": "r4", "bbox": [1.0, 2.0, 3.0, 4.0]},
            },
        )
        # Top-level handles + data.source_ref both present on the live edge.
        edge = state.edges["e1"]
        assert edge.sourceHandle == "row:Max inlet pressure"
        assert edge.targetHandle == "region:r4"
        assert edge.data["source_ref"]["region_id"] == "r4"
        # The EdgeAdded envelope payload carries the handles too — that's
        # what SSE delivers; the frontend snapshot reader needs them.
        assert env.payload["sourceHandle"] == "row:Max inlet pressure"
        assert env.payload["targetHandle"] == "region:r4"
        # Snake-case kwargs also work for the CLI path (`--source-handle`).
        await s.workspace.add_edge(
            "w1",
            id="e2",
            source="spec",
            target="doc",
            edge_type="anchored",
            source_handle="row:Temperature range",
            target_handle="region:r5",
            data={
                "kind": "evidence",
                "source_ref": {"page": 2, "region_id": "r5", "bbox": [5.0, 6.0, 7.0, 8.0]},
            },
        )
        # Reload from the store — handles survive the snapshot path.
        reloaded = await s.workspace_store.load("w1")
        re_edge = reloaded.edges["e1"]
        assert re_edge.sourceHandle == "row:Max inlet pressure"
        assert re_edge.targetHandle == "region:r4"
        assert re_edge.data["source_ref"]["region_id"] == "r4"
        snake_edge = reloaded.edges["e2"]
        assert snake_edge.sourceHandle == "row:Temperature range"
        assert snake_edge.targetHandle == "region:r5"
        # And the wire shape (get_state) emits the camelCase handles so the
        # frontend canvasStore picks them up without an alias step.
        wire = state.get_state()
        wire_edge = next(e for e in wire["edges"] if e["id"] == "e1")
        assert wire_edge["sourceHandle"] == "row:Max inlet pressure"
        assert wire_edge["targetHandle"] == "region:r4"

    asyncio.run(run())


def test_list_workspaces_dedupes_repeated_canvas_links():
    """Two canvas-nodes pointing at the same child appear once in refs."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("parent")
        await s.workspace.create_workspace("child")
        await s.workspace.add_node(
            "parent", node_type="canvas", label="link1",
            data={"canvas_slug": "child"},
        )
        await s.workspace.add_node(
            "parent", node_type="canvas", label="link2",
            data={"canvas_slug": "child"},
        )
        items = {it["slug"]: it for it in await s.workspace.list_workspaces()}
        assert items["parent"]["references"] == ["child"]
        assert items["child"]["referenced_by"] == ["parent"]

    asyncio.run(run())
