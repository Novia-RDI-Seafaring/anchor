"""Pointed extraction (anchor#132): selected regions/entities -> caller shape.

Deterministic core: a shape + region selection returns `data` filled from the
selected regions' gold cells, with a `provenance` entry per filled leaf and
the unmatched leaves reported in `unfilled` (never guessed). No model is
called; these tests run with no network / API key.
"""
from __future__ import annotations

import json

import pytest

from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
    PointedExtractionError,
    extract_pointed,
    fill_shape,
    resolve_selection,
)
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus


def _service(store: MemoryDocStore) -> IngestService:
    return IngestService(store=store, bus=MemoryEventBus(), extractor=object(), renderer=object())


async def _seed_lkh(store: MemoryDocStore) -> None:
    """A pump-datasheet-shaped doc: a spec table on p2, a chart on p4."""
    await store.write_silver_artifact(
        "lkh",
        "index.json",
        json.dumps({
            "document": {"title": "Alfa Laval LKH", "filename": "lkh.pdf", "page_count": 4},
            "outline": [],
        }),
    )
    # p2/r4 — a spec table with key/value cells.
    await store.write_gold_region_file("lkh", 2, [{
        "id": "r4",
        "kind": "table",
        "title": "Specifications",
        "page": 2,
        "bbox": [50, 480, 550, 410],
        "entities": ["LKH-5"],
        "cells": [
            {"row": 0, "col": 0, "text": "Model", "bbox": [55, 477, 200, 460]},
            {"row": 0, "col": 1, "text": "LKH-5", "bbox": [210, 477, 360, 460]},
            {"row": 1, "col": 0, "text": "Max inlet pressure", "bbox": [55, 455, 200, 438]},
            {"row": 1, "col": 1, "text": "600 kPa", "bbox": [210, 455, 360, 438]},
        ],
    }])
    # p3/r1 — an unrelated table (so page selection matters).
    await store.write_gold_region_file("lkh", 3, [{
        "id": "r1",
        "kind": "table",
        "title": "Other",
        "page": 3,
        "bbox": [10, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Weight", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "42 kg", "bbox": [80, 90, 140, 80]},
        ],
    }])
    await store.mark_gold_complete("lkh", {"mode": "keyed", "region_count": 3})


# ── Filling: provenance per filled leaf, unfilled for the rest ──────────────


async def test_fills_leaves_with_provenance_and_reports_unfilled():
    store = MemoryDocStore()
    await _seed_lkh(store)

    shape = {
        "model": "string",
        "max_inlet_pressure": "quantity",
        "connections": [{"size": "string", "type": "string"}],
    }
    out = await extract_pointed(
        store=store, slug="lkh", select={"regions": ["p2/r4"]}, shape=shape,
    )

    assert out["doc_slug"] == "lkh"
    assert out["data"]["model"] == "LKH-5"
    assert out["data"]["max_inlet_pressure"] == "600 kPa"
    # Every filled leaf has a provenance entry with a real source_ref.
    assert out["provenance"]["/model"] == {
        "slug": "lkh", "page": 2, "region_id": "r4",
        "bbox": [210.0, 477.0, 360.0, 460.0], "quote": "LKH-5",
    }
    assert out["provenance"]["/max_inlet_pressure"]["quote"] == "600 kPa"
    assert out["provenance"]["/max_inlet_pressure"]["bbox"] == [210.0, 455.0, 360.0, 438.0]
    # The array of objects the source did not cover is reported, not guessed.
    assert out["data"]["connections"] == []
    assert "/connections" in out["unfilled"]


async def test_unmatched_scalar_leaf_goes_to_unfilled_not_guessed():
    store = MemoryDocStore()
    await _seed_lkh(store)

    out = await extract_pointed(
        store=store, slug="lkh",
        select={"regions": ["p2/r4"]},
        shape={"model": "string", "flow_rate": "quantity"},
    )
    assert out["data"]["model"] == "LKH-5"
    assert out["data"]["flow_rate"] is None
    assert "/flow_rate" in out["unfilled"]
    assert "/flow_rate" not in out["provenance"]


async def test_number_and_bool_leaf_coercion():
    store = MemoryDocStore()
    await store.write_silver_artifact(
        "d", "index.json",
        json.dumps({"document": {"title": "D", "filename": "d.pdf", "page_count": 1}, "outline": []}),
    )
    await store.write_gold_region_file("d", 1, [{
        "id": "r1", "kind": "table", "page": 1, "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Stages", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "3", "bbox": [80, 90, 140, 80]},
            {"row": 1, "col": 0, "text": "Certified", "bbox": [10, 70, 60, 60]},
            {"row": 1, "col": 1, "text": "yes", "bbox": [80, 70, 140, 60]},
        ],
    }])
    await store.mark_gold_complete("d", {"mode": "keyed"})

    out = await extract_pointed(
        store=store, slug="d", select=None,
        shape={"stages": "number", "certified": "bool"},
    )
    assert out["data"]["stages"] == 3
    assert out["data"]["certified"] is True


# ── Selection: regions / pages / entity ─────────────────────────────────────


async def test_page_selection_scopes_to_the_page():
    store = MemoryDocStore()
    await _seed_lkh(store)

    regions = await resolve_selection(store=store, slug="lkh", select={"pages": [3]})
    assert {r["id"] for r in regions} == {"r1"}

    # The weight on p3 fills; the model on p2 does not (out of selection).
    out = await extract_pointed(
        store=store, slug="lkh", select={"pages": [3]},
        shape={"weight": "quantity", "model": "string"},
    )
    assert out["data"]["weight"] == "42 kg"
    assert out["data"]["model"] is None
    assert "/model" in out["unfilled"]


async def test_empty_select_uses_every_gold_region():
    store = MemoryDocStore()
    await _seed_lkh(store)
    out = await extract_pointed(
        store=store, slug="lkh", select=None,
        shape={"model": "string", "weight": "quantity"},
    )
    assert out["data"]["model"] == "LKH-5"
    assert out["data"]["weight"] == "42 kg"


async def test_entity_scoped_selection_picks_entity_region():
    store = MemoryDocStore()
    await _seed_lkh(store)

    # The entity 'LKH-5' is named on region r4 (entities + a cell); page 3 is
    # not about it. Entity scoping must pick up r4.
    regions = await resolve_selection(store=store, slug="lkh", select={"entity": "LKH-5"})
    assert "r4" in {r["id"] for r in regions}

    out = await extract_pointed(
        store=store, slug="lkh", select={"entity": "LKH-5"},
        shape={"model": "string", "max_inlet_pressure": "quantity"},
    )
    assert out["data"]["model"] == "LKH-5"
    assert out["provenance"]["/model"]["region_id"] == "r4"


# ── JSON Schema shape ───────────────────────────────────────────────────────


async def test_accepts_json_schema_shape():
    store = MemoryDocStore()
    await _seed_lkh(store)

    schema = {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "max_inlet_pressure": {"type": "string", "format": "quantity"},
        },
    }
    out = await extract_pointed(
        store=store, slug="lkh", select={"regions": ["p2/r4"]}, shape=schema,
    )
    assert out["data"]["model"] == "LKH-5"
    assert out["data"]["max_inlet_pressure"] == "600 kPa"
    assert out["provenance"]["/model"]["quote"] == "LKH-5"


# ── Nested objects ──────────────────────────────────────────────────────────


async def test_nested_object_leaves_get_pointer_provenance():
    store = MemoryDocStore()
    await store.write_silver_artifact(
        "t", "index.json",
        json.dumps({"document": {"title": "T", "filename": "t.pdf", "page_count": 1}, "outline": []}),
    )
    await store.write_gold_region_file("t", 1, [{
        "id": "r1", "kind": "table", "page": 1, "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "min", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "-10 C", "bbox": [80, 90, 140, 80]},
            {"row": 1, "col": 0, "text": "max", "bbox": [10, 70, 60, 60]},
            {"row": 1, "col": 1, "text": "140 C", "bbox": [80, 70, 140, 60]},
        ],
    }])
    await store.mark_gold_complete("t", {"mode": "keyed"})

    out = await extract_pointed(
        store=store, slug="t", select=None,
        shape={"temperature_range": {"min": "quantity", "max": "quantity"}},
    )
    assert out["data"]["temperature_range"] == {"min": "-10 C", "max": "140 C"}
    assert out["provenance"]["/temperature_range/min"]["quote"] == "-10 C"
    assert out["provenance"]["/temperature_range/max"]["quote"] == "140 C"


# ── Errors ──────────────────────────────────────────────────────────────────


async def test_unknown_slug_raises():
    store = MemoryDocStore()
    with pytest.raises(PointedExtractionError):
        await extract_pointed(store=store, slug="nope", select=None, shape={"x": "string"})


# ── Ambiguity is never guessed ──────────────────────────────────────────────


def test_ambiguous_label_across_regions_is_unfilled():
    # Two selected regions both have a "model" key with differing values; the
    # label is ambiguous, so it is left unfilled rather than guessed.
    regions = [
        {"id": "ra", "page": 1, "cells": [
            {"row": 0, "col": 0, "text": "Model", "bbox": [0, 1, 1, 0]},
            {"row": 0, "col": 1, "text": "A", "bbox": [1, 1, 2, 0]},
        ]},
        {"id": "rb", "page": 2, "cells": [
            {"row": 0, "col": 0, "text": "Model", "bbox": [0, 1, 1, 0]},
            {"row": 0, "col": 1, "text": "B", "bbox": [1, 1, 2, 0]},
        ]},
    ]
    data, provenance, unfilled = fill_shape({"model": "string"}, regions, slug="x")
    assert data["model"] is None
    assert "/model" in unfilled
    assert provenance == {}
