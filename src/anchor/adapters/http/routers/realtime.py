"""Multiplex the browser's canvas and project notifications on one SSE stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import (
    get_doc_store,
    get_event_bus,
    get_intent_service,
    get_workspace_service,
)
from anchor.adapters.http.routers.ingests import _POLL_SECONDS, _registry
from anchor.adapters.http.routers.sse import _ACTOR_KINDS
from anchor.core.ids import validate_workspace_slug
from anchor.core.intents.intent import INTENT_PENDING_EVENT
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore

router = APIRouter(prefix="/api", tags=["sse"])


async def _event_stream(
    request: Request,
    canvas: str | None,
    actor_kind: str,
    actor_label: str,
    bus: EventBus,
    workspace: WorkspaceService,
    intents: IntentService | None,
    store: DocStore,
):
    # Subscribe before taking snapshots or starting a tailer, so writes made
    # during either operation are queued for this connection.
    events = bus.subscribe(None).__aiter__()
    next_event = asyncio.create_task(anext(events))
    next_presence: asyncio.Task | None = None
    next_poll: asyncio.Task | None = None
    tracker = getattr(request.app.state, "presence", None)
    client_id: str | None = None
    presence_queue: asyncio.Queue | None = None
    registry = _registry(store)

    try:
        await asyncio.sleep(0)
        if canvas is not None:
            snapshot = await workspace.get_state(canvas)
            tailers = getattr(request.app.state, "tailer_registry", None)
            if tailers is not None:
                await tailers.ensure(canvas, replay_after_version=int(snapshot.get("version", 0)))
            if tracker is not None:
                client_id, presence_queue = tracker.connect(
                    canvas, kind=actor_kind, label=actor_label
                )
                next_presence = asyncio.create_task(presence_queue.get())
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            if client_id is not None:
                yield {
                    "event": "presence",
                    "data": json.dumps(tracker.payload(canvas) | {"you": client_id}),
                }

        count = len(await intents.list_pending()) if intents is not None else 0
        yield {"event": "intent_pending", "data": json.dumps({"count": count})}
        last_ingests = json.dumps([a.to_dict() for a in await registry.snapshot()])
        yield {"event": "ingests", "data": last_ingests}
        next_poll = asyncio.create_task(asyncio.sleep(_POLL_SECONDS))

        while not await request.is_disconnected():
            pending = {next_event, next_poll}
            if next_presence is not None:
                pending.add(next_presence)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if next_event in done:
                try:
                    event = next_event.result()
                except StopAsyncIteration:
                    return
                next_event = asyncio.create_task(anext(events))
                if event.type == INTENT_PENDING_EVENT:
                    count = len(await intents.list_pending()) if intents is not None else 0
                    yield {"event": "intent_pending", "data": json.dumps({"count": count})}
                elif canvas is not None and event.workspace_id == canvas:
                    yield {"event": "patch", "data": event.model_dump_json()}
            if next_presence is not None and next_presence in done:
                payload = next_presence.result()
                next_presence = asyncio.create_task(presence_queue.get())
                yield {"event": "presence", "data": json.dumps(payload)}
            if next_poll in done:
                current = json.dumps([a.to_dict() for a in await registry.snapshot()])
                next_poll = asyncio.create_task(asyncio.sleep(_POLL_SECONDS))
                if current != last_ingests:
                    last_ingests = current
                    yield {"event": "ingests", "data": current}
    finally:
        if client_id is not None:
            tracker.disconnect(canvas, client_id)
        tasks = [task for task in (next_event, next_presence, next_poll) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        close = getattr(events, "aclose", None)
        if callable(close):
            await close()


@router.get("/events")
async def events(
    request: Request,
    canvas: str | None = Query(None, description="Canvas to watch, alongside project notifications."),
    actor_kind: str = Query("human", description="Presence actor: human, agent, or system."),
    actor_label: str = Query("browser", description="Presence display label."),
    bus: EventBus = Depends(get_event_bus),
    workspace: WorkspaceService = Depends(get_workspace_service),
    intents: IntentService = Depends(get_intent_service),
    store: DocStore = Depends(get_doc_store),
):
    if canvas is not None:
        validate_workspace_slug(canvas)
    if actor_kind not in _ACTOR_KINDS:
        raise HTTPException(400, "unknown actor_kind (use human, agent, or system)")
    return EventSourceResponse(
        _event_stream(request, canvas, actor_kind, actor_label, bus, workspace, intents, store),
        ping=15,
    )
