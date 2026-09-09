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


def test_producer_types_are_discoverable_but_open():
    # Producer types (cad:model, spec, document, model3d) are now DESCRIBED by
    # the node-types surface (was "unknown"), so an agent can learn the key
    # that matters — e.g. a CAD node's slug lives in `cad_slug`, not `slug`.
    s = make_in_memory_services()
    only = s.workspace.node_types_schema("cad:model")
    assert len(only) == 1 and only[0]["name"] == "cad:model"
    assert "cad_slug" in only[0]["description"].lower()
    # Still OPEN: no closed field list, so no false unknown-key warning on the
    # rich producer shape (the common `slug` mistake included).
    assert only[0]["data_fields"] is None
    assert s.workspace.unknown_data_keys("cad:model", {"slug": "x", "kind": "stl"}) == []
    assert s.workspace.unknown_data_keys("spec", {"rows": [], "source_ref": {}}) == []


# -- #309: OIP ui_hints renders tokens on the node-types surface ------------

_FAKE_GRAPHTRACER_MANIFEST = {
    "oip_version": "0.3",
    "producer": {"name": "graph-data-extractor", "version": "0.2.0"},
    "ui_hints": {
        "node_types": [
            {"name": "graphtracer:chart_series", "renders": "chart"},
            # No renders token: still described, renders stays None.
            {"name": "graphtracer:calibration"},
            # Malformed entries are skipped, never an error.
            {"renders": "chart"},
            "not-a-mapping",
            {"name": "", "renders": "chart"},
        ]
    },
}


def test_node_types_from_ui_hints_carries_renders_token():
    from anchor.core.workspace.node_types import node_types_from_ui_hints

    types = node_types_from_ui_hints([_FAKE_GRAPHTRACER_MANIFEST])
    by_name = {t.name: t for t in types}
    assert set(by_name) == {"graphtracer:chart_series", "graphtracer:calibration"}
    assert by_name["graphtracer:chart_series"].renders == "chart"
    assert by_name["graphtracer:calibration"].renders is None
    # Manifest-declared types are open: no false unknown-key warning.
    assert by_name["graphtracer:chart_series"].data_fields is None
    assert "graph-data-extractor" in by_name["graphtracer:chart_series"].description


def test_node_types_from_ui_hints_tolerates_hintless_manifests():
    from anchor.core.workspace.node_types import node_types_from_ui_hints

    assert node_types_from_ui_hints([]) == []
    assert node_types_from_ui_hints([{"oip_version": "0.1"}]) == []
    assert node_types_from_ui_hints([{"ui_hints": {"node_types": "nope"}}]) == []


def test_registry_schema_includes_renders_and_exact_registration_wins():
    from anchor.core.workspace.builtin_node_types import builtin_node_type_registry
    from anchor.core.workspace.node_types import NodeType, node_types_from_ui_hints

    registry = builtin_node_type_registry()
    manifest = {
        "producer": {"name": "p"},
        "ui_hints": {
            "node_types": [
                {"name": "graphtracer:chart_series", "renders": "chart"},
                # Clash with a built-in: the exact registration wins.
                {"name": "fact", "renders": "chart"},
            ]
        },
    }
    for nt in node_types_from_ui_hints([manifest]):
        registry.register_if_absent(nt)

    schema = {e["name"]: e for e in registry.schema()}
    assert schema["graphtracer:chart_series"]["renders"] == "chart"
    # Built-ins gain the additive key with a null token; fields unchanged.
    assert schema["fact"]["renders"] is None
    assert schema["fact"]["body_field"] == "text"
    # register_if_absent reports the duplicate instead of raising.
    assert registry.register_if_absent(NodeType(name="fact")) is False
