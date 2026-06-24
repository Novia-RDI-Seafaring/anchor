"""Regression: a crash after bronze-stash but before silver must leave the
document VISIBLE as failed (issue #44), not silently absent.

Covers both stores: the fs store (on-disk ingest-report.json + orphan bronze)
and the in-memory store (event bus + status + recovery on re-ingest).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)
from tests.fixtures.services import make_in_memory_services


class BoomExtractor:
    """Extractor that raises in the silver_extract stage."""

    async def extract(self, pdf_path):
        raise RuntimeError("docling exploded")


def test_failed_ingest_is_visible_and_recoverable_on_fs(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=BoomExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )

        with pytest.raises(RuntimeError, match="docling exploded"):
            await ingest.ingest_pdf(b"%PDF-fake", "boom.pdf")

        # Orphan bronze is kept on purpose.
        assert (tmp_path / "bronze" / "boom.pdf").is_file()

        # Failure record persisted into the silver ingest-report.json slot,
        # creating silver/<slug>/ so the doc surfaces in list_documents.
        report_path = tmp_path / "silver" / "boom" / "ingest-report.json"
        assert report_path.is_file()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "failed"
        assert report["stage"] == "silver_extract"
        assert "docling exploded" in report["error"]
        assert report["filename"] == "boom.pdf"
        assert report["bronze_path"].endswith("boom.pdf")
        assert report["failed_at"].startswith("2023-")

        docs = await store.list_documents()
        assert len(docs) == 1
        entry = docs[0]
        assert entry["slug"] == "boom"
        assert entry["status"] == "failed"
        assert entry["stage"] == "silver_extract"
        assert "docling exploded" in entry["error"]
        assert entry["bronze_path"].endswith("boom.pdf")
        # Failed-early doc has no gold and no real page count — that's correct.
        assert entry["has_gold"] is False
        assert entry["page_count"] == 0

        # Recovery: re-ingest the SAME filename with a working extractor.
        ingest.extractor = FakePdfExtractor()  # type: ignore[assignment]
        summary = await ingest.ingest_pdf(b"%PDF-fake", "boom.pdf")
        assert not summary.get("skipped")

        docs = await store.list_documents()
        assert len(docs) == 1
        assert docs[0]["status"] == "ok"

    asyncio.run(run())


def test_failed_ingest_publishes_failed_event_with_real_stage():
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

        async def boom(_pdf):
            raise RuntimeError("docling exploded")
        s.extractor.extract = boom  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="docling exploded"):
            await s.ingest.ingest_pdf(b"x", "boom.pdf")
        await asyncio.wait_for(sub, timeout=2.0)

        failed = [e for e in seen if e.type == "DocIngestFailed"]
        assert failed, "expected a DocIngestFailed event"
        payload = failed[0].payload
        # Real stage, not the old hardcoded "unknown".
        assert payload["stage"] == "silver_extract"
        assert payload["stage"] != "unknown"
        assert payload["error"]

        # The failed doc is now visible via the store.
        docs = await s.doc_store.list_documents()
        boom_entries = [d for d in docs if d["slug"] == "boom"]
        assert len(boom_entries) == 1
        assert boom_entries[0]["status"] == "failed"
        assert boom_entries[0]["stage"] == "silver_extract"
        assert boom_entries[0]["error"]

    asyncio.run(run())


def test_successful_ingest_reports_status_ok_on_fs(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )

        await ingest.ingest_pdf(b"%PDF-fake", "ok.pdf")

        docs = await store.list_documents()
        assert len(docs) == 1
        assert docs[0]["slug"] == "ok"
        assert docs[0]["status"] == "ok"

    asyncio.run(run())
