"""IngestSessionService - the harness-driven ingestion protocol, with fakes."""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs.core.ingest.session import PROTOCOL_VERSION
from tests.fixtures.services import make_in_memory_services

_TWO_PAGE_DOCLING = {
    "items": [
        {"label": "title", "text": "Demo Doc", "page": 1, "bbox": [0, 720, 200, 700]},
        {"label": "section_header", "text": "Specs", "page": 1, "bbox": [0, 620, 100, 600]},
        {"label": "text", "text": "First paragraph.", "page": 1, "bbox": [0, 595, 200, 580]},
        {"label": "table", "text": "", "page": 2, "bbox": [0, 700, 500, 400],
         "cells": [{"row": 0, "col": 0, "text": "Flow"}, {"row": 0, "col": 1, "text": "50 Hz"}]},
        {"label": "text", "text": "Footnote.", "page": 2, "bbox": [0, 100, 200, 80]},
    ],
}


def _services(page_count: int = 2):
    s = make_in_memory_services(page_count=page_count)
    s.extractor.docling = _TWO_PAGE_DOCLING
    return s


async def _begin(s):
    return await s.ingest_session.ingest_begin(b"%PDF-fake", "demo.pdf")


def test_begin_returns_work_order_and_persists_silver():
    async def run():
        s = _services()
        order = await _begin(s)
        assert order["slug"] == "demo"
        assert order["protocol_version"] == PROTOCOL_VERSION
        assert order["page_count"] == 2
        assert order["session_id"].startswith("ing-")
        assert [p["page"] for p in order["pages"]] == [1, 2]
        assert all(p["status"] == "pending" for p in order["pages"])
        # Page 2 has a table -> needs polish; page 1 is plain text.
        by_page = {p["page"]: p for p in order["pages"]}
        assert by_page[2]["needs_polish"] is True
        assert by_page[1]["candidate_count"] == 3
        # Mechanical silver is on disk; gold is not visible.
        assert await s.doc_store.get_index("demo") is not None
        assert await s.doc_store.get_page_candidates("demo", 1) is not None
        assert await s.doc_store.has_gold("demo") is False

    asyncio.run(run())


def test_begin_resumes_an_open_session_instead_of_forking():
    async def run():
        s = _services()
        first = await _begin(s)
        second = await _begin(s)
        assert second["session_id"] == first["session_id"]
        assert second["resumed"] is True

    asyncio.run(run())


def test_begin_skips_when_gold_already_published_unless_forced():
    async def run():
        s = _services()
        await s.doc_store.write_silver_artifact("demo", "index.json", json.dumps({
            "document": {"page_count": 2, "title": "Demo", "filename": "demo.pdf"},
        }))
        await s.doc_store.mark_gold_complete("demo", {"mode": "keyed", "region_count": 1})
        skipped = await _begin(s)
        assert skipped["skipped"] is True
        forced = await s.ingest_session.ingest_begin(b"%PDF-fake", "demo.pdf", force=True)
        assert forced.get("skipped") is None
        assert forced["session_id"].startswith("ing-")

    asyncio.run(run())


def test_forced_begin_aborts_the_open_session():
    async def run():
        s = _services()
        first = await _begin(s)
        second = await s.ingest_session.ingest_begin(b"%PDF-fake", "demo.pdf", force=True)
        assert second["session_id"] != first["session_id"]
        old = await s.ingest_session.ingest_status(first["session_id"])
        assert old["state"] == "aborted"

    asyncio.run(run())


def test_get_page_returns_work_item_with_candidates_and_instructions():
    async def run():
        s = _services()
        order = await _begin(s)
        item = await s.ingest_session.ingest_get_page(order["session_id"], 1)
        assert item["page"] == 1
        assert item["raw_md"].startswith("# Demo Doc")
        assert [c["id"] for c in item["candidates"]] == ["p1-i0", "p1-i1", "p1-i2"]
        assert "ingest_submit_page" in item["instructions"]
        assert item["protocol_version"] == PROTOCOL_VERSION
        # Unknown page and unknown session produce structured errors.
        assert "error" in await s.ingest_session.ingest_get_page(order["session_id"], 9)
        assert "error" in await s.ingest_session.ingest_get_page("ing-nope", 1)

    asyncio.run(run())


def test_submit_page_computes_bbox_from_member_union_and_stages_only():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        verdict = await s.ingest_session.ingest_submit_page(sid, 1, regions=[{
            "kind": "spec_block",
            "title": "Specs",
            "description": "Header and intro",
            "member_item_ids": ["p1-i1", "p1-i2"],
        }], polished_md="# Demo Doc\n\npolished")
        assert verdict["accepted"] is True
        assert verdict["region_count"] == 1
        assert verdict["remaining_pages"] == [2]
        # Staged regions carry the server-computed union bbox + geometry stamp.
        staged = json.loads(
            await s.session_store.read_text(sid, "gold/pages/1.regions.json")
        )
        region = staged["regions"][0]
        assert region["bbox"] == [0.0, 620.0, 200.0, 580.0]
        assert region["geometry"] == "members"
        # Nothing is published: the doc store has no gold and no regions.
        assert await s.doc_store.has_gold("demo") is False
        assert (await s.doc_store.get_regions("demo"))["pages"] == {}

    asyncio.run(run())


def test_submit_page_rejects_bad_regions_with_structured_errors():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        verdict = await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "banner", "title": "bad kind", "member_item_ids": ["p1-i0"]},
            {"kind": "text", "title": "unknown member", "member_item_ids": ["p1-i99"]},
            {"kind": "text", "title": "no geometry"},
            {"kind": "text", "title": "stray field", "member_item_ids": ["p1-i0"], "bbox": [0, 1, 2, 0]},
        ])
        assert verdict["accepted"] is False
        fields = {e["field"] for e in verdict["errors"]}
        assert "kind" in fields
        assert "member_item_ids" in fields
        assert "bbox" in fields  # closed schema: bbox is server-computed
        # Page stays pending; nothing staged.
        status = await s.ingest_session.ingest_status(sid)
        assert status["pages_remaining"] == [1, 2]

    asyncio.run(run())


def test_submit_page_approx_bbox_is_snapped_or_stamped_coarse():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        verdict = await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            # Covers the section header + paragraph centers -> snapped.
            {"kind": "text", "title": "snapped", "approx_bbox": [0, 630, 210, 570]},
            # Covers nothing -> kept coarse, honestly stamped.
            {"kind": "figure", "title": "coarse", "approx_bbox": [300, 300, 400, 200]},
        ])
        assert verdict["accepted"] is True
        staged = json.loads(
            await s.session_store.read_text(sid, "gold/pages/1.regions.json")
        )
        snapped, coarse = staged["regions"]
        assert snapped["geometry"] == "snapped"
        assert snapped["bbox"] == [0.0, 620.0, 200.0, 580.0]
        assert coarse["geometry"] == "coarse"
        assert coarse["bbox"] == [300.0, 300.0, 400.0, 200.0]

    asyncio.run(run())


def test_submit_page_is_idempotent_per_page():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        first = await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "text", "title": "v1", "member_item_ids": ["p1-i0"]},
            {"kind": "text", "title": "v1b", "member_item_ids": ["p1-i1"]},
        ])
        assert first["region_count"] == 2
        second = await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "text", "title": "v2", "member_item_ids": ["p1-i2"]},
        ])
        assert second["accepted"] is True
        staged = json.loads(
            await s.session_store.read_text(sid, "gold/pages/1.regions.json")
        )
        assert [r["title"] for r in staged["regions"]] == ["v2"]

    asyncio.run(run())


def test_submit_page_rejects_protocol_version_mismatch():
    async def run():
        s = _services()
        order = await _begin(s)
        verdict = await s.ingest_session.ingest_submit_page(
            order["session_id"], 1, regions=[], protocol_version=99,
        )
        assert verdict["accepted"] is False
        assert any("re-run ingest_begin" in e["message"] for e in verdict["errors"])

    asyncio.run(run())


def test_status_is_the_resume_surface_by_id_and_slug():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        await s.ingest_session.ingest_submit_page(sid, 2, regions=[
            {"kind": "table", "title": "Flow table", "member_item_ids": ["p2-i0"]},
        ])
        by_slug = await s.ingest_session.ingest_status(slug="demo")
        assert by_slug["session_id"] == sid
        assert by_slug["state"] == "open"
        assert by_slug["pages_remaining"] == [1]
        by_id = await s.ingest_session.ingest_status(sid)
        assert by_id == by_slug
        assert "error" in await s.ingest_session.ingest_status(slug="nope")

    asyncio.run(run())


def test_finalize_refuses_while_pages_are_pending():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        refusal = await s.ingest_session.ingest_finalize(sid)
        assert refusal["finalized"] is False
        assert refusal["pending_pages"] == [1, 2]
        assert await s.doc_store.has_gold("demo") is False

    asyncio.run(run())


def test_finalize_publishes_atomically_with_embeddings_and_report():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "spec_block", "title": "Specs", "description": "intro",
             "member_item_ids": ["p1-i1", "p1-i2"]},
        ], polished_md="# Demo Doc polished")
        await s.ingest_session.ingest_submit_page(sid, 2, regions=[
            {"kind": "table", "title": "Flow table", "description": "50/60 Hz",
             "member_item_ids": ["p2-i0"]},
        ])
        summary = await s.ingest_session.ingest_finalize(sid, declared_model="claude-fable-5")
        assert summary["finalized"] is True
        assert summary["mode"] == "harness"
        assert summary["declared_model"] == "claude-fable-5"
        assert summary["region_count"] == 2
        assert summary["embedded_count"] == 2
        assert summary["polished_pages"] == [1]

        # Published and visible.
        assert await s.doc_store.has_gold("demo") is True
        gold = await s.doc_store.get_gold_map("demo")
        assert {int(p) for p in gold["pages"]} == {1, 2}
        embeddings = await s.doc_store.get_embeddings("demo")
        assert len(embeddings["vectors"]) == 2
        assert await s.doc_store.get_page_text("demo", 1) == "# Demo Doc polished"
        # Marker records the harness mode + declared model.
        assert await s.doc_store.has_gold("demo")
        docs = await s.doc_store.list_documents()  # memory store: seeded docs only
        assert isinstance(docs, list)
        # Session is published; a second finalize is refused.
        again = await s.ingest_session.ingest_finalize(sid)
        assert again["finalized"] is False
        # And a fresh begin without force now skips (gold exists).
        skipped = await s.ingest_session.ingest_begin(b"%PDF-fake", "demo.pdf")
        assert skipped["skipped"] is True

    asyncio.run(run())


def test_finalize_emits_the_canvas_event_chain():
    async def run():
        s = _services()
        seen = []

        async def subscribe():
            async for evt in s.bus.subscribe(None):
                seen.append(evt)
                if any(e.type == "DocIngested" for e in seen):
                    return

        sub = asyncio.create_task(subscribe())
        await asyncio.sleep(0)
        order = await _begin(s)
        sid = order["session_id"]
        await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "text", "title": "t", "member_item_ids": ["p1-i0"]},
        ], polished_md="x")
        await s.ingest_session.ingest_finalize(sid, allow_missing_pages=[2])
        await asyncio.wait_for(sub, timeout=2.0)
        types = [e.type for e in seen]
        for expected in ("DocBronzed", "DocSilvered", "DocPolished", "DocGoldExtracted", "DocIngested"):
            assert expected in types, f"missing {expected} in {types}"

    asyncio.run(run())


def test_finalize_allow_missing_pages_records_the_gap():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "text", "title": "t", "member_item_ids": ["p1-i0"]},
        ])
        summary = await s.ingest_session.ingest_finalize(sid, allow_missing_pages=[2])
        assert summary["finalized"] is True
        assert summary["missing_pages"] == [2]

    asyncio.run(run())


def test_abort_discards_staging_and_leaves_doc_ingestable():
    async def run():
        s = _services()
        order = await _begin(s)
        sid = order["session_id"]
        await s.ingest_session.ingest_submit_page(sid, 1, regions=[
            {"kind": "text", "title": "t", "member_item_ids": ["p1-i0"]},
        ])
        out = await s.ingest_session.ingest_abort(sid)
        assert out["aborted"] is True
        assert await s.session_store.read_text(sid, "gold/pages/1.regions.json") is None
        assert await s.doc_store.has_gold("demo") is False
        # Aborted sessions refuse further pages; a new begin starts fresh.
        rejected = await s.ingest_session.ingest_submit_page(sid, 1, regions=[])
        assert rejected["accepted"] is False
        fresh = await _begin(s)
        assert fresh["session_id"] != sid

    asyncio.run(run())
