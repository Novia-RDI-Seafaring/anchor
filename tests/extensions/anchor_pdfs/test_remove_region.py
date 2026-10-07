"""IngestService.remove_region — the cleanup half of derive_region (#304).

Only regions carrying ``derived_from`` may be removed; model-extracted gold
is the ground truth of an ingest pass and is refused. Removal also drops the
region's vector from the embedding index so search stays consistent.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.services import (
    IngestService,
    RegionNotRemovableError,
)
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus


def _service(store: MemoryDocStore) -> IngestService:
    return IngestService(store=store, bus=MemoryEventBus(), extractor=object(), renderer=object())


async def _seed(store: MemoryDocStore) -> None:
    await store.write_gold_region_file("lkh", 4, [
        {"id": "r1", "kind": "chart", "title": "Flow chart",
         "bbox": [56.5, 58.5, 252.8, 223.2]},
        {"id": "r2", "kind": "chart_series", "title": "Digitized series",
         "derived_from": "r1",
         "source_ref": {"slug": "lkh", "page": 4, "region_id": "r1",
                        "bbox": [56.5, 58.5, 252.8, 223.2]}},
    ])


async def test_remove_region_deletes_derived_record():
    store = MemoryDocStore()
    await _seed(store)
    svc = _service(store)

    out = await svc.remove_region("lkh", "r2")
    assert out == {
        "slug": "lkh",
        "page": 4,
        "region_id": "r2",
        "removed": True,
        "derived_from": "r1",
        "embeddings_removed": 0,
    }
    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    assert [r["id"] for r in regs] == ["r1"]  # the parent survives


async def test_remove_region_accepts_page_prefixed_token():
    store = MemoryDocStore()
    await _seed(store)
    svc = _service(store)
    out = await svc.remove_region("lkh", "p4/r2")
    assert out["removed"] is True and out["page"] == 4


async def test_remove_region_refuses_model_extracted_gold():
    store = MemoryDocStore()
    await _seed(store)
    svc = _service(store)
    with pytest.raises(RegionNotRemovableError, match="model-extracted"):
        await svc.remove_region("lkh", "r1")
    # Nothing was touched.
    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    assert {r["id"] for r in regs} == {"r1", "r2"}


async def test_remove_region_unknown_raises_value_error():
    store = MemoryDocStore()
    await _seed(store)
    svc = _service(store)
    with pytest.raises(ValueError, match="not found"):
        await svc.remove_region("lkh", "r9")


async def test_remove_region_drops_embedding_vector():
    store = MemoryDocStore()
    await _seed(store)
    await store.write_embeddings("lkh", {
        "embed_model": "fake", "dim": 2,
        "vectors": [
            {"page": 4, "region_id": "r1", "text": "chart", "vector": [0.1, 0.2]},
            {"page": 4, "region_id": "r2", "text": "series", "vector": [0.3, 0.4]},
        ],
    })
    svc = _service(store)

    out = await svc.remove_region("lkh", "r2")
    assert out["embeddings_removed"] == 1
    payload = await store.get_embeddings("lkh")
    assert [v["region_id"] for v in payload["vectors"]] == ["r1"]
