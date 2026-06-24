"""Project-level ingestion-activity surface (issue #51).

Two endpoints back the canvas "N ingesting" pill:

- ``GET /api/ingests`` — a one-shot list of in-flight (and just-resolved)
  ingests, read from the durable per-slug activity records. An agent or a
  page-load uses this.
- ``GET /api/ingests/events`` — an SSE stream that re-reads the registry on a
  short cadence and emits the list whenever it changes. Because the registry
  reads the records off disk, an ingest started by the CLI or an MCP-stdio
  subprocess appears here within one tick even though it ran in another
  process — that cross-trigger visibility is the whole point of #51.

The poll loop (rather than tailing the bus) is deliberate: ingest events are
published on the in-process bus only and are never written to a workspace's
``events.jsonl``, so the cross-process truth lives in the activity records, not
on any event log. Polling those records is the one surface that sees every
trigger uniformly.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import get_doc_store
from anchor.core.clock import SystemClock
from anchor.extensions.anchor_pdfs.core.ingest_activity import IngestActivityRegistry
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore

router = APIRouter(prefix="/api/ingests", tags=["ingests"])

#: How often the SSE loop re-reads the activity records. Fast enough to meet
#: the #51 acceptance ("the pill shows a CLI ingest within ~1s") with margin.
_POLL_SECONDS = 0.5


def _registry(store: DocStore) -> IngestActivityRegistry:
    clock = SystemClock()
    return IngestActivityRegistry(store=store, _now=clock.now)


@router.get("")
async def list_active_ingests(store: DocStore = Depends(get_doc_store)):
    """Active (and just-resolved) ingests for this project."""
    activities = await _registry(store).snapshot()
    return {"ingests": [a.to_dict() for a in activities]}


@router.get("/{slug}")
async def ingest_status(slug: str, store: DocStore = Depends(get_doc_store)):
    """The activity record for one slug, or ``{found: false}``."""
    activity = await _registry(store).get(slug)
    if activity is None:
        return {"slug": slug, "found": False}
    return {"found": True, **activity.to_dict()}


@router.get("/_stream/events")
async def events(request: Request, store: DocStore = Depends(get_doc_store)):
    """SSE stream of the active-ingest list; emits on every change.

    Mounted under ``_stream`` so it never collides with a slug. Sends an
    initial ``ingests`` event immediately, then one each time the set changes,
    plus periodic keep-alive pings (matching the canvas SSE route) so idle
    browsers stay subscribed.
    """
    registry = _registry(store)

    async def stream():
        last: str | None = None
        # Emit immediately so a freshly-opened page is correct without waiting
        # a poll tick.
        snapshot = await registry.snapshot()
        last = json.dumps([a.to_dict() for a in snapshot])
        yield {"event": "ingests", "data": last}
        while True:
            with suppress(asyncio.CancelledError):
                await asyncio.sleep(_POLL_SECONDS)
            if await request.is_disconnected():
                return
            snapshot = await registry.snapshot()
            current = json.dumps([a.to_dict() for a in snapshot])
            if current != last:
                last = current
                yield {"event": "ingests", "data": current}

    return EventSourceResponse(stream(), ping=15)
