"""Server-Sent Events for live workspace updates."""
from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import get_event_bus, get_workspace_service
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["sse"])


@router.get("/{slug}/events")
async def events(
    slug: str,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    svc: WorkspaceService = Depends(get_workspace_service),
):
    async def stream():
        # Register the in-process bus subscriber before starting the file tailer.
        # Otherwise a CLI/MCP write can be tailed and published before this SSE
        # stream is listening, which means the browser only sees it after reload.
        subscription = bus.subscribe(slug)
        events = subscription.__aiter__()
        next_event = asyncio.create_task(anext(events))
        await asyncio.sleep(0)

        snapshot = await svc.get_state(slug)
        registry = getattr(request.app.state, "tailer_registry", None)
        if registry is not None:
            await registry.ensure(
                slug,
                replay_after_version=int(snapshot.get("version", 0)),
            )

        try:
            yield {"event": "snapshot", "data": _json(snapshot)}
            while True:
                if await request.is_disconnected():
                    return
                try:
                    evt = await next_event
                except StopAsyncIteration:
                    return
                yield {"event": "patch", "data": evt.model_dump_json()}
                next_event = asyncio.create_task(anext(events))
        finally:
            next_event.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                _ = await next_event
            aclose = getattr(events, "aclose", None)
            if aclose is not None:
                await aclose()

    # ping=15 keeps the EventSource warm during idle: without it, Chromium/
    # macOS can silently drop the connection on tab background or system
    # sleep, and the browser doesn't always fire `onerror` so the client
    # reconnect path doesn't trigger. With 15-second comment pings the
    # connection stays alive and idle browsers stay subscribed.
    return EventSourceResponse(stream(), ping=15)


def _json(obj) -> str:
    import json
    return json.dumps(obj)
