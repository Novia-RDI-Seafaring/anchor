"""MCP harness ingest-session tools - handlers called without transport."""
from __future__ import annotations

import asyncio
import json

from anchor.extensions.anchor_pdfs import mcp_handlers as pdf_handlers
from tests.fixtures.services import make_in_memory_services


async def _call(s, name, args):
    body = await pdf_handlers.call_tool(
        s.ingest, s.doc_store, name, args, ingest_session=s.ingest_session,
    )
    return json.loads(body)


def test_full_session_loop_over_mcp(tmp_path):
    async def run():
        s = make_in_memory_services(page_count=1)
        pdf = tmp_path / "demo.pdf"
        pdf.write_bytes(b"%PDF-fake")

        order = await _call(s, "ingest_begin", {"pdf_path": str(pdf)})
        assert order["slug"] == "demo"
        sid = order["session_id"]
        assert order["pages"][0]["status"] == "pending"

        item = await _call(s, "ingest_get_page", {"session_id": sid, "page": 1})
        assert item["raw_md"].startswith("# Demo Doc")
        assert [c["id"] for c in item["candidates"]] == ["p1-i0", "p1-i1", "p1-i2"]
        # Memory doc store has no image path: the envelope says so instead
        # of pretending.
        assert "error" in item["image"]

        verdict = await _call(s, "ingest_submit_page", {
            "session_id": sid, "page": 1,
            "regions": [{"kind": "text", "title": "Intro", "member_item_ids": ["p1-i0", "p1-i2"]}],
            "polished_md": "# Demo Doc\n\npolished",
        })
        assert verdict["accepted"] is True

        status = await _call(s, "ingest_status", {"slug": "demo"})
        assert status["pages_remaining"] == []

        summary = await _call(s, "ingest_finalize", {
            "session_id": sid, "declared_model": "claude-fable-5",
        })
        assert summary["finalized"] is True
        assert summary["mode"] == "harness"
        assert await s.doc_store.has_gold("demo") is True

    asyncio.run(run())


def test_submit_rejection_round_trips_structured_errors(tmp_path):
    async def run():
        s = make_in_memory_services(page_count=1)
        pdf = tmp_path / "demo.pdf"
        pdf.write_bytes(b"%PDF-fake")
        order = await _call(s, "ingest_begin", {"pdf_path": str(pdf)})
        verdict = await _call(s, "ingest_submit_page", {
            "session_id": order["session_id"], "page": 1,
            "regions": [{"kind": "banner", "title": "bad"}],
        })
        assert verdict["accepted"] is False
        assert any(e["field"] == "kind" for e in verdict["errors"])

    asyncio.run(run())


def test_abort_over_mcp(tmp_path):
    async def run():
        s = make_in_memory_services(page_count=1)
        pdf = tmp_path / "demo.pdf"
        pdf.write_bytes(b"%PDF-fake")
        order = await _call(s, "ingest_begin", {"pdf_path": str(pdf)})
        out = await _call(s, "ingest_abort", {"session_id": order["session_id"]})
        assert out["aborted"] is True

    asyncio.run(run())


def test_missing_pdf_and_unwired_service_report_errors(tmp_path):
    async def run():
        s = make_in_memory_services(page_count=1)
        missing = await _call(s, "ingest_begin", {"pdf_path": str(tmp_path / "nope.pdf")})
        assert "error" in missing
        # A server built without the session service answers honestly.
        body = await pdf_handlers.call_tool(
            s.ingest, s.doc_store, "ingest_status", {"slug": "demo"},
        )
        assert "not wired" in json.loads(body)["error"]

    asyncio.run(run())
