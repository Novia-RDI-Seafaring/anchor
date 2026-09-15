"""Agent intent queue surface (issue #148) and scoped-ask threads (#343).

The project-level intent queue, exposed over HTTP for parity with MCP / CLI:

- ``GET  /api/intents``            — list pending intents (optionally ?canvas=).
- ``GET  /api/intents/all``        — list every intent (audit/UI).
- ``POST /api/intents``            — enqueue an intent (``targets[]`` makes it a thread).
- ``POST /api/intents/{id}/resolve`` — mark one resolved with a result.
- ``GET  /api/intents/events``     — SSE stream of the ``intent_pending`` signal.
- ``GET  /api/intents/{id}``       — one full record incl. thread items.
- ``POST /api/intents/{id}/items`` — append a thread item.
- ``POST /api/intents/{id}/items/{item}/answer``  — answer a question.
- ``POST /api/intents/{id}/items/{item}/apply``   — approve + apply a suggestion.
- ``POST /api/intents/{id}/items/{item}/decline`` — decline a suggestion.

The SSE stream carries the *count only*, never the payload: it is the push-half
of the push-notify / pull-payload design. A client (the canvas UI, or a harness)
learns that work is waiting and then pulls the payload via ``GET /api/intents``.
The signal rides the existing event bus (``IntentPending`` domain events) — the
same machinery the canvas SSE uses — so an enqueue in this process is delivered
without a poll. Thread mutations re-fire the same signal so a panel refetches.
Fixed sub-paths (``/all``, ``/events``) are declared before ``/{intent_id}`` so
nothing collides with an intent id segment.

Thread routes answer ``{error: <code>, message}`` with 404 (unknown intent /
item), 400 (malformed item, targets, or ops), or 409 (state conflicts and
``apply_failed``, which adds ``failing_index``, ``reason``, ``stale``). Item
``author`` is the request's actor: the #322 middleware default (human /
browser), or the body's ``actor`` override as on canvas writes.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import apply_actor_override, get_intent_service
from anchor.core.events.actor import Actor
from anchor.core.intents.intent import INTENT_KINDS, INTENT_PENDING_EVENT
from anchor.core.services.intent_service import (
    IntentService,
    SuggestionApplyError,
    ThreadError,
    UnknownIntentKindError,
)

router = APIRouter(prefix="/api/intents", tags=["intents"])


def _actor_override(body: dict[str, Any] | None) -> None:
    raw = (body or {}).get("actor")
    if isinstance(raw, dict) and raw.get("kind"):
        apply_actor_override(Actor(**raw))


def _not_found(intent_id: str, item_id: str | None = None) -> JSONResponse:
    content: dict[str, Any] = {"error": "not_found", "id": intent_id}
    if item_id is not None:
        content["item_id"] = item_id
    return JSONResponse(status_code=404, content=content)


def _thread_error(exc: ThreadError) -> JSONResponse:
    if isinstance(exc, SuggestionApplyError):
        return JSONResponse(status_code=409, content={**exc.to_dict(), "message": str(exc)})
    status = 404 if exc.code == "item_not_found" else (
        409 if exc.code in {"not_pending", "not_a_question", "not_a_suggestion"} else 400
    )
    return JSONResponse(status_code=status, content={"error": exc.code, "message": str(exc)})


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
    """Enqueue an intent. ``{kind, origin_canvas_id?, target?, payload?, targets?}``.

    ``targets`` (``[{workspace_id, node_id}]``) anchors the ask to a canvas
    selection (a thread, #343); the server records ``base_version`` from the
    origin canvas itself.
    """
    try:
        intent = await intents.enqueue(
            body.get("kind", ""),
            origin_canvas_id=body.get("origin_canvas_id"),
            target=body.get("target"),
            payload=body.get("payload"),
            targets=body.get("targets"),
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
    except ThreadError as exc:
        return _thread_error(exc)
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


# -- threads (#343) ---------------------------------------------------------- #
# Declared after the fixed sub-paths so `/all` and `/events` never match as an
# intent id.


@router.get("/{intent_id}")
async def get_intent(
    intent_id: str,
    intents: IntentService = Depends(get_intent_service),
):
    """One intent, the full record: targets, base_version, and every item."""
    intent = await intents.get(intent_id)
    if intent is None:
        return _not_found(intent_id)
    return {"intent": intent.to_dict()}


@router.post("/{intent_id}/items")
async def add_item(
    intent_id: str,
    body: dict,
    intents: IntentService = Depends(get_intent_service),
):
    """Append a thread item: ``{type, text?, ops?, supersedes?}``."""
    _actor_override(body)
    try:
        intent, item = await intents.add_item(
            intent_id,
            type=str(body.get("type") or ""),
            text=body.get("text") or "",
            ops=body.get("ops"),
            supersedes=body.get("supersedes"),
        )
    except KeyError:
        return _not_found(intent_id)
    except ThreadError as exc:
        return _thread_error(exc)
    return {"intent": intent.to_dict(), "item": item.to_dict()}


@router.post("/{intent_id}/items/{item_id}/answer")
async def answer_question(
    intent_id: str,
    item_id: str,
    body: dict,
    intents: IntentService = Depends(get_intent_service),
):
    """Answer an open question: ``{text}``."""
    _actor_override(body)
    try:
        intent, item = await intents.answer_question(
            intent_id, item_id, text=body.get("text") or "",
        )
    except KeyError:
        return _not_found(intent_id)
    except ThreadError as exc:
        return _thread_error(exc)
    return {"intent": intent.to_dict(), "item": item.to_dict()}


@router.post("/{intent_id}/items/{item_id}/apply")
async def apply_suggestion(
    intent_id: str,
    item_id: str,
    body: dict | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """Approve a pending suggestion and apply its ops all-or-nothing.

    409 ``apply_failed`` carries ``failing_index`` / ``reason`` / ``stale``
    and means the canvas is untouched.
    """
    _actor_override(body)
    try:
        intent, item, applied = await intents.apply_suggestion(intent_id, item_id)
    except KeyError:
        return _not_found(intent_id)
    except ThreadError as exc:
        return _thread_error(exc)
    return {"intent": intent.to_dict(), "item": item.to_dict(), "applied": applied}


@router.post("/{intent_id}/items/{item_id}/decline")
async def decline_suggestion(
    intent_id: str,
    item_id: str,
    body: dict | None = None,
    intents: IntentService = Depends(get_intent_service),
):
    """Decline a pending suggestion; ``{comment?}`` becomes a message item."""
    _actor_override(body)
    try:
        intent, item = await intents.decline_suggestion(
            intent_id, item_id, comment=(body or {}).get("comment"),
        )
    except KeyError:
        return _not_found(intent_id)
    except ThreadError as exc:
        return _thread_error(exc)
    return {"intent": intent.to_dict(), "item": item.to_dict()}
