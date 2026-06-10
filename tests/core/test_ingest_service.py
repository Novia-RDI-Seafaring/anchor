"""IngestService end-to-end with fakes — no docling/pymupdf/openai imports."""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)
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


def test_ingest_is_idempotent_unless_forced():
    async def run():
        s = make_in_memory_services(page_count=1)
        first = await s.ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert not first.get("skipped")
        # Re-ingesting the same slug short-circuits instead of recomputing.
        second = await s.ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert second["skipped"] is True
        # force=True recomputes.
        forced = await s.ingest.ingest_pdf(b"%PDF-fake", "demo.pdf", force=True)
        assert not forced.get("skipped")

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


def test_ingest_promotes_approximate_bbox_before_storing_gold_regions():
    async def run():
        s = make_in_memory_services(page_count=1)
        s.extractor.docling = {
            "items": [
                {"label": "title", "text": "Demo Doc", "page": 1, "bbox": [0, 720, 200, 700]},
                {"label": "section_header", "text": "Section A", "page": 1, "bbox": [0, 620, 100, 600]},
                {"label": "text", "text": "First paragraph.", "page": 1, "bbox": [0, 595, 200, 580]},
            ],
        }

        async def extract_page(*, page_image, page_no, docling_items, model):
            return [
                {
                    "id": "r1",
                    "kind": "text",
                    "title": "approx region",
                    "description": "x",
                    "approximate_bbox": [0, 720, 210, 570],
                },
            ]

        s.region_extractor.extract_page = extract_page  # type: ignore[method-assign]

        await s.ingest.ingest_pdf(b"%PDF-fake", "approx.pdf")

        regions = await s.doc_store.get_regions("approx")
        region = regions["pages"][1][0]
        assert region["approximate_bbox"] == [0, 720, 210, 570]
        assert region["bbox"] == [0, 720, 200, 580]

    asyncio.run(run())


def test_ingest_writes_timing_report_to_silver(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            embedder=StaticEmbedder(),
        )

        summary = await ingest.ingest_pdf(b"%PDF-fake", "timed.pdf")

        report_path = tmp_path / "silver" / "timed" / "ingest-report.json"
        assert report_path.is_file()
        assert summary["timing_report_path"] == str(report_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["slug"] == "timed"
        assert report["status"] == "success"
        assert report["page_count"] == 1
        assert report["region_count"] == 1
        assert report["embedded_count"] == 1
        assert isinstance(report["duration_seconds"], (float, int))
        stage_names = [stage["stage"] for stage in report["stages"]]
        assert stage_names == [
            "bronze",
            "silver_extract",
            "silver_index",
            "silver_render_pages",
            "silver_polish",
            "gold_regions",
            "embed",
        ]
        assert report["stages"][-1]["embed_model"] == "model-a"

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
