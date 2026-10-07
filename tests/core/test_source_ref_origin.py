"""Origin metadata belongs to current authoring, never historical replay."""
from __future__ import annotations

import asyncio

from tests.fixtures.services import make_in_memory_services


def test_current_workspace_writers_stamp_node_row_edge_and_bibliography_refs():
    s = make_in_memory_services()
    bbox = [304.72444, 389.03597, 350.90344, 397.30297]
    ref = {"slug": "doc", "page": 2, "bbox": bbox}

    async def run():
        await s.workspace.create_workspace("w")
        await s.workspace.add_node("w", id="doc", node_type="document")
        await s.workspace.add_node("w", id="spec", node_type="spec", data={
            "source_ref": ref, "rows": [{"value": "600 kPa", "source_ref": ref}],
        })
        await s.workspace.add_edge("w", id="e", source="spec", target="doc", data={"source_ref": ref})
        bibliography = await s.workspace.create_reference("w", source_ref=ref)
        await s.workspace.attach_reference("w", bibliography["id"], node_id="spec", row_index=0)
        state = await s.workspace.get_state("w")
        spec = next(n for n in state["nodes"] if n["id"] == "spec")
        refs = [spec["data"]["source_ref"], spec["data"]["rows"][0]["source_ref"],
                state["edges"][0]["data"]["source_ref"], state["metadata"]["references"][0]["source_ref"]]
        for stored in refs:
            assert stored["coord_origin"] == "top-left"
            assert stored["bbox"] == bbox
        # Writers must not mutate caller-owned data.
        assert "coord_origin" not in ref

    asyncio.run(run())


def test_updates_and_attachments_preserve_historical_ambiguous_locator_copies():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        refs = [{"slug": "doc", "page": 1, "bbox": [10, y, 30, y + 5]} for y in (100, 200)]
        await s.workspace.add_node("w", id="spec", node_type="spec", data={
            "rows": [{"value": str(i), "source_ref": ref} for i, ref in enumerate(refs)],
        })
        bibliography = await s.workspace.create_reference("w", source_ref=refs[0])
        stored = await s.workspace_store.load("w")
        for row in stored.nodes["spec"].data["rows"]:
            row["source_ref"].pop("coord_origin", None)
        stored.metadata["references"][0]["source_ref"].pop("coord_origin", None)
        await s.workspace_store.snapshot("w", stored)
        await s.workspace.attach_reference("w", bibliography["id"], node_id="spec")
        # Whole-list updates/reordering are not new coordinate authoring.
        await s.workspace.update_node("w", "spec", {"data": {"rows": [
            {"value": "1", "source_ref": refs[1]}, {"value": "0", "source_ref": refs[0]},
        ]}})
        result = (await s.workspace.get_state("w"))["nodes"][0]["data"]
        assert result["source_ref"].get("coord_origin") is None
        assert all(row["source_ref"].get("coord_origin") is None for row in result["rows"])

    asyncio.run(run())


def test_partial_new_bbox_write_replaces_inherited_legacy_origin():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        await s.workspace.add_node("w", id="n", data={"source_ref": {
            "slug": "doc", "page": 1, "bbox": [10, 700, 30, 680], "coord_origin": "bottom-left",
            "detail": {"cell_bbox": [12, 695, 25, 685], "quote": "600 kPa"},
        }})
        await s.workspace.update_node("w", "n", {"data": {"source_ref": {"bbox": [10, 92, 30, 112]}}})
        ref = (await s.workspace.get_state("w"))["nodes"][0]["data"]["source_ref"]
        assert ref["coord_origin"] == "top-left"
        assert ref["page"] == 1
        assert ref["bbox"] == [10, 92, 30, 112]
        assert "cell_bbox" not in ref["detail"]
        assert ref["detail"]["quote"] == "600 kPa"

    asyncio.run(run())


def test_non_page_locators_and_explicit_unknown_origins_are_not_relabelled():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        refs = [
            {"kind": "cad-face", "bbox": [1, 2, 3, 4]},
            {"file": "model.sysml", "line": 8, "col": 2},
            {"slug": "old", "page": 1, "bbox": [1, 2, 3, 4], "coord_origin": None},
        ]
        for i, ref in enumerate(refs):
            await s.workspace.add_node("w", id=str(i), data={"source_ref": ref})
        state = await s.workspace.get_state("w")
        assert [n["data"]["source_ref"] for n in state["nodes"]] == refs

    asyncio.run(run())


def test_partial_quote_edit_does_not_relabel_existing_cell_geometry():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        await s.workspace.add_node("w", id="n", data={"source_ref": {
            "slug": "doc", "page": 1, "bbox": [10, 700, 30, 680],
            "coord_origin": None, "detail": {"cell_bbox": [10, 700, 30, 680]},
        }})
        await s.workspace.update_node("w", "n", {"data": {"source_ref": {
            "detail": {"quote": "Updated caption"},
        }}})
        ref = (await s.workspace.get_state("w"))["nodes"][0]["data"]["source_ref"]
        assert ref.get("coord_origin") is None
        assert ref["detail"]["cell_bbox"] == [10, 700, 30, 680]

    asyncio.run(run())


def test_partial_quote_edit_preserves_legacy_origin_with_canonical_rows():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        await s.workspace.add_node("w", id="n", data={
            "source_ref": {"page": 1, "bbox": [10, 700, 30, 680], "coord_origin": "bottom-left"},
            "rows": [{"source_ref": {"page": 1, "bbox": [10, 92, 30, 112]}}],
        })
        await s.workspace.update_node("w", "n", {"data": {"source_ref": {"detail": {"quote": "q"}}}})
        ref = (await s.workspace.get_state("w"))["nodes"][0]["data"]["source_ref"]
        assert ref["coord_origin"] == "bottom-left"

    asyncio.run(run())


def test_explicit_origin_declaration_alone_preserves_recorded_geometry():
    s = make_in_memory_services()

    async def run():
        await s.workspace.create_workspace("w")
        ref = {"page": 1, "bbox": [10, 92, 30, 112], "coord_origin": None,
               "detail": {"cell_bbox": [12, 97, 25, 107], "quote": "q"}}
        await s.workspace.add_node("w", id="n", data={"source_ref": ref})
        await s.workspace.update_node("w", "n", {"data": {"source_ref": {"coord_origin": "top-left"}}})
        stored = (await s.workspace.get_state("w"))["nodes"][0]["data"]["source_ref"]
        assert stored == {**ref, "coord_origin": "top-left"}

    asyncio.run(run())
