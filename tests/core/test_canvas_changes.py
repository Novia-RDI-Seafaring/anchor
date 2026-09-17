"""canvas_changes — the catch-up fold over the event log (#325).

Covers: net-effect collapse (add+update → one added entry, add+remove →
net zero, pre-existing update+remove → removed), actor grouping, legacy
actor-less events under the ``None`` group, the since_version / since_ts
window boundaries, label resolution (final state vs. event payload), the
whole-log ``touched`` attribution map, and the fs-store event read.
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.events.actor import Actor, actor_scope
from anchor.core.workspace.workspace import CommandError
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore
from tests.fixtures.services import make_in_memory_services

HUMAN = Actor(kind="human", label="browser")
AGENT = Actor(kind="agent", label="claude-code")


def _group(out: dict, label: str | None) -> dict | None:
    for g in out["groups"]:
        actor = g.get("actor")
        if label is None and actor is None:
            return g
        if actor is not None and actor.get("label") == label:
            return g
    return None


# ── Net-effect collapse ─────────────────────────────────────────────────────

def test_add_then_updates_collapse_to_one_added_entry():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a", label="A", node_type="fact")
            await s.workspace.update_node("w1", "a", {"label": "A2"})
            await s.workspace.move_node("w1", "a", 10, 20)
        out = await s.workspace.canvas_changes("w1", since_version=0)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["nodes_added"]] == ["a"]
        assert g["nodes_updated"] == []
        # Label resolves from the final state (the updated one).
        assert g["nodes_added"][0]["label"] == "A2"
        assert g["nodes_added"][0]["node_type"] == "fact"
        assert out["from_version"] == 0
        assert out["to_version"] == 3

    asyncio.run(run())


def test_add_then_remove_in_window_nets_to_nothing():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a", label="A")
            await s.workspace.remove_node("w1", "a")
        out = await s.workspace.canvas_changes("w1", since_version=0)
        assert out["groups"] == []

    asyncio.run(run())


def test_preexisting_node_updated_then_removed_reports_removed():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="a", label="Pump", node_type="spec")
        boundary = 1
        with actor_scope(AGENT):
            await s.workspace.update_node("w1", "a", {"label": "Pump v2"})
            await s.workspace.remove_node("w1", "a")
        out = await s.workspace.canvas_changes("w1", since_version=boundary)
        g = _group(out, "claude-code")
        assert g is not None
        assert g["nodes_added"] == []
        assert g["nodes_updated"] == []
        assert [e["id"] for e in g["nodes_removed"]] == ["a"]
        # Gone from the final state → label comes from the event payload.
        assert g["nodes_removed"][0]["label"] == "Pump v2"

    asyncio.run(run())


def test_preexisting_node_moved_reports_updated():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="a", label="A")
        with actor_scope(AGENT):
            await s.workspace.move_node("w1", "a", 5, 5)
        out = await s.workspace.canvas_changes("w1", since_version=1)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["nodes_updated"]] == ["a"]
        assert g["nodes_added"] == [] and g["nodes_removed"] == []

    asyncio.run(run())


def test_edges_fold_like_nodes():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a")
            await s.workspace.add_node("w1", id="b")
            await s.workspace.add_edge("w1", id="e1", source="a", target="b", label="uses")
        out = await s.workspace.canvas_changes("w1", since_version=0)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["edges_added"]] == ["e1"]
        assert g["edges_added"][0]["source"] == "a"
        assert g["edges_added"][0]["target"] == "b"

    asyncio.run(run())


def test_remove_node_cascade_attributes_edge_removal_to_system():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="a")
            await s.workspace.add_node("w1", id="b")
            await s.workspace.add_edge("w1", id="e1", source="a", target="b")
        boundary = 3
        with actor_scope(AGENT):
            await s.workspace.remove_node("w1", "a")
        out = await s.workspace.canvas_changes("w1", since_version=boundary)
        agent_group = _group(out, "claude-code")
        assert agent_group is not None
        assert [e["id"] for e in agent_group["nodes_removed"]] == ["a"]
        # The cascade EdgeRemoved is stamped system (#322) and groups there.
        system_group = next(
            g for g in out["groups"]
            if g.get("actor") and g["actor"]["kind"] == "system"
        )
        assert [e["id"] for e in system_group["edges_removed"]] == ["e1"]

    asyncio.run(run())


# ── Actor grouping ──────────────────────────────────────────────────────────

def test_changes_group_by_actor():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="h1", label="H")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a1", label="A")
        out = await s.workspace.canvas_changes("w1", since_version=0)
        assert len(out["groups"]) == 2
        human = _group(out, "browser")
        agent = _group(out, "claude-code")
        assert human is not None and agent is not None
        assert [e["id"] for e in human["nodes_added"]] == ["h1"]
        assert [e["id"] for e in agent["nodes_added"]] == ["a1"]
        assert human["actor"] == {"kind": "human", "label": "browser"}

    asyncio.run(run())


def test_legacy_actorless_events_group_under_null_actor():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        # No actor_scope: the service records actor=None, exactly what a
        # pre-#322 log replays as.
        await s.workspace.add_node("w1", id="old", label="Old")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="new", label="New")
        out = await s.workspace.canvas_changes("w1", since_version=0)
        legacy = _group(out, None)
        assert legacy is not None
        assert legacy["actor"] is None
        assert [e["id"] for e in legacy["nodes_added"]] == ["old"]

    asyncio.run(run())


# ── Window boundaries ───────────────────────────────────────────────────────

def test_since_version_excludes_events_at_or_before_boundary():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a", label="A")   # v1
            await s.workspace.add_node("w1", id="b", label="B")   # v2
        out = await s.workspace.canvas_changes("w1", since_version=1)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["nodes_added"]] == ["b"]
        assert out["from_version"] == 1
        assert out["to_version"] == 2

    asyncio.run(run())


def test_since_version_at_head_reports_no_groups():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a")
        out = await s.workspace.canvas_changes("w1", since_version=1)
        assert out["groups"] == []
        assert out["from_version"] == 1
        assert out["to_version"] == 1

    asyncio.run(run())


def test_since_ts_windows_by_timestamp_and_reports_boundary_version():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a")  # ts=1700000000
        s.clock._ts = 1700000100.0
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="b")
        out = await s.workspace.canvas_changes("w1", since_ts=1700000050.0)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["nodes_added"]] == ["b"]
        assert out["from_version"] == 1  # last version at/before the ts

    asyncio.run(run())


def test_since_version_and_since_ts_are_mutually_exclusive():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with pytest.raises(CommandError):
            await s.workspace.canvas_changes(
                "w1", since_version=0, since_ts=0.0,
            )

    asyncio.run(run())


def test_negative_since_version_is_rejected():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with pytest.raises(CommandError):
            await s.workspace.canvas_changes("w1", since_version=-1)

    asyncio.run(run())


# ── Persisted attribution (`touched`) ───────────────────────────────────────

def test_whole_log_fold_carries_touched_map():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="legacy", label="L")  # actor=None
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="h", label="H")
        with actor_scope(AGENT):
            await s.workspace.move_node("w1", "h", 9, 9)
            await s.workspace.add_node("w1", id="gone")
            await s.workspace.remove_node("w1", "gone")
        out = await s.workspace.canvas_changes("w1")
        touched = out["touched"]
        # Last toucher wins; legacy touches answer None (honest "unknown").
        assert touched["h"] == {"kind": "agent", "label": "claude-code"}
        assert touched["legacy"] is None
        # Removed nodes drop out of the map.
        assert "gone" not in touched

    asyncio.run(run())


def test_windowed_fold_omits_touched_map():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a")
        out = await s.workspace.canvas_changes("w1", since_version=1)
        assert "touched" not in out
        # since_version=0 IS the whole log → touched present.
        out0 = await s.workspace.canvas_changes("w1", since_version=0)
        assert "touched" in out0

    asyncio.run(run())


# ── Canvas clear ────────────────────────────────────────────────────────────

def test_clear_surfaces_as_canvas_cleared_flag():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            await s.workspace.add_node("w1", id="a")
        boundary = 1
        with actor_scope(AGENT):
            await s.workspace.clear("w1")
        out = await s.workspace.canvas_changes("w1", since_version=boundary)
        g = _group(out, "claude-code")
        assert g is not None
        assert g.get("canvas_cleared") is True

    asyncio.run(run())


# ── FsWorkspaceStore read path ──────────────────────────────────────────────

def test_fs_store_canvas_changes_end_to_end(tmp_path):
    async def run():
        from anchor.core.services.workspace_service import WorkspaceService

        store = FsWorkspaceStore(tmp_path / "canvases")
        svc = WorkspaceService(store, MemoryEventBus())
        await svc.create_workspace("w1")
        with actor_scope(AGENT):
            await svc.add_node("w1", id="a", label="A")
            await svc.update_node("w1", "a", {"label": "A2"})
        # A fresh service over the same dir (cold boot) folds the log.
        svc2 = WorkspaceService(FsWorkspaceStore(tmp_path / "canvases"), MemoryEventBus())
        out = await svc2.canvas_changes("w1", since_version=0)
        g = _group(out, "claude-code")
        assert g is not None
        assert [e["id"] for e in g["nodes_added"]] == ["a"]
        assert g["nodes_added"][0]["label"] == "A2"
        assert out["touched"]["a"] == {"kind": "agent", "label": "claude-code"}

    asyncio.run(run())


def test_fs_store_read_events_unknown_workspace_raises(tmp_path):
    async def run():
        store = FsWorkspaceStore(tmp_path / "canvases")
        with pytest.raises(FileNotFoundError):
            await store.read_events("ghost")

    asyncio.run(run())
