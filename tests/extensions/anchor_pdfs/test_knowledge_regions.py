"""Derived storage stays separate from source gold and its generation."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.ingest.coverage import (
    coverage_stats,
    synthesize_coverage_regions,
)
from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content, inspect_region
from anchor.extensions.anchor_pdfs.core.source_identity import SourceIdentityError
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline


@pytest.fixture(params=["fs", "memory"])
def store(request, tmp_path):
    return FsDocStore(tmp_path) if request.param == "fs" else MemoryDocStore()


def gold_bytes(store):
    if isinstance(store, FsDocStore):
        return {p.relative_to(store.gold): p.read_bytes()
                for p in store.gold.rglob("*.regions.json")}
    return deepcopy(store.snapshot("doc")._regions)


async def test_new_knowledge_survives_upsert_restart_chain_search_and_removal(store, tmp_path):
    service = pipeline(store, [["Source chart"]])
    await service.ingest_pdf(b"source", "doc.pdf")
    before = gold_bytes(store)
    region = {
        "id": "child", "kind": "chart_series", "title": "Derived curve",
        "content": {"points": [[0, 10], [1, 20]]},
        "series": [{"label": "Curve", "points": [[0, 10], [1, 20]]}],
        "source_ref": {"item_id": "p1-i0", "cell": {"row": 1, "col": 2}},
    }
    out = await service.derive_region("doc", "p1/r1", region)
    assert "knowledge" in out["path"]
    await service.derive_region("doc", "p1/r1", {**region, "title": "Updated curve"})
    await service.derive_region("doc", "p1/child", {
        "id": "grandchild", "kind": "calculated", "title": "Operating point",
    })
    assert gold_bytes(store) == before
    reader = FsDocStore(tmp_path) if isinstance(store, FsDocStore) else store
    child = await inspect_region(reader, "doc", "p1/child")
    assert child["title"] == "Updated curve"
    assert child["derived_from"] == "p1/r1"
    assert child["stored_source_ref"]["item_id"] == "p1-i0"
    assert child["stored_source_ref"]["cell"] == {"row": 1, "col": 2}
    assert child["data"]["series"] == region["series"]
    assert (await get_region_content(reader, "doc", "p1/child"))["content"] == region["content"]
    assert (await inspect_region(reader, "doc", "p1/grandchild"))["derived_from"] == "p1/child"
    assert [r["id"] for r in (await reader.get_gold_map("doc"))["pages"][1]] == [
        "r1", "child", "grandchild",
    ]
    assert [r["id"] for r in (await reader.get_source_regions("doc"))["pages"][1]] == ["r1"]
    reopened = pipeline(reader, [])
    assert await reopened.embed_document("doc") == 3
    assert {h["region_id"] for h in (await reopened.search("curve", k=10))["hits"]} == {
        "r1", "child", "grandchild",
    }
    assert (await reopened.remove_region("doc", "p1/child"))["embeddings_removed"] == 1
    assert await inspect_region(reader, "doc", "p1/child") is None
    assert await inspect_region(reader, "doc", "p1/grandchild") is not None
    assert gold_bytes(store) == before


async def test_legacy_upsert_and_remove_stay_in_gold_without_copying_knowledge(store):
    service = pipeline(store, [["Original"]])
    await service.ingest_pdf(b"source", "doc.pdf")
    original = (await store.get_regions("doc"))["pages"][1]
    await store.write_gold_region_file("doc", 1, [*original, {
        "id": "legacy", "kind": "chart_series", "title": "Legacy",
        "derived_from": "p1/r1", "series": [1, 2, 3],
    }])
    await service.derive_region("doc", "p1/r1", {"id": "new", "kind": "calculated"})
    out = await service.derive_region("doc", "p1/r1", {
        "id": "legacy", "kind": "chart_series", "series": [4, 5, 6],
    })
    assert "gold" in out["path"]
    assert (await inspect_region(store, "doc", "p1/legacy"))["data"]["series"] == [4, 5, 6]
    if isinstance(store, FsDocStore):
        path = store.knowledge / "doc/pages/1.regions.json"
        knowledge_before = path.read_bytes()
        assert [r["id"] for r in json.loads(knowledge_before)["regions"]] == ["new"]
    else:
        knowledge_before = deepcopy(store._knowledge)
        assert [r["id"] for r in store._knowledge["doc", 1]] == ["new"]
    assert (await service.remove_region("doc", "p1/legacy"))["removed"]
    assert [r["id"] for r in (await store.get_regions("doc"))["pages"][1]] == ["r1", "new"]
    if isinstance(store, FsDocStore):
        assert path.read_bytes() == knowledge_before
    else:
        assert store._knowledge == knowledge_before


async def test_generated_ids_scan_both_collections_and_removal_is_page_qualified(store):
    service = pipeline(store, [["Page one"], ["Page two"]])
    await service.ingest_pdf(b"source", "doc.pdf")
    await service.derive_region("doc", "p1/r1", {"id": "r2", "kind": "calculated", "title": "First"})
    assert (await service.derive_region("doc", "p1/r1", {"kind": "calculated", "title": "Next"}))["region_id"] == "r3"
    await service.derive_region("doc", "p2/r1", {"id": "r2", "kind": "calculated", "title": "Second"})
    await service.embed_document("doc")
    assert (await service.remove_region("doc", "p1/r2"))["embeddings_removed"] == 1
    assert await inspect_region(store, "doc", "p2/r2") is not None
    vectors = (await store.get_embeddings("doc"))["vectors"]
    assert (2, "r2") in {(v["page"], v["region_id"]) for v in vectors}
    assert (1, "r2") not in {(v["page"], v["region_id"]) for v in vectors}


async def test_knowledge_and_legacy_derived_cannot_satisfy_source_completeness(store):
    await store.write_gold_region_file("doc", 1, [{
        "id": "legacy", "kind": "calculated", "derived_from": "p1/missing",
    }])
    await store.add_derived_region("doc", {
        "id": "new", "page": 1, "kind": "calculated", "derived_from": "p1/missing",
    })
    await store.write_silver_artifact("doc", "ingest-report.json", json.dumps({
        "status": "success", "gold_complete": True, "region_count": 1,
    }))
    assert len((await store.get_regions("doc"))["pages"][1]) == 2
    assert not await store.has_gold("doc")
    assert await store.get_gold_map("doc") is None


def test_derived_membership_does_not_cover_source_silver():
    candidates = [{"id": "p1-i0", "label": "text", "text": "Source evidence",
                   "bbox": [10, 20, 100, 40]}]
    derived = [{"id": "r1", "kind": "calculated", "derived_from": "p1/parent",
                "member_item_ids": ["p1-i0"]}]
    assert coverage_stats(candidates, derived)["uncovered_items"] == 1
    extra = synthesize_coverage_regions(1, candidates, derived)
    assert len(extra) == 1 and extra[0]["member_item_ids"] == ["p1-i0"]


async def test_replacement_starts_empty_and_pinned_knowledge_stays_old(store, tmp_path):
    service = pipeline(store, [["Old source"]])
    await service.ingest_pdf(b"old", "doc.pdf")
    await service.derive_region("doc", "p1/r1", {"id": "old", "kind": "calculated"})
    old = store.snapshot("doc")
    await pipeline(store, [["New source"]]).ingest_pdf(b"new", "doc.pdf", force=True)
    assert await inspect_region(store, "doc", "p1/old") is None
    assert await inspect_region(old, "doc", "p1/old") is not None
    out = await pipeline(store, []).derive_region("doc", "p1/r1", {
        "id": "current", "kind": "calculated",
    })
    if isinstance(store, FsDocStore):
        generation = (await store.get_index("doc"))["document"]["generation"]["id"]
        assert str(store.knowledge / "doc/generations" / generation / "pages") in out["path"]
        assert await inspect_region(FsDocStore(tmp_path), "doc", "p1/old") is None
    assert await inspect_region(old, "doc", "p1/current") is None


@pytest.mark.parametrize("operation", ["derive", "remove"])
async def test_publication_during_knowledge_mutation_keeps_selected_generation(
    store, monkeypatch, operation,
):
    service = pipeline(store, [["Old source"]])
    await service.ingest_pdf(b"old", "doc.pdf")
    await service.derive_region("doc", "p1/r1", {"id": "child", "kind": "calculated"})
    old = store.snapshot("doc")
    entered, release = asyncio.Event(), asyncio.Event()
    name = "add_derived_region" if operation == "derive" else "remove_derived_region"
    method = getattr(type(store), name)

    async def paused(self, *args, **kwargs):
        entered.set()
        await release.wait()
        return await method(self, *args, **kwargs)

    monkeypatch.setattr(type(store), name, paused)
    work = asyncio.create_task(
        service.derive_region("doc", "p1/r1", {"id": "late", "kind": "calculated"})
        if operation == "derive" else service.remove_region("doc", "p1/child")
    )
    await asyncio.wait_for(entered.wait(), 3)
    try:
        await pipeline(store, [["New source"]]).ingest_pdf(b"new", "doc.pdf", force=True)
    finally:
        release.set()
    await work
    assert await inspect_region(store, "doc", "p1/late") is None
    assert await inspect_region(store, "doc", "p1/child") is None
    assert (await inspect_region(old, "doc", "p1/late") is not None) == (operation == "derive")
    assert (await inspect_region(old, "doc", "p1/child") is not None) == (operation == "derive")


async def test_publication_gold_membership_excludes_knowledge(store, monkeypatch):
    service = pipeline(store, [["Old source"]])
    await service.ingest_pdf(b"old", "doc.pdf")
    publish = store.publish_replacement

    async def with_knowledge(slug, token, pages):
        candidate = store.replacement(slug, token)
        await pipeline(candidate, []).derive_region("doc", "p1/r1", {
            "id": "child", "kind": "calculated",
        })
        await publish(slug, token, pages)

    monkeypatch.setattr(store, "publish_replacement", with_knowledge)
    await pipeline(store, [["New source"]]).ingest_pdf(b"new", "doc.pdf", force=True)
    assert await inspect_region(store, "doc", "p1/child") is not None
    if isinstance(store, FsDocStore):
        manifest = json.loads((store.silver / "doc/.current.json").read_text(encoding="utf-8"))
        assert manifest["gold"] == {"1": ["r1"]}
    assert [r["id"] for r in (await store.get_source_regions("doc"))["pages"][1]] == ["r1"]


async def test_candidate_knowledge_cannot_validate_missing_source_embedding_membership(store, monkeypatch):
    service = pipeline(store, [["Old source"]])
    await service.ingest_pdf(b"old", "doc.pdf")
    publish = store.publish_replacement

    async def missing_source(slug, token, pages):
        candidate = store.replacement(slug, token)
        await candidate.write_gold_region_file("doc", 1, [])
        await candidate.add_derived_region("doc", {
            "id": "r1", "page": 1, "kind": "calculated", "derived_from": "p1/missing",
        })
        await publish(slug, token, pages)

    monkeypatch.setattr(store, "publish_replacement", missing_source)
    with pytest.raises(SourceIdentityError, match="obsolete regions"):
        await pipeline(store, [["New source"]]).ingest_pdf(b"new", "doc.pdf", force=True)
    assert "Old source" in await store.get_page_text("doc", 1)
