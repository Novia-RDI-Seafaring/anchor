"""Server-Sent Events for live workspace updates, plus canvas presence.

The event stream doubles as the presence announcement: each SSE
connection registers itself with the app's :class:`PresenceTracker`
(actor kind + label from query params, default ``human``/"browser"), and
every roster change is pushed to all subscribers as a ``presence`` event
carrying the full current roster. Presence is per-serve-process,
in-memory state — see ``anchor.infra.presence``.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from anchor.adapters.http.deps import get_event_bus, get_workspace_service
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["sse"])

_ACTOR_KINDS = ("human", "agent", "system")


async def _event_stream(
    request: Request,
    slug: str,
    actor_kind: str,
    actor_label: str,
    bus: EventBus,
    svc: WorkspaceService,
):
    """The SSE payload sequence: snapshot, then patches + presence rosters.

    Module-level (rather than a closure) so tests can drive it directly —
    an infinite SSE response can't be cleanly consumed through TestClient.
    """
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

    # Join the presence roster. Everyone else learns via the broadcast
    # queued by connect(); this stream sends the joiner its own initial
    # roster (with `you` naming its entry) right after the snapshot.
    tracker = getattr(request.app.state, "presence", None)
    client_id: str | None = None
    presence_queue: asyncio.Queue | None = None
    next_presence: asyncio.Task | None = None
    if tracker is not None:
        client_id, presence_queue = tracker.connect(
            slug, kind=actor_kind, label=actor_label
        )
        next_presence = asyncio.create_task(presence_queue.get())

    try:
        yield {"event": "snapshot", "data": _json(snapshot)}
        if tracker is not None and client_id is not None:
            initial = tracker.payload(slug) | {"you": client_id}
            yield {"event": "presence", "data": _json(initial)}
        while True:
            if await request.is_disconnected():
                return
            pending = {next_event}
            if next_presence is not None:
                pending.add(next_presence)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if next_presence is not None and next_presence in done:
                yield {"event": "presence", "data": _json(next_presence.result())}
                next_presence = asyncio.create_task(presence_queue.get())
            if next_event in done:
                try:
                    evt = next_event.result()
                except StopAsyncIteration:
                    return
                yield {"event": "patch", "data": evt.model_dump_json()}
                next_event = asyncio.create_task(anext(events))
    finally:
        if tracker is not None and client_id is not None:
            tracker.disconnect(slug, client_id)
        for task in (next_event, next_presence):
            if task is None:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                _ = await task
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            await aclose()


@router.get("/{slug}/events")
async def events(
    slug: str,
    request: Request,
    actor_kind: str = Query(
        "human",
        description="Who this viewer is: human, agent, or system (presence roster).",
    ),
    actor_label: str = Query(
        "browser",
        description="Display label for this viewer in the presence roster.",
    ),
    bus: EventBus = Depends(get_event_bus),
    svc: WorkspaceService = Depends(get_workspace_service),
):
    if actor_kind not in _ACTOR_KINDS:
        raise HTTPException(
            400, f"unknown actor_kind {actor_kind!r} (use one of {', '.join(_ACTOR_KINDS)})"
        )

    # ping=15 keeps the EventSource warm during idle: without it, Chromium/
    # macOS can silently drop the connection on tab background or system
    # sleep, and the browser doesn't always fire `onerror` so the client
    # reconnect path doesn't trigger. With 15-second comment pings the
    # connection stays alive and idle browsers stay subscribed.
    return EventSourceResponse(
        _event_stream(request, slug, actor_kind, actor_label, bus, svc), ping=15
    )


@router.get("/{slug}/presence")
async def presence(slug: str, request: Request):
    """Who is on this canvas right now (same roster the SSE stream pushes).

    For non-SSE consumers: the MCP `canvas_presence` tool and
    `anchor canvas presence` read this. Per-serve-process, in-memory; an
    unknown slug simply has an empty roster (workspaces auto-create on
    first touch, so there is no 404 to give).
    """
    tracker = getattr(request.app.state, "presence", None)
    present = tracker.roster(slug) if tracker is not None else []
    return {"workspace": slug, "present": present}


def _json(obj) -> str:
    return json.dumps(obj)
