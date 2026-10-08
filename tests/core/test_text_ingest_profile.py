"""The text profile produces searchable, grounded gold without vision calls."""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakeEmbedder, FakePdfExtractor, FakePdfRenderer


class NoVision:
    async def polish_page(self, **kwargs):
        pytest.fail("text profile called the polisher")

    async def extract_page(self, **kwargs):
        pytest.fail("text profile called the vision extractor")


def pipeline(*, docling=None, vision=True, store=None):
    store = store or MemoryDocStore()
    service = IngestService(
        store, MemoryEventBus(), extractor=FakePdfExtractor(docling),
        renderer=FakePdfRenderer(), embedder=FakeEmbedder(),
        polisher=NoVision() if vision else None,
        region_extractor=NoVision() if vision else None,
    )
    return service, store


@pytest.mark.parametrize("vision", [True, False])
def test_text_profile_preserves_grounding_and_searches_without_vision(vision, tmp_path):
    async def run():
        service, store = pipeline(vision=vision, store=FsDocStore(tmp_path))
        result = await service.ingest_pdf(b"%PDF-fake", "text.pdf", profile="text")
        assert result["profile"] == "text"
        assert result["region_count"] == result["embedded_count"] == 1
        assert result["polished_pages"] == []
        assert await store.has_gold("text")
        gold = await store.get_gold_map("text")
        region = gold["pages"][1][0]
        assert region["member_item_ids"] == ["p1-i1", "p1-i2"]
        assert region["bbox"] == [0, 172, 200, 212]
        assert "First paragraph." in region["content"]
        embeddings = await store.get_embeddings("text")
        assert "First paragraph." in embeddings["vectors"][0]["text"]
        report = json.loads((tmp_path / "silver/text/ingest-report.json").read_text(encoding="utf-8"))
        assert report["mode"] == "text"
        assert report["options"]["polish_model"] is None
        assert report["options"]["region_model"] is None
        assert report["gold_complete"] is True
        assert not any(stage["stage"] == "silver_polish" for stage in report["stages"])
        skipped = await service.ingest_pdf(b"%PDF-fake", "text.pdf", profile="text")
        assert skipped["skipped"] is True
        assert len(service.extractor.calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("docling", [
    {"items": []},
    {"items": [{"label": "picture", "text": "", "page": 1, "bbox": [0, 0, 100, 100]}]},
])
def test_text_profile_does_not_mark_visual_or_empty_documents_complete(docling):
    async def run():
        service, store = pipeline(docling=docling)
        result = await service.ingest_pdf(b"%PDF-fake", "empty.pdf", profile="text")
        assert result["status"] == "empty_gold"
        assert "no groundable text" in result["reason"]
        assert not await store.has_gold("empty")
    asyncio.run(run())


@pytest.mark.parametrize("options", [{"profile": "unknown"}, {"profile": "text", "regions": False}])
def test_invalid_profile_options_fail_before_writing(options):
    async def run():
        service, store = pipeline()
        with pytest.raises(ValueError):
            await service.ingest_pdf(b"%PDF-fake", "text.pdf", **options)
        assert await store.list_documents() == []
        assert service.extractor.calls == []
    asyncio.run(run())


def test_empty_text_replacement_preserves_previously_published_gold(tmp_path):
    async def run():
        service, store = pipeline(store=FsDocStore(tmp_path))
        await service.ingest_pdf(b"%PDF-fake", "text.pdf", profile="text")
        previous = await store.get_gold_map("text")
        service.extractor.docling = {"items": []}
        result = await service.ingest_pdf(b"%PDF-fake", "text.pdf", profile="text", force=True)
        assert result["status"] == "empty_gold"
        assert await store.has_gold("text")
        assert await store.get_gold_map("text") == previous
    asyncio.run(run())


def test_text_profile_keeps_full_table_cells():
    async def run():
        service, store = pipeline(docling={"items": [{
            "label": "table", "text": "", "page": 1, "bbox": [0, 0, 100, 100],
            "cells": [
                {"row": 0, "col": 0, "text": "Pressure", "bbox": [0, 0, 50, 40]},
                {"row": 0, "col": 1, "text": "17 bar", "bbox": [50, 0, 100, 40]},
            ],
        }]})
        await service.ingest_pdf(b"%PDF-fake", "table.pdf", profile="text")
        gold = await store.get_gold_map("table")
        region = gold["pages"][1][0]
        assert region["kind"] == "table"
        assert region["member_item_ids"] == ["p1-i0"]
        assert "17 bar" in region["content"]
        assert region["cells"][1]["bbox"] == [50, 0, 100, 40]
    asyncio.run(run())
