"""IngestService.derive_region — generic consumer side of a region producer.

Persists a region derived from an existing gold region, inheriting the
parent's source_ref and recording derived_from. Producer-agnostic; the
chart digitizer's chart_series is the first user.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus


def _service(store: MemoryDocStore) -> IngestService:
    return IngestService(store=store, bus=MemoryEventBus(), extractor=object(), renderer=object())


CHART_SERIES = {
    "id": "lkh:p4-series-b",
    "kind": "chart_series",
    "title": "LKH-85 head vs flow",
    "content": {"data": {"x_label": "Q", "y_label": "H",
                         "series": [{"label": "LKH-85", "points": [[0, 94], [400, 50]]}]}},
}


async def _seed_parent(store: MemoryDocStore) -> None:
    await store.write_gold_region_file("lkh", 4, [
        {"id": "lkh:p4-r1", "kind": "chart", "title": "Flow chart",
         "source_ref": {"kind": "pdf-page-bbox", "page": 4, "bbox": [56.5, 783.4, 252.8, 605.7]}},
    ])


async def test_derive_region_inherits_provenance_and_persists():
    store = MemoryDocStore()
    await _seed_parent(store)
    svc = _service(store)

    out = await svc.derive_region("lkh", "lkh:p4-r1", dict(CHART_SERIES))
    assert out["region_id"] == "lkh:p4-series-b"
    assert out["derived_from"] == "lkh:p4-r1"

    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    series = [r for r in regs if r["kind"] == "chart_series"]
    assert len(series) == 1
    # the parent chart is still there; the derived region sits beside it
    assert any(r["kind"] == "chart" for r in regs)
    # provenance inherited from the parent
    assert series[0]["derived_from"] == "lkh:p4-r1"
    assert series[0]["source_ref"]["page"] == 4
    assert series[0]["source_ref"]["bbox"] == [56.5, 783.4, 252.8, 605.7]


async def test_derive_region_unknown_parent_raises():
    store = MemoryDocStore()
    await _seed_parent(store)
    svc = _service(store)
    with pytest.raises(ValueError, match="not found"):
        await svc.derive_region("lkh", "lkh:p9-nope", dict(CHART_SERIES))
