"""IngestService.derive_region — generic consumer side of a region producer.

Persists a region derived from an existing gold region, inheriting the
parent's source_ref and recording derived_from. Producer-agnostic; the
chart digitizer's chart_series is the first user.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.services import (
    AmbiguousRegionError,
    IngestService,
)
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


async def test_derive_region_synthesizes_ref_when_parent_stores_none():
    # Ordinary gold regions carry only a bbox, no source_ref; the derived
    # region must still point at the parent's page and bbox (#242 P2a).
    store = MemoryDocStore()
    await store.write_gold_region_file("lkh", 4, [
        {"id": "r1", "kind": "chart", "title": "Flow chart",
         "bbox": [56.5, 58.5, 252.8, 223.2]},
    ])
    svc = _service(store)

    await svc.derive_region("lkh", "r1", dict(CHART_SERIES))
    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    series = next(r for r in regs if r["kind"] == "chart_series")
    assert series["source_ref"] == {
        "slug": "lkh",
        "page": 4,
        "region_id": "r1",
        "bbox": [56.5, 58.5, 252.8, 223.2],
    }


async def test_derive_region_unknown_parent_raises():
    store = MemoryDocStore()
    await _seed_parent(store)
    svc = _service(store)
    with pytest.raises(ValueError, match="not found"):
        await svc.derive_region("lkh", "lkh:p9-nope", dict(CHART_SERIES))


async def test_derive_region_mints_next_free_id_when_omitted():
    # A producer that omits the id must not persist an unaddressable record
    # (#304): the consumer mints the next free r<n> on the parent's page.
    store = MemoryDocStore()
    await _seed_parent(store)  # page 4 holds "lkh:p4-r1" (trailing r1)
    svc = _service(store)

    region = dict(CHART_SERIES)
    del region["id"]
    out = await svc.derive_region("lkh", "lkh:p4-r1", region)
    assert out["region_id"] == "r2"

    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    stored = next(r for r in regs if r["kind"] == "chart_series")
    assert stored["id"] == "r2"

    # A second id-less derivation lands on the next free number.
    region2 = dict(CHART_SERIES)
    del region2["id"]
    out2 = await svc.derive_region("lkh", "lkh:p4-r1", region2)
    assert out2["region_id"] == "r3"


async def test_derive_region_explicit_id_still_wins():
    store = MemoryDocStore()
    await _seed_parent(store)
    svc = _service(store)
    out = await svc.derive_region("lkh", "lkh:p4-r1", dict(CHART_SERIES))
    assert out["region_id"] == "lkh:p4-series-b"


# ── page-ambiguous parent lookup (#287) ─────────────────────────────────────
#
# Region ids are only unique per page: `r1` exists on page 1 AND page 4 of
# the LKH datasheet. A bare parent id must never silently bind page 1's r1
# (the logo) when the caller means page 4's chart.


async def _seed_colliding_ids(store: MemoryDocStore) -> None:
    await store.write_gold_region_file("lkh", 1, [
        {"id": "r1", "kind": "logo", "title": "Alfa Laval logo",
         "bbox": [10.0, 10.0, 60.0, 30.0]},
    ])
    await store.write_gold_region_file("lkh", 4, [
        {"id": "r1", "kind": "chart", "title": "Flow chart",
         "bbox": [56.5, 58.5, 252.8, 223.2]},
    ])


async def test_derive_region_accepts_page_qualified_parent_token():
    store = MemoryDocStore()
    await _seed_colliding_ids(store)
    svc = _service(store)

    out = await svc.derive_region("lkh", "p4/r1", dict(CHART_SERIES))

    assert out["derived_from"] == "r1"
    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    series = next(r for r in regs if r["kind"] == "chart_series")
    # Provenance binds to page 4's chart, not page 1's logo.
    assert series["source_ref"]["page"] == 4
    assert series["source_ref"]["bbox"] == [56.5, 58.5, 252.8, 223.2]
    # Page 1 stays untouched.
    page1 = (await store.get_regions("lkh", page=1))["pages"][1]
    assert [r["kind"] for r in page1] == ["logo"]


async def test_derive_region_bare_ambiguous_parent_fails_with_pages():
    store = MemoryDocStore()
    await _seed_colliding_ids(store)
    svc = _service(store)

    with pytest.raises(AmbiguousRegionError) as excinfo:
        await svc.derive_region("lkh", "r1", dict(CHART_SERIES))

    err = excinfo.value
    assert err.region_id == "r1"
    assert err.pages == [1, 4]
    assert "p1/r1" in str(err)
    # Nothing was written on either page.
    for page in (1, 4):
        regs = (await store.get_regions("lkh", page=page))["pages"][page]
        assert all(r["kind"] != "chart_series" for r in regs)


async def test_derive_region_page_hint_misses_raises_not_found():
    store = MemoryDocStore()
    await _seed_colliding_ids(store)
    svc = _service(store)
    with pytest.raises(ValueError, match="not found"):
        await svc.derive_region("lkh", "p2/r1", dict(CHART_SERIES))


async def test_derive_region_bare_single_page_match_keeps_working():
    # Covered implicitly above, but pin the contract: a bare id that matches
    # exactly one page needs no qualification.
    store = MemoryDocStore()
    await _seed_colliding_ids(store)
    svc = _service(store)
    await store.write_gold_region_file("lkh", 4, [
        {"id": "r1", "kind": "chart", "title": "Flow chart",
         "bbox": [56.5, 58.5, 252.8, 223.2]},
        {"id": "r9", "kind": "table", "title": "Specs",
         "bbox": [1.0, 2.0, 3.0, 4.0]},
    ])

    out = await svc.derive_region("lkh", "r9", dict(CHART_SERIES))

    assert out["derived_from"] == "r9"
