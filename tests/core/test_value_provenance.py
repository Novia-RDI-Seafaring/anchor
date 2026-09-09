from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.source_ref_resolve import resolve_source_ref
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_uses_matching_gold_cell_bbox():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 2, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 2,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "Value", "bbox": [80, 90, 140, 80]},
        ],
    }])
    data = {
        "rows": [{
            "key": "Field",
            "value": "Value",
            "source_ref": {"slug": "doc", "page": 2, "region_id": "r1", "bbox": [0, 100, 200, 0]},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"]["bbox"] == [80.0, 90.0, 140.0, 80.0]
    # #242 P2c: the matched cell is recorded as a selector alongside the
    # cached bbox, so resolve_source_ref can re-answer from stored geometry.
    assert enriched["rows"][0]["source_ref"]["cell"] == {"row": 0, "col": 1}


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_accepts_value_with_unit_suffix():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 1,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Length", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "42", "bbox": [80, 90, 140, 80]},
        ],
    }])
    data = {
        "source_doc_slug": "doc",
        "rows": [{
            "key": "Length",
            "value": "42 mm",
            "source_region_id": "r1",
            "source_ref": {"page": 1, "bbox": [0, 100, 200, 0]},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"]["bbox"] == [80.0, 90.0, 140.0, 80.0]


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_uses_key_to_disambiguate_duplicate_values():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 1,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "First", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "Shared", "bbox": [80, 90, 140, 80]},
            {"row": 1, "col": 0, "text": "Second", "bbox": [10, 70, 60, 60]},
            {"row": 1, "col": 1, "text": "Shared", "bbox": [80, 70, 140, 60]},
        ],
    }])
    data = {
        "source_doc_slug": "doc",
        "source_region_id": "r1",
        "rows": [{
            "key": "Second",
            "value": "Shared",
            "source_ref": {"page": 1},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"] == {
        "slug": "doc",
        "page": 1,
        "region_id": "r1",
        "bbox": [80.0, 70.0, 140.0, 60.0],
        "cell": {"row": 1, "col": 1},
    }


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_accepts_row_level_region_id():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 1,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "Result", "bbox": [80, 90, 140, 80]},
        ],
    }])
    data = {
        "source_doc_slug": "doc",
        "rows": [{
            "key": "Field",
            "value": "Result",
            "source_region_id": "r1",
            "source_ref": {"page": 1, "bbox": [0, 100, 200, 0]},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched["rows"][0]["source_ref"] == {
        "slug": "doc",
        "page": 1,
        "region_id": "r1",
        "bbox": [80.0, 90.0, 140.0, 80.0],
        "cell": {"row": 0, "col": 1},
    }


@pytest.mark.asyncio
async def test_enrich_spec_row_source_refs_leaves_ambiguous_values_unchanged():
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 1, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 1,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Shared", "bbox": [10, 90, 60, 80]},
            {"row": 1, "col": 0, "text": "Shared", "bbox": [10, 70, 60, 60]},
        ],
    }])
    data = {
        "rows": [{
            "key": "Unknown",
            "value": "Shared",
            "source_ref": {"slug": "doc", "page": 1, "region_id": "r1", "bbox": [0, 100, 200, 0]},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)

    assert enriched is data


@pytest.mark.asyncio
async def test_recorded_cell_selector_round_trips_through_the_resolver():
    """Writer + resolver contract (#242 P2c): the `cell` the enrichment

    records is exactly what `resolve_source_ref` needs to re-answer with
    the same cell bbox at `precision == "cell"`.
    """
    store = MemoryDocStore()
    await store.write_gold_region_file("doc", 2, [{
        "id": "r1",
        "kind": "table",
        "title": "Data",
        "page": 2,
        "bbox": [0, 100, 200, 0],
        "cells": [
            {"row": 0, "col": 0, "text": "Field", "bbox": [10, 90, 60, 80]},
            {"row": 0, "col": 1, "text": "Value", "bbox": [80, 90, 140, 80]},
        ],
    }])
    data = {
        "rows": [{
            "key": "Field",
            "value": "Value",
            "source_ref": {"slug": "doc", "page": 2, "region_id": "r1", "bbox": [0, 100, 200, 0]},
        }],
    }

    enriched = await enrich_spec_row_source_refs(data, store)
    ref = enriched["rows"][0]["source_ref"]
    assert ref["cell"] == {"row": 0, "col": 1}

    resolved = await resolve_source_ref(store, "doc", ref)
    assert resolved is not None
    assert resolved["precision"] == "cell"
    assert resolved["bbox"] == ref["bbox"] == [80.0, 90.0, 140.0, 80.0]
