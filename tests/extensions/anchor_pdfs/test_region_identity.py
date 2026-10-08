"""Same-page identity is validated before gold or embeddings become current."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content, inspect_region
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import (
    ItemRegions,
    harness,
    pipeline,
    published,
    submit_all,
)
from tests.fixtures.fakes import FakeEmbedder


class DuplicateRegions(ItemRegions):
    async def extract_page(self, *, page_no, **kwargs):
        regions = await super().extract_page(page_no=page_no, **kwargs)
        if page_no == 2:
            return [regions[0], {**deepcopy(regions[0]), "title": "Conflicting B"}]
        return regions


class RecordingEmbedder(FakeEmbedder):
    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return await super().embed(texts)


@pytest.mark.parametrize("memory", [False, True])
async def test_keyed_duplicate_candidate_is_rejected(tmp_path, memory):
    store = MemoryDocStore() if memory else FsDocStore(tmp_path)
    embedder = RecordingEmbedder()
    svc = pipeline(store, [["Page A"], ["Page B"]], region_extractor=DuplicateRegions(), embedder=embedder)
    with pytest.raises(ValueError, match="duplicate region id 'r1' on page 2"):
        await svc.ingest_pdf(b"source", "doc.pdf")
    assert not await store.has_gold("doc")
    assert not (await store.get_regions("doc"))["pages"]
    assert await store.get_embeddings("doc") is None
    assert embedder.calls == []


async def test_harness_finalization_revalidates_persisted_page_identity(tmp_path):
    store = FsDocStore(tmp_path)
    svc = harness(store, tmp_path, [["A"], ["B"]])
    order = await svc.ingest_begin(b"source", "doc.pdf")
    sid = order["session_id"]
    await submit_all(svc, order)
    # Persisted session artifacts can outlive the submit validator/version.
    payload = json.loads(await svc.sessions.read_text(sid, "gold/pages/2.regions.json"))
    payload["regions"].append(deepcopy(payload["regions"][0]))
    await svc.sessions.write_text(sid, "gold/pages/2.regions.json", json.dumps(payload))
    result = await svc.ingest_finalize(sid)
    assert not result["finalized"]
    assert result["errors"][0]["message"] == "duplicate region id 'r1' on page 2"
    assert (await svc.ingest_status(sid))["state"] == "open"
    assert not await store.has_gold("doc")
    assert not (await store.get_regions("doc"))["pages"]
    assert await store.get_embeddings("doc") is None


@pytest.mark.parametrize("lane", ["keyed", "harness", "harness-staged"])
@pytest.mark.parametrize("memory", [False, True])
async def test_invalid_replacement_preserves_complete_generation_and_search(tmp_path, lane, memory):
    store = MemoryDocStore() if memory else FsDocStore(tmp_path)
    pages = [["OLD page one"], ["OLD page two"]]
    for source in (b"A", b"B"):
        await pipeline(store, pages).ingest_pdf(source, "doc.pdf", force=True)
    before = await published(store)
    assert before["index"]["document"]["generation"]["id"]
    hits_before = await pipeline(store, pages).search("OLD", k=100)
    embedder = RecordingEmbedder()
    if lane == "keyed":
        svc = pipeline(store, [["NEW one"], ["NEW two"]], region_extractor=DuplicateRegions(), embedder=embedder)
        with pytest.raises(ValueError, match="duplicate region id 'r1' on page 2"):
            await svc.ingest_pdf(b"C", "doc.pdf", force=True)
    else:
        svc = harness(store, tmp_path, [["NEW one"], ["NEW two"]], embedder=embedder)
        order = await svc.ingest_begin(b"C", "doc.pdf", force=True)
        sid = order["session_id"]
        if lane == "harness":
            first = await svc.ingest_submit_page(sid, 1, regions=[{
                "id": "r1", "kind": "text", "title": "NEW one", "member_item_ids": ["p1-i0"],
            }])
            assert first["accepted"]
            row = {"id": "r1", "kind": "text", "title": "NEW two", "member_item_ids": ["p2-i0"]}
            verdict = await svc.ingest_submit_page(sid, 2, regions=[row, deepcopy(row)])
            assert not verdict["accepted"]
            assert verdict["errors"][0]["message"] == "duplicate region id 'r1' on page 2"
        else:
            await submit_all(svc, order)
            raw = json.loads(await svc.sessions.read_text(sid, "gold/pages/2.regions.json"))
            raw["regions"].append(deepcopy(raw["regions"][0]))
            await svc.sessions.write_text(sid, "gold/pages/2.regions.json", json.dumps(raw))
        assert not (await svc.ingest_finalize(sid))["finalized"]
    assert embedder.calls == []
    for reader in (store, store if memory else FsDocStore(tmp_path)):
        assert await published(reader) == before
        assert await pipeline(reader, pages).search("OLD", k=100) == hits_before
        for page in (1, 2):
            assert "OLD" in (await inspect_region(reader, "doc", f"p{page}/r1"))["title"]


@pytest.mark.parametrize("lane", ["keyed", "harness"])
async def test_cross_page_repeats_search_and_inspect_exactly(tmp_path, lane):
    store = FsDocStore(tmp_path)
    pages = [["Page one content"], ["Page two content"]]
    if lane == "keyed":
        await pipeline(store, pages).ingest_pdf(b"A", "doc.pdf")
    else:
        svc = harness(store, tmp_path, pages)
        order = await svc.ingest_begin(b"A", "doc.pdf")
        await submit_all(svc, order)
        assert (await svc.ingest_finalize(order["session_id"]))["finalized"]
    assert await inspect_region(store, "doc", "r1") is None
    hits = (await pipeline(store, pages).search("content", k=100))["hits"]
    assert {(hit["page"], hit["region_id"]) for hit in hits} == {(1, "r1"), (2, "r1")}
    for hit in hits:
        locator = f"p{hit['page']}/{hit['region_id']}"
        region = await inspect_region(FsDocStore(tmp_path), hit["slug"], locator)
        assert hit["text"] == region["title"] == region["content"]
        assert (await get_region_content(store, hit["slug"], locator))["content"] == hit["text"]


async def test_legacy_duplicate_records_are_not_silently_repaired(tmp_path):
    store = FsDocStore(tmp_path)
    regions = [{"id": "r1", "kind": "text", "title": title, "bbox": [10, 20, 100, 30]} for title in ("A", "B")]
    await store.write_gold_region_file("doc", 2, regions)
    assert await inspect_region(store, "doc", "p2/r1") is None
    assert await get_region_content(store, "doc", "p2/r1") is None
    assert (await FsDocStore(tmp_path).get_regions("doc", 2))["pages"][2] == regions


@pytest.mark.parametrize("memory", [False, True])
async def test_publication_rejects_duplicate_persisted_candidate(tmp_path, memory, monkeypatch):
    store = MemoryDocStore() if memory else FsDocStore(tmp_path)
    await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
    before = await published(store)
    publish = store.publish_replacement
    pending = []

    async def pause_publication(slug, generation, pages):
        pending.append((slug, generation, pages))
        raise RuntimeError("interrupted before publication")

    monkeypatch.setattr(store, "publish_replacement", pause_publication)
    with pytest.raises(RuntimeError, match="interrupted before publication"):
        await pipeline(store, [["NEW one"], ["NEW two"]]).ingest_pdf(b"B", "doc.pdf", force=True)
    slug, generation, pages = pending[0]
    candidate = store.replacement(slug, generation)
    regions = (await candidate.get_regions(slug, 2))["pages"][2]
    await candidate.write_gold_region_file(slug, 2, [*regions, deepcopy(regions[0])])
    with pytest.raises(ValueError, match="duplicate region id 'r1' on page 2"):
        await publish(slug, generation, pages)
    assert await published(store if memory else FsDocStore(tmp_path)) == before
