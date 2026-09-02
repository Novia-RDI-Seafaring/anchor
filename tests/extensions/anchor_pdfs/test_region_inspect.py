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
