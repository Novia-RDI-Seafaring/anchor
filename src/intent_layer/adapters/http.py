"""Agent intent queue surface (issue #148) and scoped-ask threads (#343).

The project-level intent queue, exposed over HTTP for parity with MCP / CLI:

- ``GET  /api/intents``            - list pending intents (optionally ?canvas=).
- ``GET  /api/intents/all``        - list every intent (audit/UI).
- ``POST /api/intents``            - enqueue an intent (``targets[]`` makes it a thread).
- ``POST /api/intents/{id}/resolve`` - mark one resolved with a result.
- ``GET  /api/intents/events``     - SSE stream of the ``intent_pending`` signal.
- ``GET  /api/intents/{id}``       - one full record incl. thread items.
- ``POST /api/intents/{id}/items`` - append a thread item.
- ``POST /api/intents/{id}/items/{item}/answer``  - answer a question.
- ``POST /api/intents/{id}/items/{item}/apply``   - approve + apply a suggestion.
- ``POST /api/intents/{id}/items/{item}/decline`` - decline a suggestion.

The SSE stream carries the *count only*, never the payload: it is the push-half
of the push-notify / pull-payload design. A client (the canvas UI, or a harness)
learns that work is waiting and then pulls the payload via ``GET /api/intents``.
The host supplies a count-signal source. Thread mutations re-fire the same
signal so a panel refetches; the router does not require a canvas event bus.
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
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sse_starlette.sse import EventSourceResponse

from intent_layer.actor import Actor, actor_scope, current_actor, set_current_actor
from intent_layer.models import INTENT_KINDS
from intent_layer.service import (
    IntentService,
    SuggestionApplyError,
    ThreadError,
    UnknownIntentKindError,
)
from intent_layer.signals import PendingSignals


def create_router(get_intent_service: Callable[..., IntentService],
                  get_signals: Callable[..., PendingSignals], *,
                  prefix: str = "/api/intents",
                  default_actor: Actor | None = None) -> APIRouter:
    """Mount thread routes with host-provided service and count signals."""

    class ActorScopedRoute(APIRoute):
        def get_route_handler(self):
            handler = super().get_route_handler()

            async def scoped_handler(request: Request):
                actor = current_actor() or default_actor or Actor(kind="human", label="browser")
                with actor_scope(actor):
                    return await handler(request)

            return scoped_handler

    router = APIRouter(prefix=prefix, tags=["intents"], route_class=ActorScopedRoute)


    def _actor_override(body: dict[str, Any] | None) -> None:
        raw = (body or {}).get("actor")
        if isinstance(raw, dict) and raw.get("kind"):
            set_current_actor(Actor(**raw))
        elif current_actor() is None:
            set_current_actor(default_actor or Actor(kind="human", label="browser"))


    def _not_found(intent_id: str, item_id: str | None = None) -> JSONResponse:
        content: dict[str, Any] = {"error": "not_found", "id": intent_id}
        if item_id is not None:
            content["item_id"] = item_id
        return JSONResponse(status_code=404, content=content)


    def _thread_error(exc: ThreadError) -> JSONResponse:
        # `exc.message` is the literal authored at the raise site; never str(exc),
        # so no exception rendering flows to the client.
        if isinstance(exc, SuggestionApplyError):
            return JSONResponse(status_code=409, content={**exc.to_dict(), "message": exc.message})
        status = 404 if exc.code == "item_not_found" else (
            409 if exc.code in {"not_pending", "not_a_question", "not_a_suggestion"} else 400
        )
        return JSONResponse(status_code=status, content={"error": exc.code, "message": exc.message})


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

        ``targets`` contains opaque host identifiers. The service records
        ``base_version`` from the host and preserves the legacy origin name.
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
        signals: PendingSignals = Depends(get_signals),
    ):
        """SSE stream of the ``intent_pending`` count signal.

        Emits the current pending count immediately, then re-emits on each
        ``IntentPending`` bus event. The payload is ``{count}`` only - a client
        pulls the intents themselves from ``GET /api/intents``.
        """
        bus = signals

        async def stream():
            # Count signals are already filtered by the host's signal port.
            subscription = bus.subscribe()
            events_it = subscription.__aiter__()
            next_event = asyncio.create_task(anext(events_it))
            await asyncio.sleep(0)

            try:
                # Subscribe before the snapshot, and clean up even if the
                # snapshot fails or the client leaves at the initial yield.
                count = len(await intents.list_pending(canvas=canvas))
                yield {"event": "intent_pending", "data": json.dumps({"count": count})}
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        await next_event
                    except StopAsyncIteration:
                        return
                    next_event = asyncio.create_task(anext(events_it))
                    count = len(await intents.list_pending(canvas=canvas))
                    yield {"event": "intent_pending", "data": json.dumps({"count": count})}
            finally:
                next_event.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    _ = await next_event
                aclose = getattr(events_it, "aclose", None)
                if callable(aclose):
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
        """Append a thread item: ``{type, text?, ops?, supersedes?, place?, options?}``."""
        _actor_override(body)
        try:
            intent, item = await intents.add_item(
                intent_id,
                type=str(body.get("type") or ""),
                text=body.get("text") or "",
                ops=body.get("ops"),
                supersedes=body.get("supersedes"),
                place=body.get("place"),
                options=body.get("options"),
            )
        except KeyError:
            return _not_found(intent_id)
        except ThreadError as exc:
            return _thread_error(exc)
        return {"intent": intent.to_dict(), "item": item.to_dict()}


    @router.patch("/{intent_id}/items/{item_id}")
    async def update_item(
        intent_id: str,
        item_id: str,
        body: dict,
        intents: IntentService = Depends(get_intent_service),
    ):
        """Change a message in place: ``{text?, state?, place?}``.

        For work in progress. A ghost drawn where a node will go moves from
        ``planned`` to ``active`` to ``done`` here, and its status line is
        rewritten rather than the thread growing an entry per step.
        """
        _actor_override(body)
        try:
            intent, item = await intents.update_item(
                intent_id,
                item_id,
                text=body.get("text"),
                state=body.get("state"),
                place=body.get("place"),
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


    @router.post("/{intent_id}/items/{item_id}/revert")
    async def revert_suggestion(
        intent_id: str,
        item_id: str,
        body: dict | None = None,
        intents: IntentService = Depends(get_intent_service),
    ):
        """Put an applied suggestion back, all-or-nothing, from its recorded undo."""
        _actor_override(body)
        try:
            intent, item, reverted = await intents.revert_suggestion(intent_id, item_id)
        except KeyError:
            return _not_found(intent_id)
        except ThreadError as exc:
            return _thread_error(exc)
        return {"intent": intent.to_dict(), "item": item.to_dict(), "reverted": reverted}


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
    return router
