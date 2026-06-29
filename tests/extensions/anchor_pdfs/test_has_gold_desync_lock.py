"""Issue #175: has_gold must reflect real queryable gold, not just the stub
marker; the marker is finalize-only and atomic; and a per-slug ingest lock
stops two concurrent --force ingests on one slug from desyncing the marker.

The reported scenario: a killed / concurrent ``anchor ingest --force`` on a
slug resets ``gold/<slug>/.complete.json`` to the start-of-run stub
``{"complete": false}`` and exits before finalizing, even though every gold
artifact (regions + embeddings + a success ingest-report with
``gold_complete: true``) was written. ``anchor list`` / ``list_documents``
then reported ``has_gold: false, region_count: 0`` for a fully-golded,
queryable doc, so a consumer needlessly re-ingested (re-billing the vision
model).

These tests pin:
- a stub marker + present-and-consistent gold artifacts => has_gold true with
  the real region_count (the exact #175 scenario), on both stores;
- the marker only flips ``complete: true`` at finalize and is written
  atomically (no false-true on a killed mid-run);
- the per-slug lock serializes / fails-fast so concurrent re-ingests cannot
  interleave;
- a genuinely-incomplete doc (stub marker, no consistent artifacts) stays
  has_gold false (the cross-check is conservative).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_pdfs.core.ports.doc_store import IngestLockHeld
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import (
    GOLD_COMPLETE_MARKER,
    FsDocStore,
)
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


def _write_stub_marker(store: FsDocStore, slug: str) -> None:
    """Reproduce the start-of-run stub a killed --force leaves behind."""
    marker = store.gold / slug / GOLD_COMPLETE_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"complete": False}), encoding="utf-8")


# ── Fix 1: has_gold reflects real queryable gold, not the stub ───────────────


def test_stub_marker_with_consistent_gold_reads_has_gold_on_fs(tmp_path):
    """The exact #175 scenario: stub .complete.json + real gold => has_gold true."""

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
        summary = await ingest.ingest_pdf(b"%PDF-fake", "loop-engineering-ieee.pdf")
        slug = summary["slug"]
        assert summary["region_count"] >= 1
        assert await store.has_gold(slug) is True

        # Now simulate a concurrent / killed --force run that reset the marker
        # to the start-of-run stub but exited before finalizing — all gold
        # artifacts (regions, success ingest-report with gold_complete:true)
        # are still on disk.
        _write_stub_marker(store, slug)
        assert json.loads(
            (store.gold / slug / GOLD_COMPLETE_MARKER).read_text(encoding="utf-8")
        ) == {"complete": False}

        # has_gold must cross-check the real artifacts, not trust the stub.
        assert await store.has_gold(slug) is True
        docs = await store.list_documents()
        entry = next(d for d in docs if d["slug"] == slug)
        assert entry["has_gold"] is True
        assert entry["region_count"] == summary["region_count"]
        assert entry["status"] == "ok"
        # Gold map is queryable again despite the stub marker.
        gold = await store.get_gold_map(slug)
        assert gold is not None

    asyncio.run(run())


def test_stub_marker_with_consistent_gold_reads_has_gold_in_memory():
    async def run():
        store = MemoryDocStore()
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=FakePdfExtractor(),
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )
        summary = await ingest.ingest_pdf(b"%PDF-fake", "loop-engineering-ieee.pdf")
        slug = summary["slug"]
        assert await store.has_gold(slug) is True

        # Reset the marker to the stub the killed run leaves behind; the
        # regions + success report are still present in the store.
        await store.clear_gold_complete(slug)
        assert store._gold_markers[slug] == {"complete": False}

        assert await store.has_gold(slug) is True
        docs = await store.list_documents()
        entry = next(d for d in docs if d["slug"] == slug)
        assert entry["has_gold"] is True
        assert entry["region_count"] == summary["region_count"]

    asyncio.run(run())


def test_cross_check_is_conservative_on_fs(tmp_path):
    """A genuinely-incomplete doc (stub marker, no consistent report) stays false.

    The cross-check must not flip a silver-only / partial doc to has_gold:true.
    """

    async def run():
        store = FsDocStore(tmp_path)
        # Silver only: index written, a couple of region files present, but NO
        # success ingest-report -> the cross-check has nothing trustworthy to
        # vouch for completeness, so has_gold stays false.
        await store.write_silver_artifact("partial", "index.json", json.dumps({
            "document": {"page_count": 2, "title": "Partial", "filename": "partial.pdf"},
        }))
        await store.write_gold_region_file("partial", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])
        _write_stub_marker(store, "partial")
        assert await store.has_gold("partial") is False
        docs = await store.list_documents()
        entry = next(d for d in docs if d["slug"] == "partial")
        assert entry["has_gold"] is False
        assert entry["region_count"] == 0

    asyncio.run(run())


def test_cross_check_rejects_truncated_gold_on_fs(tmp_path):
    """A report claims N regions but fewer are on disk (a crash truncated the
    overwrite): the cross-check must NOT vouch for it."""

    async def run():
        store = FsDocStore(tmp_path)
        await store.write_silver_artifact("trunc", "index.json", json.dumps({
            "document": {"page_count": 2, "title": "Trunc", "filename": "trunc.pdf"},
        }))
        # Only one region actually on disk...
        await store.write_gold_region_file("trunc", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])
        # ...but a stale success report claims many more.
        await store.write_silver_artifact("trunc", "ingest-report.json", json.dumps({
            "status": "success", "gold_complete": True, "region_count": 99,
        }))
        _write_stub_marker(store, "trunc")
        assert await store.has_gold("trunc") is False

    asyncio.run(run())


# ── Fix 2: atomic, finalize-only marker ──────────────────────────────────────


def test_marker_only_flips_true_on_finalize(tmp_path):
    """clear_gold_complete writes the stub; the marker never reads complete:true
    until mark_gold_complete lands. A killed mid-run leaves the stub, not a
    false-true."""

    async def run():
        store = FsDocStore(tmp_path)
        marker = store.gold / "demo" / GOLD_COMPLETE_MARKER
        # The gold dir exists once a region file lands (as in the real loop);
        # clear_gold_complete then writes the stub into it.
        (store.gold / "demo").mkdir(parents=True, exist_ok=True)

        await store.clear_gold_complete("demo")
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data == {"complete": False}
        # Marker present, mid-run: must not read as complete.
        assert await store.has_gold("demo") is False

        await store.mark_gold_complete("demo", {
            "mode": "keyed", "model": "gpt-5.4", "region_count": 3,
        })
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["complete"] is True
        assert data["region_count"] == 3
        assert await store.has_gold("demo") is True

    asyncio.run(run())


def test_marker_write_is_atomic_no_temp_left_behind(tmp_path):
    """Both writers go through write-temp + os.replace; no .tmp is left and the
    marker is always valid JSON (never a half-written file)."""

    async def run():
        store = FsDocStore(tmp_path)
        gold_dir = store.gold / "demo"
        await store.clear_gold_complete("demo")
        await store.mark_gold_complete("demo", {"region_count": 1})
        # No leftover temp sibling.
        assert not (gold_dir / (GOLD_COMPLETE_MARKER + ".tmp")).exists()
        # Marker parses cleanly.
        json.loads((gold_dir / GOLD_COMPLETE_MARKER).read_text(encoding="utf-8"))

    asyncio.run(run())


# ── Fix 3: per-slug ingest lock ──────────────────────────────────────────────


def test_ingest_lock_fail_fast_when_held_on_fs(tmp_path):
    """A second acquisition with wait=False raises IngestLockHeld while the
    first holds the slug's lock; a different slug is unaffected."""

    async def run():
        store = FsDocStore(tmp_path)
        async with store.ingest_lock("slug-a"):
            with pytest.raises(IngestLockHeld):
                async with store.ingest_lock("slug-a", wait=False):
                    pass
            # A different slug is independent.
            async with store.ingest_lock("slug-b", wait=False):
                pass
        # Released after the block: re-acquire works.
        async with store.ingest_lock("slug-a", wait=False):
            pass

    asyncio.run(run())


def test_ingest_lock_waits_then_acquires_on_fs(tmp_path):
    """A waiting acquisition blocks until the holder releases, then proceeds."""

    async def run():
        store = FsDocStore(tmp_path)
        order: list[str] = []

        async def holder():
            async with store.ingest_lock("slug"):
                order.append("holder-acquired")
                await asyncio.sleep(0.2)
                order.append("holder-releasing")

        async def waiter():
            await asyncio.sleep(0.05)  # ensure holder grabs it first
            async with store.ingest_lock("slug", wait=True, timeout=5.0):
                order.append("waiter-acquired")

        await asyncio.gather(holder(), waiter())
        # The waiter only got in after the holder released.
        assert order == ["holder-acquired", "holder-releasing", "waiter-acquired"]

    asyncio.run(run())


def test_ingest_lock_wait_timeout_raises_on_fs(tmp_path):
    """A bounded wait that elapses surfaces IngestLockHeld, not a hang."""

    async def run():
        store = FsDocStore(tmp_path)
        async with store.ingest_lock("slug"):
            with pytest.raises(IngestLockHeld):
                async with store.ingest_lock("slug", wait=True, timeout=0.1):
                    pass

    asyncio.run(run())


def test_stale_ingest_lock_is_reclaimed_on_fs(tmp_path):
    """A lock orphaned by a hard kill (old mtime) is reclaimed, not wedged."""
    import os
    import time

    from anchor.extensions.anchor_pdfs.infra import fs_doc_store as mod

    async def run():
        store = FsDocStore(tmp_path)
        lock_path = store._ingest_lock_path("slug")
        lock_path.write_text("pid=999 orphaned\n", encoding="utf-8")
        # Backdate it well past the stale threshold.
        old = time.time() - (mod.INGEST_LOCK_STALE_SECONDS + 60)
        os.utime(lock_path, (old, old))
        # A new acquisition reclaims the stale lock instead of failing.
        async with store.ingest_lock("slug", wait=False):
            pass

    asyncio.run(run())


def test_ingest_lock_fail_fast_when_held_in_memory():
    async def run():
        store = MemoryDocStore()
        async with store.ingest_lock("slug-a"):
            with pytest.raises(IngestLockHeld):
                async with store.ingest_lock("slug-a", wait=False):
                    pass
            async with store.ingest_lock("slug-b", wait=False):
                pass

    asyncio.run(run())


def test_ingest_lock_serializes_concurrent_passes_in_memory():
    """Two coroutines entering the same slug's lock never overlap inside it."""

    async def run():
        store = MemoryDocStore()
        active = 0
        max_active = 0

        async def worker():
            nonlocal active, max_active
            async with store.ingest_lock("slug", wait=True, timeout=5.0):
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1

        await asyncio.gather(*(worker() for _ in range(4)))
        assert max_active == 1

    asyncio.run(run())


def test_concurrent_force_ingests_do_not_desync_marker_on_fs(tmp_path):
    """Two concurrent ingest_pdf(force=True) on one slug serialize via the lock;
    the marker ends consistent with the real gold (the #175 desync is gone)."""

    async def run():
        store = FsDocStore(tmp_path)

        def make_ingest():
            return IngestService(
                store,
                MemoryEventBus(),
                extractor=FakePdfExtractor(),
                renderer=FakePdfRenderer(page_count=1),
                polisher=FakePolisher(),
                region_extractor=FakeRegionExtractor(),
                clock=FixedClock(ts=1700000000.0),
            )

        # First ingest seeds gold; both concurrent --force runs then re-run it.
        await make_ingest().ingest_pdf(b"%PDF-fake", "doc.pdf")
        results = await asyncio.gather(
            make_ingest().ingest_pdf(b"%PDF-fake", "doc.pdf", force=True),
            make_ingest().ingest_pdf(b"%PDF-fake", "doc.pdf", force=True),
        )
        slug = results[0]["slug"]
        # Whichever ran last, the marker reads complete and matches real gold.
        assert await store.has_gold(slug) is True
        docs = await store.list_documents()
        entry = next(d for d in docs if d["slug"] == slug)
        assert entry["has_gold"] is True
        assert entry["region_count"] == store._count_gold_regions(slug)
        assert entry["region_count"] >= 1

    asyncio.run(run())


def test_lock_released_after_ingest_so_next_force_can_run_on_fs(tmp_path):
    """The lock is released when ingest finishes; a follow-up --force is not
    blocked by a stale held lock."""

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
        await ingest.ingest_pdf(b"%PDF-fake", "doc.pdf")
        # Lock file is gone after the pass.
        assert not store._ingest_lock_path("doc").exists()
        # A fresh --force succeeds (would hang/raise if the lock leaked).
        await ingest.ingest_pdf(b"%PDF-fake", "doc.pdf", force=True)
        assert not store._ingest_lock_path("doc").exists()

    asyncio.run(run())
