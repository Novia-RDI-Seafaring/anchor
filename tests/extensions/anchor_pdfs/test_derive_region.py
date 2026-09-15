"""IngestService.derive_region — generic consumer side of a region producer.

Persists a region derived from an existing gold region, inheriting the
parent's source_ref and recording derived_from. Producer-agnostic; the
chart digitizer's chart_series is the first user.
"""
from __future__ import annotations

import hashlib

import pytest

from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content, inspect_region
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.extensions.anchor_pdfs.test_replacement_generations import harness, pipeline, submit_all


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
    assert out["derived_from"] == "p4/lkh:p4-r1"

    regs = (await store.get_regions("lkh", page=4))["pages"][4]
    series = [r for r in regs if r["kind"] == "chart_series"]
    assert len(series) == 1
    # the parent chart is still there; the derived region sits beside it
    assert any(r["kind"] == "chart" for r in regs)
    # provenance inherited from the parent
    assert series[0]["derived_from"] == "p4/lkh:p4-r1"
    assert series[0]["source_ref"]["page"] == 4
    # A legacy nested locator is not authority for missing canonical geometry.
    assert series[0]["source_ref"] == (await inspect_region(store, "lkh", "lkh:p4-r1"))["source_ref"]
    assert series[0]["source_ref"]["bbox"] is None


async def test_derive_region_unknown_parent_raises():
    store = MemoryDocStore()
    await _seed_parent(store)
    svc = _service(store)
    with pytest.raises(ValueError, match="not found"):
        await svc.derive_region("lkh", "lkh:p9-nope", dict(CHART_SERIES))


@pytest.mark.parametrize("kind", ["chart", "table", "text"])
async def test_ordinary_parent_uses_inspect_locator(kind):
    store = MemoryDocStore()
    await store.write_gold_region_file("lkh", 4, [{
        "id": "r1", "kind": kind, "page": 4,
        "bbox": [50, 100, 250, 300], "title": "Flow chart",
    }])
    parent = await inspect_region(store, "lkh", "r1")
    await _service(store).derive_region("lkh", "r1", dict(CHART_SERIES))
    regions = (await store.get_regions("lkh", 4))["pages"][4]
    child = next(r for r in regions if r["id"] == CHART_SERIES["id"])
    assert child["source_ref"] == parent["source_ref"]
    assert child["page"] == parent["page"]
    assert child["bbox"] == parent["bbox"]
    assert child["derived_from"] == "p4/r1"


@pytest.mark.parametrize("locator,page", [("p2/r1", 2), ("2/r1", 2), ("p1/r1", 1),
    ("r1", None), ("p3/r1", None), ("p2/missing", None), ("wrong/r1", None)])
async def test_inspect_and_derive_share_exact_locator(locator, page):
    store = MemoryDocStore()
    for p in (1, 2):
        await store.write_gold_region_file("lkh", p, [{
            "id": "r1", "kind": "text", "bbox": [p, 20, 200, 100],
        }])
    parent = await inspect_region(store, "lkh", locator)
    if page is None:
        assert parent is None
        assert await get_region_content(store, "lkh", locator) is None
        with pytest.raises(ValueError, match="not found|ambiguous"):
            await _service(store).derive_region("lkh", locator, dict(CHART_SERIES))
    else:
        assert parent["page"] == page
        result = await _service(store).derive_region("lkh", locator, dict(CHART_SERIES))
        assert result["derived_from"] == f"p{page}/r1"
        child = await inspect_region(store, "lkh", f"p{page}/{CHART_SERIES['id']}")
        assert child["bbox"] == parent["bbox"]


@pytest.mark.parametrize("override", [
    {"source_ref": {"slug": "other"}}, {"source_ref": {"page": 3}},
    {"slug": "other"}, {"page": 3}, {"source_ref": {"region_id": "other"}},
    {"source_ref": {"source_sha256": "old"}}, {"source_ref": {"generation_id": "old"}},
    {"coord_origin": "bottom-left"}, {"source_ref": "invalid"},
])
async def test_conflicting_source_override_is_rejected_without_writing(override):
    store = MemoryDocStore()
    await store.write_gold_region_file("lkh", 2, [{
        "id": "r1", "kind": "chart", "bbox": [50, 100, 250, 300],
    }])
    before = await store.get_regions("lkh")
    with pytest.raises(ValueError, match="source.*conflict|source_ref.*object"):
        await _service(store).derive_region("lkh", "p2/r1", {**CHART_SERIES, **override})
    assert await store.get_regions("lkh") == before


@pytest.mark.parametrize("lane", ["keyed", "harness"])
@pytest.mark.parametrize("memory", [False, True])
async def test_ingested_parent_chain_generation_restart_and_search(tmp_path, lane, memory):
    store = MemoryDocStore() if memory else FsDocStore(tmp_path)
    svc = pipeline(store, [["old page"], ["obsolete parent"]])
    await svc.ingest_pdf(b"old", "doc.pdf")
    old = store.snapshot("doc")
    pages = [["current parent"]]
    svc = pipeline(store, pages)
    if lane == "harness":
        session = harness(store, tmp_path, pages)
        order = await session.ingest_begin(b"current", "doc.pdf", force=True)
        await submit_all(session, order)
        assert (await session.ingest_finalize(order["session_id"]))["finalized"]
    else:
        await svc.ingest_pdf(b"current", "doc.pdf", force=True)
    assert await inspect_region(old, "doc", "p2/r1") is not None
    with pytest.raises(ValueError, match="not found"):
        await svc.derive_region("doc", "p2/r1", dict(CHART_SERIES))
    parent = await inspect_region(store, "doc", "p1/r1")
    document = (await store.get_index("doc"))["document"]
    source = parent["source_ref"]
    assert source["source_sha256"] == hashlib.sha256(b"current").hexdigest()
    assert source["generation_id"] == document["generation"]["id"]
    assert source["coord_origin"] == "top-left"
    old_source = (await inspect_region(old, "doc", "p1/r1"))["source_ref"]
    with pytest.raises(ValueError, match="conflicts"):
        await svc.derive_region("doc", "p1/r1", {**CHART_SERIES, "source_ref": old_source})
    await svc.derive_region("doc", "p1/r1", {
        **CHART_SERIES, "id": "child", "source_ref": {**source, "note": "producer note"},
    })
    child = await inspect_region(store, "doc", "p1/child")
    assert child["derived_from"] == "p1/r1"
    await svc.derive_region("doc", "p1/child", {**CHART_SERIES, "id": "grandchild"})
    grandchild = await inspect_region(store, "doc", "p1/grandchild")
    assert grandchild["derived_from"] == "p1/child"
    assert grandchild["bbox"] == child["bbox"] == parent["bbox"]
    for key in ("slug", "page", "source_sha256", "generation_id", "coord_origin"):
        assert grandchild["source_ref"][key] == child["source_ref"][key] == source[key]
    assert (await get_region_content(store, "doc", "p1/grandchild"))["source_ref"] == grandchild["source_ref"]
    await svc.embed_document("doc")
    hits = (await svc.search("LKH-85", k=100))["hits"]
    hit = next(h for h in hits if h["region_id"] == "grandchild")
    reader = store if memory else FsDocStore(tmp_path)
    assert await inspect_region(reader, hit["slug"], f"p{hit['page']}/{hit['region_id']}") == grandchild
    assert await inspect_region(old, "doc", "p1/child") is None


async def test_unknown_stored_origin_is_not_reinterpreted():
    store = MemoryDocStore()
    await store.write_gold_region_file("lkh", 2, [{
        "id": "old", "kind": "chart", "coord_origin": None, "bbox": [10, 200, 50, 100],
    }])
    await _service(store).derive_region("lkh", "p2/old", dict(CHART_SERIES))
    child = await inspect_region(store, "lkh", f"p2/{CHART_SERIES['id']}")
    assert child["source_ref"]["coord_origin"] is None
    assert child["bbox"] == [10, 200, 50, 100]
    assert "evidence" not in child
