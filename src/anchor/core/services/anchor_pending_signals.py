"""Bridge thread count signals to Anchor's existing canvas event bus."""
from __future__ import annotations

from collections.abc import AsyncIterator

from anchor.core.events.envelope import DomainEvent
from anchor.core.intents.intent import INTENT_PENDING_EVENT
from anchor.core.ports.event_bus import EventBus
from intent_layer.signals import PendingSignal


class AnchorPendingSignals:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(self, signal: PendingSignal) -> None:
        await self._bus.publish(DomainEvent(
            workspace_id=signal.origin_id or "_project",
            type=INTENT_PENDING_EVENT,
            ts=signal.ts,
            payload={"count": signal.count},
        ))

    async def subscribe(self) -> AsyncIterator[PendingSignal]:
        events = self._bus.subscribe(None)
        try:
            async for event in events:
                if event.type == INTENT_PENDING_EVENT:
                    yield PendingSignal(event.workspace_id, event.payload["count"], event.ts)
        finally:
            close = getattr(events, "aclose", None)
            if callable(close):
                await close()
