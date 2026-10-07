"""Anchor mounts the reusable intent routes with its runtime dependencies."""
from fastapi import Request

from anchor.adapters.http.deps import get_intent_service
from anchor.core.services.anchor_pending_signals import AnchorPendingSignals
from intent_layer.adapters.http import create_router


def get_signals(request: Request) -> AnchorPendingSignals:
    return AnchorPendingSignals(request.app.state.bus)

router = create_router(get_intent_service, get_signals)

_events_route = next(route.endpoint for route in router.routes if route.name == "events")


async def events(request: Request, canvas: str | None = None, intents=None):
    """Retain the direct route callable used by existing SSE integrations."""
    return await _events_route(request, canvas, intents or get_intent_service(request),
                               get_signals(request))
