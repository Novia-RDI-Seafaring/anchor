"""Authoritative document replacement through the supported ingest services."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.region_inspect import get_region_content, inspect_region
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakeEmbedder, FakePdfExtractor, FakePdfRenderer


class ItemRegions:
    async def extract_page(self, *, page_no, docling_items, **kwargs):
        return [{"id": f"r{i}", "kind": "text", "page": page_no,
                 "title": item["text"], "bbox": item["bbox"]}
                for i, item in enumerate(docling_items, 1)]


def pipeline(store, pages, *, embedder=None, extractor=None, region_extractor=None):
    items = [{"label": "text", "page": page, "text": text,
              "bbox": [20, 30 + i * 40, 300, 50 + i * 40]}
             for page, texts in enumerate(pages, 1) for i, text in enumerate(texts)]
    return IngestService(store, MemoryEventBus(),
                         extractor=extractor or FakePdfExtractor({"items": items}),
                         renderer=FakePdfRenderer(len(pages)),
                         region_extractor=region_extractor or ItemRegions(),
                         embedder=embedder or FakeEmbedder(), embed_model_id="test")


@pytest.mark.parametrize("memory", [False, True])
def test_forced_shrinking_replacement_removes_obsolete_members(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"source A", "same.pdf", slug="doc")
        await pipeline(store, [["REPLACEMENT PAGE"]]).ingest_pdf(b"source B", "same.pdf", slug="doc", force=True)
        assert await store.get_page_text("doc", 2) is None
        assert set((await store.get_regions("doc"))["pages"]) == {1}
        assert {v["page"] for v in (await store.get_embeddings("doc"))["vectors"]} == {1}
        if not memory:
            assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"source B"
    asyncio.run(run())


def harness(store, root, pages, *, embedder=None):
    keyed = pipeline(store, pages, embedder=embedder)
    return IngestSessionService(store, FsIngestSessionStore(root), keyed.bus,
                                extractor=keyed.extractor, renderer=keyed.renderer,
                                embedder=keyed.embedder, embed_model_id="test")


async def submit_all(svc, order):
    for page in order["pages"]:
        p = page["page"]
        work = await svc.ingest_get_page(order["session_id"], p)
        verdict = await svc.ingest_submit_page(order["session_id"], p, regions=[
            {"id": f"r{i}", "kind": "text", "title": c["text"], "member_item_ids": [c["id"]]}
            for i, c in enumerate(work["candidates"], 1)
        ])
        assert verdict["accepted"], verdict


def test_harness_replacement_stays_private_until_finalize_and_survives_restart(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"source A", "same.pdf", slug="doc")
        svc = harness(store, tmp_path, [["REPLACEMENT PAGE"]])
        order = await svc.ingest_begin(b"source B", "same.pdf", slug="doc", force=True)
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"source A"
        assert "CURRENT PAGE" in await store.get_page_text("doc", 1)
        await submit_all(svc, order)
        restarted = harness(FsDocStore(tmp_path), tmp_path, [["REPLACEMENT PAGE"]])
        assert (await restarted.ingest_finalize(order["session_id"]))["finalized"]
        reader = FsDocStore(tmp_path)
        assert await reader.get_page_text("doc", 2) is None
        assert set((await reader.get_regions("doc"))["pages"]) == {1}
        assert {v["page"] for v in (await reader.get_embeddings("doc"))["vectors"]} == {1}
        assert (await reader.get_raw_pdf_path("doc")).read_bytes() == b"source B"
    asyncio.run(run())


@pytest.mark.parametrize("old,new", [(2, 1), (3, 2), (1, 2), (2, 2)])
@pytest.mark.parametrize("lane", ["keyed", "harness"])
def test_replacement_is_a_complete_page_and_region_set(tmp_path, old, new, lane):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [[f"OLD {p}", "REMOVE REGION"] for p in range(old)]).ingest_pdf(b"A", "doc.pdf")
        pages = [[f"NEW {p}"] for p in range(new)]
        if lane == "keyed":
            await pipeline(store, pages).ingest_pdf(b"B", "doc.pdf", force=True)
        else:
            svc = harness(store, tmp_path, pages)
            order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
            await submit_all(svc, order)
            assert (await svc.ingest_finalize(order["session_id"]))["finalized"]
        for reader in (store, FsDocStore(tmp_path)):
            current = set(range(1, new + 1))
            assert (await reader.get_index("doc"))["document"]["page_count"] == new
            assert set((await reader.get_regions("doc"))["pages"]) == current
            assert await inspect_region(reader, "doc", "p1/r2") is None
            assert await get_region_content(reader, "doc", "p1/r2") is None
            for page in range(new + 1, old + 1):
                assert await reader.get_page_text("doc", page) is None
                assert await reader.get_page_candidates("doc", page) is None
                assert await reader.get_page_image_path("doc", page) is None
                assert await inspect_region(reader, "doc", f"p{page}/r1") is None
                assert await get_region_content(reader, "doc", f"p{page}/r1") is None
            vectors = (await reader.get_embeddings("doc"))["vectors"]
            assert {(v["page"], v["region_id"]) for v in vectors} == {(p, "r1") for p in current}
            assert all("OLD" not in v["text"] and "REMOVE" not in v["text"] for v in vectors)
            hits = (await pipeline(reader, pages).search("REMOVE REGION", k=100))["hits"]
            assert all("OLD" not in h["text"] and "REMOVE" not in h["text"] for h in hits)
    asyncio.run(run())


async def published(store):
    return deepcopy({"index": await store.get_index("doc"), "gold": await store.get_gold_map("doc"),
                     "embeddings": await store.get_embeddings("doc"),
                     "text": [await store.get_page_text("doc", p) for p in range(1, 4)]})


class BrokenExtractor:
    async def extract(self, *args, **kwargs):
        raise RuntimeError("controlled extraction failure")


class BrokenGold(ItemRegions):
    async def extract_page(self, *, page_no, **kwargs):
        if page_no == 2:
            raise RuntimeError("controlled gold failure")
        return await super().extract_page(page_no=page_no, **kwargs)


class BrokenEmbedder:
    async def embed(self, texts):
        raise RuntimeError("controlled embedding failure")


@pytest.mark.parametrize("stage", ["extractor", "region_extractor", "embedder"])
def test_failed_replacement_keeps_old_complete_generation(tmp_path, stage):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        failure = {"extractor": BrokenExtractor(), "region_extractor": BrokenGold(), "embedder": BrokenEmbedder()}[stage]
        with pytest.raises(RuntimeError, match="controlled"):
            await pipeline(store, [["NEW 1"], ["NEW 2"]], **{stage: failure}).ingest_pdf(b"B", "doc.pdf", force=True)
        assert await published(FsDocStore(tmp_path)) == before
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"A"
    asyncio.run(run())


class PausedEmbedder(FakeEmbedder):
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts):
        self.entered.set()
        await self.release.wait()
        return await super().embed(texts)


def test_readers_during_replacement_see_old_complete_then_new_complete(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        pause = PausedEmbedder()
        work = asyncio.create_task(pipeline(store, [["NEW"]], embedder=pause).ingest_pdf(b"B", "doc.pdf", force=True))
        await asyncio.wait_for(pause.entered.wait(), 3)
        try:
            assert await published(FsDocStore(tmp_path)) == before
            hits = (await pipeline(store, []).search("REMOVE ME"))["hits"]
            assert any("REMOVE ME" in h["text"] for h in hits)
        finally:
            pause.release.set()
        await work
        assert await store.get_page_text("doc", 2) is None
    asyncio.run(run())


def test_late_embedding_result_cannot_write_old_members_into_new_generation(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        pause = PausedEmbedder()
        work = asyncio.create_task(pipeline(store, [], embedder=pause).embed_document("doc"))
        await asyncio.wait_for(pause.entered.wait(), 3)
        try:
            await pipeline(store, [["NEW"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        finally:
            pause.release.set()
        await work
        assert {v["page"] for v in (await store.get_embeddings("doc"))["vectors"]} == {1}
    asyncio.run(run())


def test_finalize_recovers_after_publication_without_rewriting_current_data(tmp_path, monkeypatch):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["CURRENT PAGE"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        svc = harness(store, tmp_path, [["NEW"]])
        order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
        await submit_all(svc, order)
        save = svc._save_session

        async def interrupt_bookkeeping(session):
            if session["state"] == "published":
                raise RuntimeError("crash after publication")
            await save(session)

        monkeypatch.setattr(svc, "_save_session", interrupt_bookkeeping)
        with pytest.raises(RuntimeError, match="crash after publication"):
            await svc.ingest_finalize(order["session_id"])
        before = await published(store)
        restarted = harness(FsDocStore(tmp_path), tmp_path, [["NEW"]], embedder=BrokenEmbedder())
        result = await restarted.ingest_finalize(order["session_id"])
        assert result["finalized"]
        assert await published(FsDocStore(tmp_path)) == before
    asyncio.run(run())


def test_missing_current_generation_index_never_uses_pending_bronze_receipt(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        await pipeline(store, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        await store.stash_bronze(b"C", "doc.pdf", slug="doc")
        pointer = json.loads((tmp_path / "silver/doc/.current.json").read_text(encoding="utf-8"))
        (tmp_path / "silver/doc/generations" / pointer["generation"] / "index.json").unlink()
        with pytest.raises(ValueError, match="generation|metadata"):
            await FsDocStore(tmp_path).get_raw_pdf_path("doc")
    asyncio.run(run())


def test_initial_harness_session_cannot_overwrite_a_later_replacement(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        svc = harness(store, tmp_path, [["A"]])
        order = await svc.ingest_begin(b"A", "doc.pdf")
        await submit_all(svc, order)
        await pipeline(store, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        before = await published(store)
        with pytest.raises(ValueError, match="superseded"):
            await svc.ingest_finalize(order["session_id"])
        assert await published(store) == before
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["gold", "embedding"])
def test_failed_harness_finalization_keeps_old_generation(tmp_path, monkeypatch, failure):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        svc = harness(store, tmp_path, [["B"]], embedder=BrokenEmbedder() if failure == "embedding" else None)
        order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
        await submit_all(svc, order)
        if failure == "gold":
            original = svc.sessions.read_text

            async def missing_page(sid, name):
                return None if name.startswith("gold/pages/") else await original(sid, name)

            monkeypatch.setattr(svc.sessions, "read_text", missing_page)
        with pytest.raises((ValueError, RuntimeError)):
            await svc.ingest_finalize(order["session_id"])
        assert await published(FsDocStore(tmp_path)) == before
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"A"
    asyncio.run(run())


def test_interrupted_pointer_publication_keeps_old_generation(tmp_path, monkeypatch):
    import os

    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        replace = os.replace

        def interrupted(source, target):
            if target.name == ".current.json":
                raise OSError("controlled publication interruption")
            return replace(source, target)

        monkeypatch.setattr(os, "replace", interrupted)
        with pytest.raises(OSError, match="controlled"):
            await pipeline(store, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        assert await published(FsDocStore(tmp_path)) == before
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"A"
    asyncio.run(run())


def test_concurrent_finalizers_cannot_mutate_a_published_candidate(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        pause = PausedEmbedder()
        first = harness(store, tmp_path, [["B"]], embedder=pause)
        order = await first.ingest_begin(b"B", "doc.pdf", force=True)
        await submit_all(first, order)
        work = asyncio.create_task(first.ingest_finalize(order["session_id"]))
        await asyncio.wait_for(pause.entered.wait(), 3)
        second = harness(FsDocStore(tmp_path), tmp_path, [["B"]], embedder=BrokenEmbedder())
        other = asyncio.create_task(second.ingest_finalize(order["session_id"]))
        pause.release.set()
        assert (await work)["finalized"]
        assert (await other)["error"] == "session already published"
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"B"
        assert {v["page"] for v in (await store.get_embeddings("doc"))["vectors"]} == {1}
    asyncio.run(run())


def test_superseded_candidate_cannot_publish_over_newer_generation(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        svc = harness(store, tmp_path, [["B"]])
        order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
        await submit_all(svc, order)
        await pipeline(store, [["C"]]).ingest_pdf(b"C", "doc.pdf", force=True)
        before = await published(store)
        with pytest.raises(ValueError, match="superseded"):
            await svc.ingest_finalize(order["session_id"])
        assert await published(store) == before
    asyncio.run(run())


def test_source_only_replacement_does_not_keep_or_rebuild_old_embeddings(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        svc = pipeline(store, [["B"]])
        await svc.ingest_pdf(b"B", "doc.pdf", force=True, regions=False)
        assert await store.get_gold_map("doc") is None
        assert await store.get_embeddings("doc") is None
        assert await svc.embed_document("doc") == 0
        assert (await svc.search("REMOVE ME"))["hits"] == []
    asyncio.run(run())


def test_replacement_membership_includes_rendered_pages_without_text_items(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        svc = harness(store, tmp_path, [["B"], []])
        order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
        assert order["page_count"] == 2
        assert [p["page"] for p in order["pages"]] == [1, 2]
        await submit_all(svc, order)
        assert (await svc.ingest_finalize(order["session_id"]))["finalized"]
        index = await store.get_index("doc")
        assert index["document"]["generation"]["pages"] == [1, 2]
        assert index["document"]["page_count"] == 2
        assert await store.get_page_text("doc", 2) == ""
        assert await store.get_raw_pdf_path("doc", page=2) is not None
        assert await store.get_raw_pdf_path("doc", page=3) is None
    asyncio.run(run())


def test_abort_and_finalize_have_one_serialized_outcome(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        pause = PausedEmbedder()
        svc = harness(store, tmp_path, [["B"]], embedder=pause)
        order = await svc.ingest_begin(b"B", "doc.pdf", force=True)
        await submit_all(svc, order)
        finalizing = asyncio.create_task(svc.ingest_finalize(order["session_id"]))
        await asyncio.wait_for(pause.entered.wait(), 3)
        aborting = asyncio.create_task(svc.ingest_abort(order["session_id"]))
        await asyncio.sleep(0.01)
        pause.release.set()
        assert (await finalizing)["finalized"]
        result = await aborting
        assert result["aborted"] is False
        assert (await svc.ingest_status(order["session_id"]))["state"] == "published"
    asyncio.run(run())


def test_publish_rejects_incomplete_candidate_before_switching_source(tmp_path):
    from anchor.extensions.anchor_pdfs.core.source_identity import original_source

    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        await store.stash_bronze(b"B", "doc.pdf", slug="doc")
        token = await store.begin_replacement("doc", [1])
        candidate = store.replacement("doc", token)
        await candidate.write_silver_artifact("doc", "index.json", json.dumps({
            "document": {"filename": "doc.pdf", "page_count": 1, "source": original_source(b"B", "doc")},
        }))
        with pytest.raises(ValueError, match="incomplete|membership"):
            await store.publish_replacement("doc", token, [1])
        assert await published(store) == before
    asyncio.run(run())


def test_legacy_inconsistent_corpus_is_retained_but_not_merged_on_replacement(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"], ["LEGACY EXTRA"]]).ingest_pdf(b"A", "doc.pdf")
        # Model historical inconsistency. Startup must not guess membership
        # from page_count or destructively repair missing/extra artifacts.
        index = await store.get_index("doc")
        index["document"]["page_count"] = 1
        await store.write_silver_artifact("doc", "index.json", json.dumps(index))
        (tmp_path / "silver/doc/pages/1.png").unlink()
        files = {p: p.read_bytes() for layer in ("silver", "gold")
                 for p in (tmp_path / layer / "doc").rglob("*") if p.is_file()}
        restarted = FsDocStore(tmp_path)
        assert "LEGACY EXTRA" in await restarted.get_page_text("doc", 2)
        assert await restarted.get_page_image_path("doc", 1) is None
        await pipeline(restarted, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        assert await restarted.get_page_text("doc", 2) is None
        assert set((await restarted.get_regions("doc"))["pages"]) == {1}
        assert {v["page"] for v in (await restarted.get_embeddings("doc"))["vectors"]} == {1}
        assert all(p.read_bytes() == raw for p, raw in files.items())
    asyncio.run(run())


def test_g4_removes_polished_members_without_changing_g5_same_page_precedence(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["A"], ["REMOVE ME"]]).ingest_pdf(b"A", "doc.pdf")
        await store.write_silver_artifact("doc", "pages/1.md", "OLD POLISHED")
        await store.write_silver_artifact("doc", "pages/2.md", "REMOVED POLISHED")
        await pipeline(store, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True, polish=False)
        assert await store.get_page_text("doc", 1) == "OLD POLISHED"
        assert await store.get_page_text("doc", 2) is None
        assert all("POLISHED" not in v["text"] for v in (await store.get_embeddings("doc"))["vectors"])
    asyncio.run(run())
