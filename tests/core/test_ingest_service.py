"""IngestService end-to-end with fakes — no docling/pymupdf/openai imports."""
from __future__ import annotations

import asyncio

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakePdfExtractor, FakePdfRenderer
from tests.fixtures.services import make_in_memory_services


class StaticEmbedder:
    model_id = "model-a"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_ingest_pdf_emits_full_event_chain_and_persists_silver():
    async def run():
        s = make_in_memory_services(page_count=1)
        # Subscribe globally so we see the cross-workspace ingest events
        seen = []

        async def subscribe():
            async for evt in s.bus.subscribe(None):
                seen.append(evt)
                if any(e.type == "DocIngested" for e in seen):
                    return

        sub = asyncio.create_task(subscribe())
        await asyncio.sleep(0)

        summary = await s.ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        await asyncio.wait_for(sub, timeout=2.0)

        types = [e.type for e in seen]
        assert "DocBronzed" in types
        assert "DocSilvered" in types
        assert "DocPolished" in types
        assert "DocGoldExtracted" in types
        assert "DocIngested" in types
        assert summary["slug"] == "demo"
        # silver artifacts present
        assert (await s.doc_store.get_index("demo")) is not None

    asyncio.run(run())


def test_search_reports_skipped_docs_with_incompatible_embed_model():
    async def run():
        store = MemoryDocStore()
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(),
            embedder=StaticEmbedder(),
        )
        await store.write_embeddings(
            "compatible",
            {
                "embed_model": "model-a",
                "dim": 2,
                "embedded_at": 1.0,
                "vectors": [
                    {
                        "page": 2,
                        "region_id": "r1",
                        "text": "Compatible hit",
                        "vector": [1.0, 0.0],
                    }
                ],
            },
        )
        await store.write_embeddings(
            "incompatible",
            {
                "embed_model": "model-b",
                "dim": 2,
                "embedded_at": 1.0,
                "vectors": [
                    {
                        "page": 3,
                        "region_id": "r2",
                        "text": "Wrong embedding space",
                        "vector": [1.0, 0.0],
                    }
                ],
            },
        )

        result = await ingest.search("temperature", k=5)

        assert result["doc_count"] == 1
        assert [hit["slug"] for hit in result["hits"]] == ["compatible"]
        assert result["skipped"] == [
            {
                "slug": "incompatible",
                "stored_model": "model-b",
                "query_model": "model-a",
                "reason": "embed_model_mismatch",
            }
        ]

    asyncio.run(run())


def test_ingest_skips_polish_and_regions_when_disabled():
    async def run():
        s = make_in_memory_services(page_count=1)
        seen = []

        async def subscribe():
            async for evt in s.bus.subscribe(None):
                seen.append(evt)
                if any(e.type == "DocIngested" for e in seen):
                    return

        sub = asyncio.create_task(subscribe())
        await asyncio.sleep(0)
        await s.ingest.ingest_pdf(b"%PDF-fake", "raw.pdf", polish=False, regions=False)
        await asyncio.wait_for(sub, timeout=2.0)
        types = [e.type for e in seen]
        assert "DocPolished" not in types
        assert "DocGoldExtracted" not in types

    asyncio.run(run())


def test_ingest_uses_service_level_pipeline_defaults():
    async def run():
        s = make_in_memory_services(page_count=1)
        seen: dict[str, object] = {}

        async def render_pages(_pdf, dpi=150):
            seen["dpi"] = dpi
            return {1: b"PNG"}

        async def polish_page(*, page_image, page_no, deterministic_md, docling_items, model):
            seen["polish_model"] = model
            return deterministic_md

        async def extract_page(*, page_image, page_no, docling_items, model):
            seen["region_model"] = model
            return []

        s.renderer.render_pages = render_pages  # type: ignore[method-assign]
        s.polisher.polish_page = polish_page  # type: ignore[method-assign]
        s.region_extractor.extract_page = extract_page  # type: ignore[method-assign]
        s.ingest.default_polish_model = "configured-polish"
        s.ingest.default_region_model = "configured-regions"
        s.ingest.default_dpi = 222

        await s.ingest.ingest_pdf(b"%PDF-fake", "configured.pdf")

        assert seen == {
            "dpi": 222,
            "polish_model": "configured-polish",
            "region_model": "configured-regions",
        }

    asyncio.run(run())


def test_ingest_failure_emits_failed_event():
    async def run():
        s = make_in_memory_services()
        seen = []

        async def subscribe():
            async for evt in s.bus.subscribe(None):
                seen.append(evt)
                if any(e.type in {"DocIngestFailed", "DocIngested"} for e in seen):
                    return

        sub = asyncio.create_task(subscribe())
        await asyncio.sleep(0)

        # Make the extractor blow up
        async def boom(_pdf):
            raise RuntimeError("docling exploded")
        s.extractor.extract = boom  # type: ignore[assignment]

        try:
            await s.ingest.ingest_pdf(b"x", "boom.pdf")
        except RuntimeError:
            # Expected: this test asserts that the failure event is published.
            pass
        await asyncio.wait_for(sub, timeout=2.0)
        assert any(e.type == "DocIngestFailed" for e in seen)

    asyncio.run(run())
