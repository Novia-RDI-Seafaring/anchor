"""source_ref resolution (#242 P2b): cell > item > region > bbox.

Deterministic core over a MemoryDocStore — no model, no network.
"""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

REGION_BBOX = [50.0, 40.0, 550.0, 200.0]
CELL_BBOX = [280.0, 120.0, 340.0, 132.0]
ITEM_BBOX = [50.0, 40.0, 550.0, 60.0]


def _store(*, region_cells_have_bbox: bool = True) -> MemoryDocStore:
    store = MemoryDocStore()

    cells = [
        {"row": 0, "col": 0, "text": "Flow"},
        {"row": 0, "col": 1, "text": "35 m3/h"},
    ]
    if region_cells_have_bbox:
        cells[1]["bbox"] = CELL_BBOX

    async def seed() -> None:
        await store.write_silver_artifact(
            "lkh",
            "pages/2.candidates.json",
            json.dumps(
                [
                    {"id": "p2-i0", "label": "text", "bbox": ITEM_BBOX,
                     "text": "intro"},
                    {"id": "p2-i1", "label": "table", "bbox": REGION_BBOX,
                     "cells": [
                         {"row": 0, "col": 0, "text": "Flow"},
                         {"row": 0, "col": 1, "text": "35 m3/h",
                          "bbox": CELL_BBOX},
                     ]},
                ]
            ),
        )
        await store.write_gold_region_file(
            "lkh",
            2,
            [{"id": "r4", "kind": "table", "title": "Specs",
              "bbox": REGION_BBOX, "cells": cells,
              "member_item_ids": ["p2-i1"]}],
        )

    asyncio.run(seed())
    return store


def _resolve(store, ref):
    return asyncio.run(resolve_source_ref(store, "lkh", ref))


def test_legacy_region_ref_resolves_as_before():
    # Golden: a pre-P2b ref answers with the region bbox, nothing else.
    out = _resolve(_store(), {"page": 2, "region_id": "r4", "bbox": REGION_BBOX})
    assert out == {
        "slug": "lkh", "page": 2, "bbox": REGION_BBOX,
        "precision": "region", "region_id": "r4",
    }


def test_bare_bbox_ref_resolves_with_bbox_precision():
    out = _resolve(_store(), {"page": 2, "bbox": ITEM_BBOX})
    assert out["precision"] == "bbox"
    assert out["bbox"] == ITEM_BBOX


def test_cell_resolves_from_region_cells():
    out = _resolve(
        _store(), {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 1}}
    )
    assert out["precision"] == "cell"
    assert out["bbox"] == CELL_BBOX
    assert out["cell"] == {"row": 0, "col": 1}


def test_cell_falls_back_to_silver_geometry():
    # Region cells stored without bboxes: the silver table (#270) answers.
    out = _resolve(
        _store(region_cells_have_bbox=False),
        {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 1}},
    )
    assert out["precision"] == "cell"
    assert out["bbox"] == CELL_BBOX


def test_cell_without_stored_bbox_falls_through_to_region():
    # (0,0) has no bbox anywhere; the region layer answers instead.
    out = _resolve(
        _store(region_cells_have_bbox=False),
        {"page": 2, "region_id": "r4", "cell": {"row": 0, "col": 0}},
    )
    assert out["precision"] == "region"
    assert out["bbox"] == REGION_BBOX


def test_item_id_resolves_and_supplies_page():
    # No page in the ref: parsed from the item id.
    out = _resolve(_store(), {"item_id": "p2-i0"})
    assert out == {
        "slug": "lkh", "page": 2, "bbox": ITEM_BBOX,
        "precision": "item", "item_id": "p2-i0",
    }


def test_unknown_item_falls_through_to_region():
    out = _resolve(_store(), {"page": 2, "region_id": "r4", "item_id": "p2-i9"})
    assert out["precision"] == "region"


def test_unresolvable_ref_returns_none():
    assert _resolve(_store(), {}) is None
    assert _resolve(_store(), {"page": 9, "region_id": "r99"}) is None
