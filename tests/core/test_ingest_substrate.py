"""Transactional substrate for gold: completeness marker, validation gate,
persisted candidates. Regression tests for the partial-gold leak (#101)."""
from __future__ import annotations

import asyncio
import json

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


def _fs_ingest(tmp_path, **kwargs):
    store = FsDocStore(tmp_path)
    ingest = IngestService(
        store,
        MemoryEventBus(),
        extractor=kwargs.pop("extractor", FakePdfExtractor()),
        renderer=kwargs.pop("renderer", FakePdfRenderer(page_count=1)),
        polisher=kwargs.pop("polisher", FakePolisher()),
        region_extractor=kwargs.pop("region_extractor", FakeRegionExtractor()),
        **kwargs,
    )
    return store, ingest


def test_crash_interrupted_ingest_is_not_reported_as_already_ingested(tmp_path):
    """Silver exists, gold partial (no marker) -> re-ingest must run, not skip."""
    async def run():
        store, ingest = _fs_ingest(tmp_path)
        # Simulate the on-disk state a crash mid-gold leaves behind: silver
        # index present, one region file written, no completeness marker.
        await store.write_silver_artifact("demo", "index.json", json.dumps({
            "document": {"page_count": 2, "title": "Demo", "filename": "demo.pdf"},
        }))
        await store.write_gold_region_file("demo", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])

        assert await store.has_gold("demo") is False
        result = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert not result.get("skipped"), "partial gold must not satisfy the idempotency gate"
        # After the full run the document is complete and skipping resumes.
        second = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert second.get("skipped") is True

    asyncio.run(run())


def test_partial_gold_is_not_visible(tmp_path):
    """Without the marker: has_gold False, get_gold_map None, list hides regions."""
    async def run():
        store = FsDocStore(tmp_path)
        await store.write_silver_artifact("demo", "index.json", json.dumps({
            "document": {"page_count": 2, "title": "Demo", "filename": "demo.pdf"},
        }))
        await store.write_gold_region_file("demo", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])

        assert await store.has_gold("demo") is False
        assert await store.get_gold_map("demo") is None
        docs = await store.list_documents()
        assert docs[0]["has_gold"] is False
        assert docs[0]["region_count"] == 0

        # The marker is the commit point: after it, everything is visible.
        await store.mark_gold_complete("demo", {"mode": "keyed", "region_count": 1})
        assert await store.has_gold("demo") is True
        gold = await store.get_gold_map("demo")
        assert gold is not None and 1 in gold["pages"]
        docs = await store.list_documents()
        assert docs[0]["has_gold"] is True
        assert docs[0]["region_count"] == 1
        assert docs[0]["gold_mode"] == "keyed"

    asyncio.run(run())


def test_skip_regions_ingest_is_not_already_ingested(tmp_path):
    """A --skip-regions pass leaves no gold; a later full pass must run."""
    async def run():
        store, ingest = _fs_ingest(tmp_path)
        first = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf", regions=False)
        assert not first.get("skipped")
        assert await store.has_gold("demo") is False
        second = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert not second.get("skipped")
        assert await store.has_gold("demo") is True

    asyncio.run(run())


def test_keyed_ingest_writes_completeness_marker(tmp_path):
    async def run():
        store, ingest = _fs_ingest(tmp_path)
        await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        marker = tmp_path / "gold" / "demo" / ".complete.json"
        assert marker.is_file()
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["complete"] is True
        assert data["mode"] == "keyed"
        assert data["region_count"] == 1

    asyncio.run(run())


def test_legacy_doc_with_success_report_still_counts_as_gold(tmp_path):
    """Docs ingested before the marker existed fall back to the ingest report."""
    async def run():
        store = FsDocStore(tmp_path)
        await store.write_silver_artifact("legacy", "index.json", json.dumps({
            "document": {"page_count": 1, "title": "Legacy", "filename": "legacy.pdf"},
        }))
        await store.write_gold_region_file("legacy", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])
        await store.write_silver_artifact("legacy", "ingest-report.json", json.dumps({
            "slug": "legacy", "status": "success", "region_count": 1,
        }))
        assert await store.has_gold("legacy") is True
        assert await store.get_gold_map("legacy") is not None

    asyncio.run(run())


def test_invalid_regions_are_rejected_and_reported(tmp_path):
    async def run():
        bad_regions = FakeRegionExtractor(regions_per_page=[
            {"id": "ok", "kind": "text", "title": "valid", "description": "x",
             "bbox": [10, 600, 200, 580], "tags": [], "entities": []},
            {"id": "bad-kind", "kind": "banner", "title": "nope",
             "bbox": [10, 600, 200, 580]},
            {"id": "bad-bbox", "kind": "text", "title": "inverted box",
             "bbox": [200, 600, 10, 580]},
            {"id": "no-title", "kind": "text", "bbox": [10, 600, 200, 580]},
        ])
        store, ingest = _fs_ingest(tmp_path, region_extractor=bad_regions)
        summary = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")

        assert summary["region_count"] == 1
        assert summary["invalid_region_count"] == 3
        regions = await store.get_regions("demo")
        assert [r["id"] for r in regions["pages"][1]] == ["ok"]
        report = json.loads(
            (tmp_path / "silver" / "demo" / "ingest-report.json").read_text(encoding="utf-8")
        )
        assert report["invalid_region_count"] == 3
        fields = {e["field"] for e in report["region_errors"]}
        assert {"kind", "bbox", "title"} <= fields

    asyncio.run(run())


def test_candidates_are_persisted_with_stable_item_ids(tmp_path):
    async def run():
        store, ingest = _fs_ingest(tmp_path)
        await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        candidates = await store.get_page_candidates("demo", 1)
        assert candidates is not None
        assert [c["id"] for c in candidates] == ["p1-i0", "p1-i1", "p1-i2"]
        assert candidates[0]["label"] == "title"
        assert candidates[0]["text"] == "Demo Doc"
        assert candidates[0]["bbox"] == [0.0, 720.0, 200.0, 700.0]
        # Ids agree with pages.meta.json (build_pages_meta mints the same).
        meta = await store.get_pages_meta("demo")
        assert meta["pages"]["1"]["item_ids"] == [c["id"] for c in candidates]

    asyncio.run(run())


def test_memory_store_mirrors_completeness_semantics():
    async def run():
        s = make_in_memory_services(page_count=1)
        # Silver-only state: index written, no marker.
        await s.doc_store.write_silver_artifact("demo", "index.json", json.dumps({
            "document": {"page_count": 1, "title": "Demo", "filename": "demo.pdf"},
        }))
        assert await s.doc_store.has_gold("demo") is False
        assert await s.doc_store.get_gold_map("demo") is None
        result = await s.ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert not result.get("skipped")
        assert await s.doc_store.has_gold("demo") is True
        assert await s.doc_store.get_gold_map("demo") is not None

    asyncio.run(run())


def test_forced_reingest_crash_does_not_resurrect_stale_gold(tmp_path):
    """clear_gold_complete runs before the gold loop, so a crash during a
    forced re-ingest leaves the doc invisible-as-gold even though the old
    (successful) ingest report is still on disk."""
    async def run():
        store, ingest = _fs_ingest(tmp_path)
        await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert await store.has_gold("demo") is True

        class Boom:
            async def extract_page(self, **_kw):
                raise RuntimeError("crash mid-gold")

        ingest.region_extractor = Boom()
        try:
            await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf", force=True)
        except RuntimeError:
            # Expected: this test asserts on the on-disk state the crash
            # leaves behind, not on the exception itself.
            pass
        assert await store.has_gold("demo") is False
        assert await store.get_gold_map("demo") is None
        # A plain re-ingest (no force) runs and completes the document.
        ingest.region_extractor = FakeRegionExtractor()
        out = await ingest.ingest_pdf(b"%PDF-fake", "demo.pdf")
        assert not out.get("skipped")
        assert await store.has_gold("demo") is True

    asyncio.run(run())
