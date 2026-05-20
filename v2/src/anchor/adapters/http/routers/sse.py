"""Server-Sent Events for live workspace updates."""
from __future__ import annotations

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
    # Make sure any writes from other processes (CLI, MCP-stdio, ...) get
    # bridged onto our in-process bus while this client is subscribed.
    registry = getattr(request.app.state, "tailer_registry", None)
    if registry is not None:
        await registry.ensure(slug)

    async def stream():
        # Initial snapshot
        snapshot = await svc.get_state(slug)
        yield {"event": "snapshot", "data": _json(snapshot)}
        async for evt in bus.subscribe(slug):
            if await request.is_disconnected():
                return
            yield {"event": "patch", "data": evt.model_dump_json()}

    return EventSourceResponse(stream())


def _json(obj) -> str:
    import json
    return json.dumps(obj)
