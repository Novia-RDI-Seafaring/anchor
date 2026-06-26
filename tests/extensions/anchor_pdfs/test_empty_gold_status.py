"""Issue #188: a gold pass that yields 0 regions on a non-empty document must
not be recorded as a silent `ok`.

A transient region-extraction failure can produce 0 gold regions while silver
(pages/text) is non-empty. Before this fix the run was written with
`status: success` and `has_gold: false`, indistinguishable from a genuinely
region-less PDF and with no error — so an autonomous loop read it as done and
only a human-noticed `--force` re-ingest recovered the real regions.

These tests pin the new behaviour:
- a 0-region gold pass on a non-empty doc surfaces as `status: empty_gold`
  (not `ok`) via list_documents on both stores, with a reason;
- gold is NOT marked complete (has_gold stays false), so a plain re-ingest
  re-runs the gold stage;
- a transient empty pass is retried a bounded number of times and recovers.
"""
from __future__ import annotations

import asyncio
import json

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_pdfs.core.ingest_activity import (
    EMPTY_GOLD,
    IngestActivityRegistry,
)
from anchor.extensions.anchor_pdfs.core.services import (
    GOLD_EMPTY_MAX_ATTEMPTS,
    IngestService,
)
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)
from tests.fixtures.services import make_in_memory_services


class EmptyRegionExtractor:
    """Region extractor that always returns 0 regions (region-less / down)."""

    def __init__(self) -> None:
        self.calls = 0

    async def extract_page(self, *, page_image, page_no, docling_items, model):
        self.calls += 1
        return []


class FlakyRegionExtractor:
    """0 regions on the first whole pass, real regions on every later pass.

    Mirrors a transient gold failure: the first attempt yields nothing, a
    fresh attempt recovers. ``passes`` counts whole gold passes (it flips on
    the first page of each new pass).
    """

    def __init__(self) -> None:
        self.calls = 0
        self.passes = 0

    async def extract_page(self, *, page_image, page_no, docling_items, model):
        self.calls += 1
        if page_no == 1:
            self.passes += 1
        if self.passes <= 1:
            return []
        return [
            {
                "id": "r1", "kind": "text", "title": "recovered region",
                "description": "x", "bbox": [10, 600, 200, 580],
                "tags": [], "entities": [], "page": page_no,
            }
        ]


def test_empty_gold_surfaces_as_non_ok_on_fs(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=EmptyRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )

        summary = await ingest.ingest_pdf(b"%PDF-fake", "empty.pdf")

        # The result itself flags the empty-gold outcome with a reason.
        assert summary["region_count"] == 0
        assert summary["status"] == "empty_gold"
        assert "0 regions" in summary["reason"]

        # The persisted report is empty_gold, not success.
        report = json.loads(
            (tmp_path / "silver" / "empty" / "ingest-report.json").read_text(encoding="utf-8")
        )
        assert report["status"] == "empty_gold"
        assert report["gold_complete"] is False
        assert report["reason"]

        # Gold is NOT complete: a plain re-ingest (no --force) re-runs gold.
        assert await store.has_gold("empty") is False

        # Visible as a distinct non-ok row, not a silent ok.
        docs = await store.list_documents()
        assert len(docs) == 1
        entry = docs[0]
        assert entry["slug"] == "empty"
        assert entry["status"] == "empty_gold"
        assert entry["has_gold"] is False
        assert entry["region_count"] == 0
        assert entry["reason"]

    asyncio.run(run())


def test_empty_gold_surfaces_as_non_ok_in_memory():
    async def run():
        s = make_in_memory_services(page_count=1)
        s.region_extractor.extract_page = EmptyRegionExtractor().extract_page  # type: ignore[method-assign]

        summary = await s.ingest.ingest_pdf(b"%PDF-fake", "empty.pdf")
        assert summary["status"] == "empty_gold"

        docs = await s.doc_store.list_documents()
        empty = [d for d in docs if d["slug"] == "empty"]
        assert len(empty) == 1
        assert empty[0]["status"] == "empty_gold"
        assert empty[0]["reason"]
        assert empty[0]["has_gold"] is False
        # Not marked complete: a re-ingest re-runs the gold stage.
        assert await s.doc_store.has_gold("empty") is False

    asyncio.run(run())


def test_empty_gold_marks_activity_record_non_done():
    async def run():
        s = make_in_memory_services(page_count=1)
        s.region_extractor.extract_page = EmptyRegionExtractor().extract_page  # type: ignore[method-assign]

        await s.ingest.ingest_pdf(b"%PDF-fake", "empty.pdf")

        registry = IngestActivityRegistry(store=s.doc_store)
        activity = await registry.get("empty")
        assert activity is not None
        # The ingest-activity surface flags it instead of reading `done`.
        assert activity.status == EMPTY_GOLD
        assert activity.status != "done"
        assert activity.error

    asyncio.run(run())


def test_transient_empty_gold_is_retried_and_recovers_on_fs(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        flaky = FlakyRegionExtractor()
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=flaky,
            clock=FixedClock(ts=1700000000.0),
        )

        summary = await ingest.ingest_pdf(b"%PDF-fake", "flaky.pdf")

        # The bounded retry ran a second whole pass and recovered.
        assert flaky.passes == 2
        assert summary.get("status") != "empty_gold"
        assert summary["region_count"] == 1

        report = json.loads(
            (tmp_path / "silver" / "flaky" / "ingest-report.json").read_text(encoding="utf-8")
        )
        assert report["status"] == "success"
        assert report["gold_complete"] is True
        assert report["gold_attempts"] == 2

        # Recovered run is a real, complete gold layer.
        assert await store.has_gold("flaky") is True
        docs = await store.list_documents()
        assert docs[0]["status"] == "ok"
        assert docs[0]["region_count"] == 1

    asyncio.run(run())


def test_persistent_empty_gold_stops_after_bounded_attempts():
    async def run():
        s = make_in_memory_services(page_count=1)
        extractor = EmptyRegionExtractor()
        s.region_extractor.extract_page = extractor.extract_page  # type: ignore[method-assign]

        summary = await s.ingest.ingest_pdf(b"%PDF-fake", "empty.pdf")

        assert summary["status"] == "empty_gold"
        # One call per page per attempt; 1 page * GOLD_EMPTY_MAX_ATTEMPTS.
        assert extractor.calls == GOLD_EMPTY_MAX_ATTEMPTS

    asyncio.run(run())


def test_non_empty_gold_still_reads_ok_on_fs(tmp_path):
    """Guard the happy path: a normal gold pass stays status ok / has_gold."""

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

        summary = await ingest.ingest_pdf(b"%PDF-fake", "ok.pdf")
        assert summary.get("status") != "empty_gold"

        docs = await store.list_documents()
        assert docs[0]["status"] == "ok"
        assert docs[0]["has_gold"] is True
        assert docs[0]["region_count"] == 1

    asyncio.run(run())
