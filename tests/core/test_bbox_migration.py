"""Bottom-left -> top-left data migration (#281), over the in-memory fakes."""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.bbox_migration import (
    flip_index,
    flip_pages_meta,
    flip_source_ref,
    migrate_all,
    migrate_document,
    needs_migration,
)
from tests.fixtures.services import make_in_memory_services

# Legacy bottom-left fixture: a 792pt-tall page; the title is near the top
# (large y in bottom-left space).
_LEGACY_H = 792.0


def _seed_legacy(store):
    async def seed():
        await store.write_silver_artifact("doc", "index.json", json.dumps({
            "document": {"filename": "doc.pdf", "title": "Doc", "page_count": 1},
            "outline": [{"level": 1, "title": "Doc", "page": 1, "bbox": [0, 720, 200, 700]}],
            "tables": [{"id": "t1", "page": 1, "bbox": [0, 600, 500, 400],
                        "cells": [{"row": 0, "col": 0, "text": "x", "bbox": [10, 590, 80, 560]}]}],
            "figures": [],
        }))
        await store.write_silver_artifact("doc", "pages.meta.json", json.dumps({
            "page_count": 1,
            "pages": {"1": {"item_count": 2, "labels": {}, "item_ids": ["p1-i0", "p1-i1"],
                            "bbox_union": [0, 720, 500, 400],
                            # No PDF in the memory store: the migration falls back to
                            # a recorded page size.
                            "page_size": [612.0, _LEGACY_H]}},
        }))
        await store.write_silver_artifact("doc", "pages/1.candidates.json", json.dumps([
            {"id": "p1-i0", "label": "title", "bbox": [0, 720, 200, 700], "text": "Doc"},
            {"id": "p1-i1", "label": "table", "bbox": [0, 600, 500, 400], "text": "",
             "cells": [{"row": 0, "col": 0, "text": "x", "bbox": [10, 590, 80, 560]}]},
        ]))
        await store.write_gold_region_file("doc", 1, [{
            "id": "r1", "kind": "table", "title": "T", "page": 1,
            "bbox": [0, 600, 500, 400], "approx_bbox": [0, 610, 510, 390],
            "cells": [{"row": 0, "col": 0, "text": "x", "bbox": [10, 590, 80, 560]}],
        }])

    asyncio.run(seed())


def test_needs_migration_keys_on_the_stamp():
    assert needs_migration(None) is True
    assert needs_migration({"pages": {}}) is True
    assert needs_migration({"bbox_origin": "top-left"}) is False


def test_flip_index_and_pages_meta():
    idx = flip_index({"outline": [{"page": 1, "bbox": [0, 720, 200, 700]}]}, {1: 792.0})
    assert idx["outline"][0]["bbox"] == [0.0, 72.0, 200.0, 92.0]
    meta = flip_pages_meta({"pages": {"1": {"bbox_union": [0, 720, 500, 400]}}}, {1: (612.0, 792.0)})
    assert meta["bbox_origin"] == "top-left"
    assert meta["pages"]["1"]["page_size"] == [612.0, 792.0]
    assert meta["pages"]["1"]["bbox_union"] == [0.0, 72.0, 500.0, 392.0]


def test_flip_source_ref_stamps_and_is_idempotent():
    ref = {"slug": "doc", "page": 1, "bbox": [0, 720, 200, 700],
           "detail": {"quote": "q", "cell_bbox": [10, 590, 80, 560]}}
    once = flip_source_ref(ref, 792.0)
    assert once["bbox"] == [0.0, 72.0, 200.0, 92.0]
    assert once["detail"]["cell_bbox"] == [10.0, 202.0, 80.0, 232.0]
    assert once["coord_origin"] == "top-left"
    assert flip_source_ref(once, 792.0) == once


def test_migrate_document_flips_silver_and_gold_then_stamps():
    s = make_in_memory_services(page_count=1)
    _seed_legacy(s.doc_store)

    async def run():
        first = await migrate_document(s.doc_store, None, "doc")
        assert first["status"] == "migrated"
        index = await s.doc_store.get_index("doc")
        assert index["outline"][0]["bbox"] == [0.0, 72.0, 200.0, 92.0]
        assert index["tables"][0]["cells"][0]["bbox"] == [10.0, 202.0, 80.0, 232.0]
        cands = await s.doc_store.get_page_candidates("doc", 1)
        assert cands[0]["bbox"] == [0.0, 72.0, 200.0, 92.0]
        assert cands[1]["cells"][0]["bbox"] == [10.0, 202.0, 80.0, 232.0]
        region = (await s.doc_store.get_regions("doc"))["pages"][1][0]
        assert region["bbox"] == [0.0, 192.0, 500.0, 392.0]
        assert region["approx_bbox"] == [0.0, 182.0, 510.0, 402.0]
        assert region["cells"][0]["bbox"] == [10.0, 202.0, 80.0, 232.0]
        meta = await s.doc_store.get_pages_meta("doc")
        assert meta["bbox_origin"] == "top-left"
        # Idempotent: a second run is a no-op.
        again = await migrate_document(s.doc_store, None, "doc")
        assert again["status"] == "already_top_left"
        assert (await s.doc_store.get_regions("doc"))["pages"][1][0]["bbox"] == [0.0, 192.0, 500.0, 392.0]

    asyncio.run(run())


def test_migrate_all_flips_canvas_source_refs_into_migrated_docs():
    s = make_in_memory_services(page_count=1)
    _seed_legacy(s.doc_store)

    async def run():
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="d", node_type="document", label="Doc", x=0, y=0,
                                   data={"slug": "doc"})
        await s.workspace.add_node("w1", id="spec", node_type="spec", label="S", x=0, y=0, data={
            "source_doc_slug": "doc",
            "source_ref": {"page": 1, "bbox": [0, 600, 500, 400]},
            "rows": [{"key": "x", "value": "1",
                      "source_ref": {"slug": "doc", "page": 1, "bbox": [10, 590, 80, 560]}}],
        })
        await s.workspace.add_edge("w1", source="spec", target="d", edge_type="anchored",
                                   data={"kind": "evidence", "source_ref": {"page": 1, "bbox": [0, 600, 500, 400]}})
        report = await migrate_all(s.doc_store, None, s.workspace)
        assert report["migrated"] == ["doc"]
        assert report["canvases"] == {"nodes_updated": 1, "edges_updated": 1}
        state = await s.workspace.get_state("w1")
        spec = next(n for n in state["nodes"] if n["id"] == "spec")
        assert spec["data"]["source_ref"]["bbox"] == [0.0, 192.0, 500.0, 392.0]
        assert spec["data"]["source_ref"]["coord_origin"] == "top-left"
        assert spec["data"]["rows"][0]["source_ref"]["bbox"] == [10.0, 202.0, 80.0, 232.0]
        edge = state["edges"][0]
        assert edge["data"]["source_ref"]["bbox"] == [0.0, 192.0, 500.0, 392.0]
        # Second pass touches nothing.
        again = await migrate_all(s.doc_store, None, s.workspace)
        assert again["canvases"] == {"nodes_updated": 0, "edges_updated": 0}

    asyncio.run(run())
