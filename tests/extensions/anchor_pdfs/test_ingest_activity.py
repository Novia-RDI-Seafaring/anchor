"""Ingest-activity surface (issue #51): the registry read model, the durable
records the pipeline writes, and the cross-process rebuild-from-disk path.

The cross-process guarantee is the load-bearing one: an ingest run in another
process leaves records on disk, so a *fresh* registry/store built over the same
data dir (the "server that never touched the ingest" case) still sees it.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_pdfs.core.ingest_activity import (
    DEFAULT_TERMINAL_TTL_SECONDS,
    IngestActivity,
    IngestActivityRegistry,
)
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


def test_activity_pct_and_roundtrip():
    a = IngestActivity(slug="x", stage="gold_regions", current=3, total=4)
    assert a.pct == 75
    # No denominator -> indeterminate (None), not a divide error.
    assert IngestActivity(slug="x", stage="bronze").pct is None
    back = IngestActivity.from_dict(a.to_dict())
    assert back.slug == "x" and back.stage == "gold_regions" and back.pct == 75


def test_registry_lists_running_and_prunes_old_terminal():
    async def run():
        store = FsDocStore_tmp()
        clock = FixedClock(ts=1000.0)
        registry = IngestActivityRegistry(
            store=store, _now=clock.now, terminal_ttl_seconds=DEFAULT_TERMINAL_TTL_SECONDS,
        )
        # A running one, a fresh terminal one, and a stale terminal one.
        await store.write_ingest_activity("run", {
            "slug": "run", "stage": "embed", "status": "running",
            "started_at": 1000.0, "updated_at": 1000.0,
        })
        await store.write_ingest_activity("fresh", {
            "slug": "fresh", "stage": "embed", "status": "done",
            "started_at": 990.0, "updated_at": 995.0,  # 5s old < TTL
        })
        await store.write_ingest_activity("stale", {
            "slug": "stale", "stage": "embed", "status": "failed",
            "started_at": 100.0, "updated_at": 100.0,  # 900s old > TTL
        })
        snap = await registry.snapshot()
        slugs = {a.slug for a in snap}
        assert "run" in slugs  # running always shown
        assert "fresh" in slugs  # recent terminal shown
        assert "stale" not in slugs  # old terminal pruned
        # get() ignores the TTL — it is a direct lookup.
        stale = await registry.get("stale")
        assert stale is not None and stale.status == "failed"

    asyncio.run(run())


def FsDocStore_tmp() -> FsDocStore:
    import tempfile
    return FsDocStore(tempfile.mkdtemp())


def _ingest(store, clock):
    return IngestService(
        store,
        MemoryEventBus(),
        extractor=FakePdfExtractor(),
        renderer=FakePdfRenderer(page_count=1),
        polisher=FakePolisher(),
        region_extractor=FakeRegionExtractor(),
        clock=clock,
    )


def test_pipeline_writes_activity_and_resolves_done(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        clock = FixedClock(ts=2000.0)
        await _ingest(store, clock).ingest_pdf(b"%PDF-fake", "ok.pdf")

        # A durable record landed on disk.
        rec_path = tmp_path / "ingest_status" / "ok.json"
        assert rec_path.is_file()
        rec = json.loads(rec_path.read_text())
        assert rec["slug"] == "ok"
        assert rec["status"] == "done"

        # And the registry surfaces it as resolved (fresh terminal).
        registry = IngestActivityRegistry(store=store, _now=clock.now)
        got = await registry.get("ok")
        assert got is not None and got.status == "done" and got.filename == "ok.pdf"

    asyncio.run(run())


def test_pipeline_writes_failed_activity_with_stage(tmp_path):
    class Boom:
        async def extract(self, _p):
            raise RuntimeError("docling exploded")

    async def run():
        store = FsDocStore(tmp_path)
        clock = FixedClock(ts=3000.0)
        ingest = _ingest(store, clock)
        ingest.extractor = Boom()  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="docling exploded"):
            await ingest.ingest_pdf(b"%PDF-fake", "boom.pdf")

        registry = IngestActivityRegistry(store=store, _now=clock.now)
        got = await registry.get("boom")
        assert got is not None
        assert got.status == "failed"
        assert got.stage == "silver_extract"  # the real failing stage
        assert "docling exploded" in (got.error or "")

    asyncio.run(run())


def test_cross_process_rebuild_from_disk(tmp_path):
    """An ingest run by one store/process is visible to a SECOND store built
    over the same data dir that never saw the in-process bus events."""
    async def run():
        clock = FixedClock(ts=4000.0)
        # "Process A" runs the ingest.
        store_a = FsDocStore(tmp_path)
        await _ingest(store_a, clock).ingest_pdf(b"%PDF-fake", "shared.pdf")

        # "Process B" — a brand-new store + registry over the same dir, with
        # its own (empty) bus. It only knows what is on disk.
        store_b = FsDocStore(tmp_path)
        registry_b = IngestActivityRegistry(store=store_b, _now=clock.now)
        snap = await registry_b.snapshot()
        assert any(a.slug == "shared" for a in snap), (
            "a CLI/MCP-triggered ingest must be visible to a server that never "
            "touched its event bus"
        )

    asyncio.run(run())
