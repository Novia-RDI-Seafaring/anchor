"""Agent intent queue surface (issue #148).

The project-level intent queue, exposed over HTTP for parity with MCP / CLI:

- ``GET  /api/intents``            — list pending intents (optionally ?canvas=).
- ``GET  /api/intents/all``        — list every intent (audit/UI).
- ``POST /api/intents``            — enqueue an intent.
- ``POST /api/intents/{id}/resolve`` — mark one resolved with a result.
- ``GET  /api/intents/events``     — SSE stream of the ``intent_pending`` signal.

The SSE stream carries the *count only*, never the payload: it is the push-half
of the push-notify / pull-payload design. A client (the canvas UI, or a harness)
learns that work is waiting and then pulls the payload via ``GET /api/intents``.
The signal rides the existing event bus (``IntentPending`` domain events) — the
same machinery the canvas SSE uses — so an enqueue in this process is delivered
without a poll. Mounted under ``/_stream`` style fixed paths so nothing collides
with an intent id segment.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import get_intent_service
from anchor.core.intents.intent import INTENT_KINDS, INTENT_PENDING_EVENT
from anchor.core.services.intent_service import IntentService, UnknownIntentKindError

router = APIRouter(prefix="/api/intents", tags=["intents"])


@router.get("")
async def list_pending(
    canvas: str | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """Pending intents for this project (oldest first), optionally per-canvas."""
    pending = await intents.list_pending(canvas=canvas)
    return {"intents": [i.to_dict() for i in pending], "count": len(pending)}


@router.get("/all")
async def list_all(
    canvas: str | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """Every intent (pending + resolved), newest first."""
    items = await intents.list_all(canvas=canvas)
    return {"intents": [i.to_dict() for i in items]}


@router.post("")
async def enqueue(
    body: dict,
    intents: IntentService = Depends(get_intent_service),
):
    """Enqueue an intent. ``{kind, origin_canvas_id?, target?, payload?}``."""
    try:
        intent = await intents.enqueue(
            body.get("kind", ""),
            origin_canvas_id=body.get("origin_canvas_id"),
            target=body.get("target"),
            payload=body.get("payload"),
        )
    except UnknownIntentKindError:
        # Return a fixed, safe message (the valid kinds are a static set) rather
        # than echoing the exception text -- keeps client-controlled input out
        # of the error body.
        return {
            "error": "unknown_kind",
            "message": "unknown intent kind",
            "valid_kinds": sorted(INTENT_KINDS),
        }
    return {"intent": intent.to_dict()}


@router.post("/{intent_id}/resolve")
async def resolve(
    intent_id: str,
    body: dict | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """Mark an intent resolved with an optional ``result`` payload."""
    result = (body or {}).get("result")
    try:
        resolved = await intents.resolve(intent_id, result)
    except KeyError:
        return {"error": "not_found", "id": intent_id}
    return {"resolved": resolved.to_dict()}


@router.get("/events")
async def events(
    request: Request,
    canvas: str | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """SSE stream of the ``intent_pending`` count signal.

    Emits the current pending count immediately, then re-emits on each
    ``IntentPending`` bus event. The payload is ``{count}`` only — a client
    pulls the intents themselves from ``GET /api/intents``.
    """
    bus = request.app.state.bus

    async def stream():
        # Subscribe to the global firehose (count signals carry a project /
        # canvas workspace id, not necessarily the viewing canvas) and filter
        # to IntentPending here.
        subscription = bus.subscribe(None)
        events_it = subscription.__aiter__()
        next_event = asyncio.create_task(anext(events_it))
        await asyncio.sleep(0)

        # Initial snapshot so a freshly-opened client is correct at once.
        count = len(await intents.list_pending(canvas=canvas))
        yield {"event": "intent_pending", "data": json.dumps({"count": count})}
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    evt = await next_event
                except StopAsyncIteration:
                    return
                next_event = asyncio.create_task(anext(events_it))
                if evt.type != INTENT_PENDING_EVENT:
                    continue
                count = len(await intents.list_pending(canvas=canvas))
                yield {"event": "intent_pending", "data": json.dumps({"count": count})}
        finally:
            next_event.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                _ = await next_event
            aclose = getattr(events_it, "aclose", None)
            if aclose is not None:
                await aclose()

    return EventSourceResponse(stream(), ping=15)
