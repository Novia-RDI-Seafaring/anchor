"""Region inspection read-ops (#242 P1): inspect_region + get_region_content.

Deterministic core over a MemoryDocStore — no model, no network.
"""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.region_inspect import (
    get_region_content,
    inspect_region,
)
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore


def _store_with_region() -> MemoryDocStore:
    store = MemoryDocStore()

    async def seed() -> None:
        await store.write_gold_region_file(
            "lkh",
            2,
            [
                {
                    "id": "r4",
                    "kind": "table",
                    "title": "Specifications",
                    "description": "",
                    "page": 2,
                    "bbox": [50, 480, 550, 410],
                    "tags": ["spec"],
                    "entities": ["LKH-5"],
                    "content": "| Model | LKH-5 |",
                    "cells": [
                        {"row": 0, "col": 0, "text": "Model"},
                        {"row": 0, "col": 1, "text": "LKH-5"},
                    ],
                }
            ],
        )

    asyncio.run(seed())
    return store


def test_inspect_region_returns_full_record_and_source_ref():
    store = _store_with_region()
    out = asyncio.run(inspect_region(store, "lkh", "p2/r4"))
    assert out is not None
    assert out["region_id"] == "r4"
    assert out["page"] == 2
    assert out["kind"] == "table"
    assert out["title"] == "Specifications"
    assert out["entities"] == ["LKH-5"]
    assert out["source_ref"] == {
        "slug": "lkh",
        "page": 2,
        "region_id": "r4",
        "bbox": [50, 480, 550, 410],
    }
    assert out["cells"][1]["text"] == "LKH-5"


def test_inspect_region_accepts_bare_id():
    store = _store_with_region()
    out = asyncio.run(inspect_region(store, "lkh", "r4"))
    assert out is not None and out["region_id"] == "r4" and out["page"] == 2


def test_get_region_content_returns_stored_content():
    store = _store_with_region()
    out = asyncio.run(get_region_content(store, "lkh", "p2/r4"))
    assert out is not None
    assert "| Model | LKH-5 |" in out["content"]
    assert out["cells"][0]["text"] == "Model"


def test_inspect_region_missing_returns_none():
    store = _store_with_region()
    assert asyncio.run(inspect_region(store, "lkh", "r99")) is None
    assert asyncio.run(get_region_content(store, "lkh", "nope")) is None


def _store_with_derived_region() -> MemoryDocStore:
    store = MemoryDocStore()

    async def seed() -> None:
        await store.write_gold_region_file(
            "lkh",
            4,
            [
                {"id": "r1", "kind": "chart", "title": "Flow chart",
                 "bbox": [56, 58, 252, 223]},
                {
                    "id": "r9",
                    "kind": "chart_series",
                    "title": "LKH-5 digitized",
                    "derived_from": "r1",
                    "source_ref": {"page": 4, "region_id": "r1",
                                   "bbox": [56, 58, 252, 223]},
                    "series": [{"label": "LKH-5", "points": [[0, 21.7], [20.9, 8.8]]}],
                    "axes": {"x_label": "Q", "y_label": "H"},
                },
            ],
        )

    asyncio.run(seed())
    return store


def test_inspect_region_returns_stored_provenance_for_derived_region():
    # A derived region's stored source_ref points at its parent; the read
    # view must return it (not a synthesized self-ref) plus derived_from
    # and the producer payload (#242 P2a; found live by an AX session).
    store = _store_with_derived_region()
    out = asyncio.run(inspect_region(store, "lkh", "p4/r9"))
    assert out is not None
    assert out["derived_from"] == "r1"
    assert out["source_ref"]["region_id"] == "r1"
    assert out["source_ref"]["bbox"] == [56, 58, 252, 223]
    assert out["source_ref"]["slug"] == "lkh"  # defaulted in
    assert out["data"]["series"][0]["label"] == "LKH-5"
    assert out["data"]["axes"]["x_label"] == "Q"


def test_get_region_content_carries_derived_provenance_and_payload():
    store = _store_with_derived_region()
    out = asyncio.run(get_region_content(store, "lkh", "p4/r9"))
    assert out is not None
    assert out["derived_from"] == "r1"
    assert out["source_ref"]["region_id"] == "r1"
    assert out["data"]["series"][0]["points"][0] == [0, 21.7]


def test_inspect_region_plain_region_keeps_synthesized_ref_shape():
    # Regions without a stored ref answer exactly as before (P2a golden).
    store = _store_with_region()
    out = asyncio.run(inspect_region(store, "lkh", "p2/r4"))
    assert out["source_ref"] == {
        "slug": "lkh", "page": 2, "region_id": "r4", "bbox": [50, 480, 550, 410],
    }
    assert out["derived_from"] is None
    assert out["data"] is None


def test_inspect_region_expands_members():
    store = MemoryDocStore()

    async def seed() -> None:
        await store.write_silver_artifact(
            "lkh",
            "pages/2.candidates.json",
            json.dumps(
                [
                    {"id": "p2-i0", "label": "text",
                     "bbox": [50, 40, 550, 60],
                     "text": "The LKH-5 delivers up to 35 m3/h at 60 Hz." * 6},
                    {"id": "p2-i1", "label": "table",
                     "bbox": [50, 80, 550, 200], "text": ""},
                ]
            ),
        )
        await store.write_gold_region_file(
            "lkh",
            2,
            [{"id": "r1", "kind": "table", "title": "Specs", "page": 2,
              "bbox": [50, 40, 550, 200],
              "member_item_ids": ["p2-i0", "p2-i1", "p2-ghost"]}],
        )

    asyncio.run(seed())
    out = asyncio.run(inspect_region(store, "lkh", "p2/r1"))
    members = out["members"]
    assert [m["item_id"] for m in members] == ["p2-i0", "p2-i1"]  # ghost skipped
    assert members[0]["kind"] == "text"
    assert members[0]["bbox"] == [50, 40, 550, 60]
    assert len(members[0]["text"]) == 120  # truncated
    assert members[1]["kind"] == "table"


def test_get_region_content_reconstructs_from_candidates_when_absent():
    store = MemoryDocStore()

    async def seed() -> None:
        await store.write_silver_artifact(
            "lkh",
            "pages/2.candidates.json",
            json.dumps(
                [
                    {
                        "id": "p2-i0",
                        "label": "table",
                        "bbox": [50, 480, 550, 410],
                        "text": "",
                        "cells": [
                            {"row": 0, "col": 0, "text": "Flow"},
                            {"row": 0, "col": 1, "text": "35 m3/h"},
                        ],
                    }
                ]
            ),
        )
        # A region with member_item_ids but no stored content.
        await store.write_gold_region_file(
            "lkh",
            2,
            [
                {
                    "id": "r1",
                    "kind": "table",
                    "title": "Table",
                    "page": 2,
                    "bbox": [50, 480, 550, 410],
                    "member_item_ids": ["p2-i0"],
                }
            ],
        )

    asyncio.run(seed())
    out = asyncio.run(get_region_content(store, "lkh", "p2/r1"))
    assert out is not None
    assert "35 m3/h" in out["content"]
