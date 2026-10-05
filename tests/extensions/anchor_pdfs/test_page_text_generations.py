"""Page text belongs to the selected source generation, including optional polish."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import harness, pipeline, published


class Polisher:
    async def polish_page(self, *, deterministic_md, **kwargs):
        return deterministic_md + "\nCURRENT POLISH"


@pytest.mark.parametrize("memory", [False, True])
def test_skip_polish_replacement_returns_current_raw_and_retains_old_snapshot(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        first = pipeline(store, [["OLD_GENERATION_TEXT"]])
        first.polisher = Polisher()
        await first.ingest_pdf(b"A", "shared.pdf", slug="doc")
        old = store.snapshot("doc")
        old_text = await old.get_page_text("doc", 1)
        assert "CURRENT POLISH" in old_text
        await pipeline(store, [["NEW_GENERATION_TEXT"]]).ingest_pdf(
            b"B", "shared.pdf", slug="doc", force=True, polish=False,
        )
        current = await store.get_page_text("doc", 1)
        assert "NEW_GENERATION_TEXT" in current
        assert "OLD_GENERATION_TEXT" not in current
        assert "CURRENT POLISH" not in current
        assert await old.get_page_text("doc", 1) == old_text
        if not memory:
            assert (tmp_path / "silver/doc/pages/1.md").read_text(encoding="utf-8") == old_text
            assert await FsDocStore(tmp_path).get_page_text("doc", 1) == current
            assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"B"
    asyncio.run(run())


@pytest.mark.parametrize("memory", [False, True])
def test_orphan_polish_is_not_admitted_by_file_presence_after_publication(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        await pipeline(store, [["NEW"]]).ingest_pdf(b"B", "doc.pdf", force=True, polish=False)
        # An old G4 copy or a late orphan file must not expand the published
        # generation's polished membership just by occupying the same page.
        await store.write_silver_artifact("doc", "pages/1.md", "OLD POLISHED")
        await store.write_silver_artifact("doc", "ingest-report.json", json.dumps({
            "status": "success", "polished_pages": [1],
        }))
        assert "NEW" in await store.get_page_text("doc", 1)
        assert "OLD" not in await store.get_page_text("doc", 1)
    asyncio.run(run())


@pytest.mark.parametrize("memory", [False, True])
def test_current_polish_is_preferred_and_published_membership_is_pinned(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        replacement = pipeline(store, [["NEW RAW"]])
        replacement.polisher = Polisher()
        await replacement.ingest_pdf(b"B", "doc.pdf", force=True)
        reader = store.snapshot("doc")
        assert "NEW RAW" in await reader.get_page_text("doc", 1)
        assert "CURRENT POLISH" in await reader.get_page_text("doc", 1)
        # Post-publication report changes cannot remove or grant authority.
        await store.write_silver_artifact("doc", "ingest-report.json", json.dumps({
            "status": "success", "polished_pages": [],
        }))
        assert "CURRENT POLISH" in await reader.get_page_text("doc", 1)
        if not memory:
            assert "CURRENT POLISH" in await FsDocStore(tmp_path).get_page_text("doc", 1)
        await pipeline(store, [["THIRD RAW"]]).ingest_pdf(b"C", "doc.pdf", force=True, polish=False)
        assert "THIRD RAW" in await store.get_page_text("doc", 1)
        assert "CURRENT POLISH" in await reader.get_page_text("doc", 1)
    asyncio.run(run())


@pytest.mark.parametrize("inventory", [None, "missing", "1", [True], [1, 1]])
def test_pre_g5_or_invalid_polish_inventory_falls_back_without_deleting_files(tmp_path, inventory):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        replacement = pipeline(store, [["NEW RAW"]])
        replacement.polisher = Polisher()
        await replacement.ingest_pdf(b"B", "doc.pdf", force=True)
        pointer = tmp_path / "silver/doc/.current.json"
        manifest = json.loads(pointer.read_text(encoding="utf-8"))
        if inventory == "missing":
            manifest.pop("polished_pages")  # Exact pre-G5 manifest schema.
        else:
            manifest["polished_pages"] = inventory
        pointer.write_text(json.dumps(manifest), encoding="utf-8")
        polished = tmp_path / "silver/doc/generations" / manifest["generation"] / "pages/1.md"
        polished.write_text("OLD COPIED POLISH", encoding="utf-8")
        restarted = FsDocStore(tmp_path)
        text = await restarted.get_page_text("doc", 1)
        assert "NEW RAW" in text and "OLD" not in text
        assert polished.read_text(encoding="utf-8") == "OLD COPIED POLISH"
        assert (await restarted.get_index("doc"))["document"]["source"]["sha256"] == hashlib.sha256(b"B").hexdigest()
    asyncio.run(run())


def test_missing_current_polished_file_falls_back_to_current_raw(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        replacement = pipeline(store, [["NEW RAW"]])
        replacement.polisher = Polisher()
        await replacement.ingest_pdf(b"B", "doc.pdf", force=True)
        generation = (await store.get_index("doc"))["document"]["generation"]["id"]
        (tmp_path / "silver/doc/generations" / generation / "pages/1.md").unlink()
        assert "NEW RAW" in await store.get_page_text("doc", 1)
        assert "CURRENT POLISH" not in await store.get_page_text("doc", 1)
    asyncio.run(run())


@pytest.mark.parametrize("memory", [False, True])
def test_polish_failure_keeps_old_complete_generation_then_raw_retry_succeeds(tmp_path, memory):
    class FailsOnSecondPage(Polisher):
        async def polish_page(self, *, page_no, **kwargs):
            if page_no == 2:
                raise RuntimeError("controlled polish failure")
            return await super().polish_page(**kwargs)

    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        first = pipeline(store, [["OLD 1"], ["OLD 2"]])
        first.polisher = Polisher()
        await first.ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        replacement = pipeline(store, [["NEW 1"], ["NEW 2"]])
        replacement.polisher = FailsOnSecondPage()
        with pytest.raises(RuntimeError, match="controlled polish"):
            await replacement.ingest_pdf(b"B", "doc.pdf", force=True)
        assert await published(store) == before
        await replacement.ingest_pdf(b"B", "doc.pdf", force=True, polish=False)
        for page in (1, 2):
            text = await store.get_page_text("doc", page)
            assert f"NEW {page}" in text and "OLD" not in text and "CURRENT POLISH" not in text
    asyncio.run(run())


@pytest.mark.parametrize("first_lane", ["harness", "built-in"])
@pytest.mark.parametrize("polish_new", [False, True])
def test_cross_workflow_replacement_uses_only_current_page_text(tmp_path, first_lane, polish_new):
    async def ingest(store, lane, source, text, polish):
        if lane == "built-in":
            svc = pipeline(store, [[text]])
            svc.polisher = Polisher()
            await svc.ingest_pdf(source, "doc.pdf", force=True, polish=polish)
        else:
            svc = harness(store, tmp_path, [[text]])
            order = await svc.ingest_begin(source, "doc.pdf", force=True)
            work = await svc.ingest_get_page(order["session_id"], 1)
            assert text in work["raw_md"]
            if text == "NEW TOKEN":
                assert "OLD TOKEN" not in work["raw_md"]
            verdict = await svc.ingest_submit_page(order["session_id"], 1, regions=[{
                "id": "r1", "kind": "text", "title": text,
                "member_item_ids": [c["id"] for c in work["candidates"]],
            }], polished_md=text + " CURRENT POLISH" if polish else None)
            assert verdict["accepted"]
            assert (await svc.ingest_finalize(order["session_id"]))["finalized"]

    async def run():
        store = FsDocStore(tmp_path)
        await ingest(store, first_lane, b"A", "OLD TOKEN", True)
        old = store.snapshot("doc")
        await ingest(store, "built-in" if first_lane == "harness" else "harness", b"B", "NEW TOKEN", polish_new)
        for reader in (store, FsDocStore(tmp_path)):
            text = await reader.get_page_text("doc", 1)
            assert "NEW TOKEN" in text and "OLD TOKEN" not in text
            assert ("CURRENT POLISH" in text) == polish_new
            assert (await reader.get_index("doc"))["document"]["page_count"] == 1
            assert (await reader.get_raw_pdf_path("doc")).read_bytes() == b"B"
        assert "OLD TOKEN" in await old.get_page_text("doc", 1)
    asyncio.run(run())


@pytest.mark.parametrize("polished", [[2], [True], [1, 1], [1]])
def test_publication_rejects_invalid_or_missing_polished_members_before_switch(tmp_path, polished):
    async def run():
        store = FsDocStore(tmp_path)
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        before = await published(store)
        token = await store.begin_replacement("doc", [1])
        candidate = store.replacement("doc", token)
        index = await store.get_index("doc")
        await candidate.write_silver_artifact("doc", "index.json", json.dumps(index))
        await candidate.write_silver_artifact("doc", "pages.meta.json", json.dumps({"pages": {"1": {}}}))
        await candidate.write_silver_artifact("doc", "pages/1.raw.md", "NEW RAW")
        await candidate.write_silver_artifact("doc", "pages/1.png", b"image")
        await candidate.write_silver_artifact("doc", "pages/1.candidates.json", "[]")
        await candidate.write_silver_artifact("doc", "ingest-report.json", json.dumps({
            "status": "success", "polished_pages": polished,
        }))
        with pytest.raises(ValueError, match="polished"):
            await store.publish_replacement("doc", token, [1])
        assert await published(store) == before
    asyncio.run(run())
