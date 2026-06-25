"""Adapter parity for the ingestion-activity surface (issue #51): HTTP list +
per-slug endpoints and the MCP list_active_ingests / get_ingest_status tools,
all reading the same durable records the pipeline writes.
"""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs import mcp_handlers
from tests.fixtures.services import make_in_memory_services


def _client():
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app), s


def _seed(s, slug="alpha", **over):
    rec = {
        "slug": slug, "filename": f"{slug}.pdf", "stage": "gold_regions",
        "current": 2, "total": 4, "status": "running",
        "started_at": 1.0, "updated_at": 2.0,
    }
    rec.update(over)
    asyncio.run(s.doc_store.write_ingest_activity(slug, rec))


def test_http_list_active_ingests():
    client, s = _client()
    assert client.get("/api/ingests").json() == {"ingests": []}
    _seed(s, "alpha")
    body = client.get("/api/ingests").json()
    assert len(body["ingests"]) == 1
    entry = body["ingests"][0]
    assert entry["slug"] == "alpha"
    assert entry["stage"] == "gold_regions"
    assert entry["pct"] == 50  # 2/4


def test_http_ingest_status_per_slug():
    client, s = _client()
    miss = client.get("/api/ingests/ghost").json()
    assert miss == {"slug": "ghost", "found": False}
    _seed(s, "beta", status="failed", stage="silver_extract", error="boom")
    hit = client.get("/api/ingests/beta").json()
    assert hit["found"] is True
    assert hit["status"] == "failed"
    assert hit["stage"] == "silver_extract"
    assert hit["error"] == "boom"


def test_http_events_stream_emits_initial_snapshot():
    """The SSE stream emits the current activity list as its first event.

    Driven directly against the route's async generator (rather than the
    blocking TestClient SSE transport, which never closes the long-lived
    EventSource): read exactly the first yielded event, then stop.
    """
    from anchor.adapters.http.routers import ingests as ingests_router

    s = make_in_memory_services()
    _seed(s, "gamma")

    class _Req:  # minimal stand-in for fastapi Request
        async def is_disconnected(self):
            return False

    async def run():
        # The route returns an EventSourceResponse wrapping the generator; we
        # call the route fn to build it, then pull one item off the body
        # iterator and assert it carries our seeded ingest.
        response = await ingests_router.events(_Req(), store=s.doc_store)
        agen = response.body_iterator
        first = await agen.__anext__()
        await agen.aclose()
        return first

    first = asyncio.run(run())
    text = first if isinstance(first, str) else first.get("data", "")
    assert "gamma" in text
    payload = json.loads(text.split("data:", 1)[1] if "data:" in text else text)
    assert any(a["slug"] == "gamma" for a in payload)


def test_mcp_list_active_ingests_and_status():
    s = make_in_memory_services()
    _seed(s, "delta")

    async def run():
        listed = json.loads(
            await mcp_handlers.call_tool(s.ingest, s.doc_store, "list_active_ingests", {})
        )
        assert [a["slug"] for a in listed["ingests"]] == ["delta"]

        status = json.loads(
            await mcp_handlers.call_tool(
                s.ingest, s.doc_store, "get_ingest_status", {"slug": "delta"}
            )
        )
        assert status["found"] is True and status["slug"] == "delta"

        missing = json.loads(
            await mcp_handlers.call_tool(
                s.ingest, s.doc_store, "get_ingest_status", {"slug": "nope"}
            )
        )
        assert missing == {"slug": "nope", "found": False}

    asyncio.run(run())
