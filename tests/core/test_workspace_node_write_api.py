"""WorkspaceService node-write API hardening — #186/#189/#191/#192."""
from __future__ import annotations

import asyncio

from tests.fixtures.services import make_in_memory_services


# ── #192: update-node --data merges, not replaces ───────────────────────────

def test_update_node_data_merges_and_preserves_source_ref():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node(
            "w1", id="f", node_type="fact", label="F",
            x=0, y=0,
            data={"body": "x", "source_ref": {"page": 1, "bbox": [0, 0, 1, 1]}, "doc": "d"},
        )
        state, _ = await s.workspace.update_node("w1", "f", {"data": {"text": "hello"}})
        data = state.nodes["f"].data
        # source_ref + doc survive; new key added.
        assert data["text"] == "hello"
        assert data["source_ref"] == {"page": 1, "bbox": [0, 0, 1, 1]}
        assert data["doc"] == "d"

    asyncio.run(run())


def test_update_node_null_deletes_a_data_key():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="f", node_type="fact", x=0, y=0,
                                   data={"text": "x", "stale": "y"})
        state, _ = await s.workspace.update_node("w1", "f", {"data": {"stale": None}})
        assert "stale" not in state.nodes["f"].data
        assert state.nodes["f"].data["text"] == "x"

    asyncio.run(run())


# ── #189: server auto-place ─────────────────────────────────────────────────

def test_add_node_without_coords_auto_places_non_overlapping():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        # First node, no coords -> origin.
        _, e1 = await s.workspace.add_node("w1", node_type="fact", width=120, height=80)
        assert (e1.payload["x"], e1.payload["y"]) == (0.0, 0.0)
        # Second node, no coords -> not on top of the first.
        _, e2 = await s.workspace.add_node("w1", node_type="fact", width=120, height=80)
        assert (e2.payload["x"], e2.payload["y"]) != (e1.payload["x"], e1.payload["y"])

    asyncio.run(run())


def test_add_node_with_coords_lands_exactly_there():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        _, env = await s.workspace.add_node("w1", node_type="fact", x=500, y=600)
        assert (env.payload["x"], env.payload["y"]) == (500.0, 600.0)

    asyncio.run(run())


def test_place_auto_overrides_given_coords():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", node_type="fact", x=0, y=0,
                                   width=120, height=80)
        # Ask for (0,0) but place=auto -> server moves it clear of node a.
        _, env = await s.workspace.add_node(
            "w1", node_type="fact", x=0, y=0, width=120, height=80, place="auto",
        )
        assert (env.payload["x"], env.payload["y"]) != (0.0, 0.0)

    asyncio.run(run())


# ── #191: data-field contract ───────────────────────────────────────────────

def test_node_types_schema_lists_body_fields():
    s = make_in_memory_services()
    schema = {e["name"]: e for e in s.workspace.node_types_schema()}
    assert schema["fact"]["body_field"] == "text"
    assert schema["concept"]["body_field"] == "subtitle"
    assert "text" in schema["fact"]["data_fields"]
    # A single type can be requested.
    only = s.workspace.node_types_schema("fact")
    assert len(only) == 1 and only[0]["name"] == "fact"


def test_unknown_data_keys_flags_body_on_fact():
    s = make_in_memory_services()
    # `body` is not a rendered key on fact (it renders `text`).
    assert s.workspace.unknown_data_keys("fact", {"body": "x"}) == ["body"]
    # `text` is recognised.
    assert s.workspace.unknown_data_keys("fact", {"text": "x"}) == []
    # Unregistered/producer types stay open (no warning).
    assert s.workspace.unknown_data_keys("spec", {"rows": []}) == []
