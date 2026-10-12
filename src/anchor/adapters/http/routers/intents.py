"""Anchor mounts the reusable intent routes with its runtime dependencies."""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from anchor.adapters.http.deps import get_intent_service
from anchor.core.services.anchor_pending_signals import AnchorPendingSignals
from anchor.core.services.intent_service import IntentService
from intent_layer.adapters.http import create_router
from intent_layer.timing import intent_timing


def get_signals(request: Request) -> AnchorPendingSignals:
    return AnchorPendingSignals(request.app.state.bus)

router = create_router(get_intent_service, get_signals)



@router.get("/{intent_id}/timing")
async def intent_timing_route(
    intent_id: str,
    request: Request,
    intents: IntentService = Depends(get_intent_service),
):
    """How long this intent took and how many calls it cost: pickup, first
    suggestion, last agent item, resolution, and the adapter calls in its
    window from the activity log, by kind and by name."""
    intent = await intents.get(intent_id)
    if intent is None:
        return JSONResponse(status_code=404, content={"error": "not_found", "id": intent_id})
    log = getattr(request.app.state, "activity", None)
    calls = log.read(since=intent.created_at) if log is not None else []
    return {"timing": intent_timing(intent, calls)}


_events_route = next(route.endpoint for route in router.routes if route.name == "events")


async def events(request: Request, canvas: str | None = None, intents=None):
    """Retain the direct route callable used by existing SSE integrations."""
    return await _events_route(request, canvas, intents or get_intent_service(request),
                               get_signals(request))
