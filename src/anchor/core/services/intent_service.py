"""IntentService — enqueue / list / resolve agent intents (#148).

This is the eventing layer over the durable project-level intent store. It owns
the two halves of the push-notify / pull-payload transport:

- **pull**: ``list_pending`` / ``next`` / ``resolve`` read and mutate the
  durable store, so a harness fetches the full payload on its own cadence.
- **push (signal only)**: after any change to the pending set it publishes a
  lightweight ``IntentPending {count}`` event on the bus. Subscribers learn
  *that* work is waiting without paying for the payload on every turn.

Pure core: it depends on the store port, the event-bus port, and a clock, never
on a concrete adapter. The ``workspace_id`` carried on the bus event is set to
the originating canvas (or a project-level sentinel) so a per-canvas SSE
subscriber sees the signal.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anchor.core.events.envelope import DomainEvent
from anchor.core.intents.intent import (
    INTENT_KINDS,
    INTENT_PENDING_EVENT,
    PENDING,
    RESOLVED,
    Intent,
    IntentKind,
)
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.intent_store import IntentStore

#: Bus ``workspace_id`` used for the count signal when an intent has no
#: originating canvas. A project-level subscriber (or the global firehose)
#: still receives it; a per-canvas SSE stream filters on the canvas id.
PROJECT_SIGNAL_ID = "_project"


class UnknownIntentKindError(ValueError):
    """Raised when an enqueue uses a kind the queue does not recognize."""


class IntentService:
    def __init__(
        self,
        store: IntentStore,
        bus: EventBus,
        *,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._now = now

    def _ts(self) -> float:
        return self._now() if callable(self._now) else 0.0

    async def enqueue(
        self,
        kind: IntentKind | str,
        *,
        origin_canvas_id: str | None = None,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Intent:
        """Add a pending intent and fire the ``IntentPending`` count signal.

        Raises :class:`UnknownIntentKindError` for an unrecognized kind so a
        caller never silently enqueues something no handler understands.
        """
        if kind not in INTENT_KINDS:
            raise UnknownIntentKindError(
                f"unknown intent kind {kind!r}; expected one of {sorted(INTENT_KINDS)}"
            )
        intent = Intent(
            kind=kind,  # type: ignore[arg-type]
            origin_canvas_id=origin_canvas_id,
            target=target,
            payload=dict(payload or {}),
            status=PENDING,
            created_at=self._ts(),
        )
        stored = await self._store.add(intent)
        await self._signal_pending(origin_canvas_id)
        return stored

    async def list_pending(self, *, canvas: str | None = None) -> list[Intent]:
        """Pending intents for this project, oldest first.

        ``canvas`` filters to a per-canvas view (matching ``origin_canvas_id``
        or ``target``); omit it for the whole project. A cross-canvas intent is
        therefore visible from the canvas that raised it and from the canvas it
        targets.
        """
        items = [i for i in await self._store.list() if i.status == PENDING]
        if canvas is not None:
            items = [
                i
                for i in items
                if i.origin_canvas_id == canvas or i.target == canvas
            ]
        items.sort(key=lambda i: (i.created_at, i.id))
        return items

    async def list_all(self, *, canvas: str | None = None) -> list[Intent]:
        """Every intent (pending + resolved), newest first. For audit/UI."""
        items = await self._store.list()
        if canvas is not None:
            items = [
                i
                for i in items
                if i.origin_canvas_id == canvas or i.target == canvas
            ]
        items.sort(key=lambda i: (i.created_at, i.id), reverse=True)
        return items

    async def next(self, *, canvas: str | None = None) -> Intent | None:
        """The oldest pending intent (optionally for one canvas), or ``None``.

        A peek, not a claim: it does not mark the intent in-flight. The handler
        calls :meth:`resolve` when done, which is the only state transition.
        """
        pending = await self.list_pending(canvas=canvas)
        return pending[0] if pending else None

    async def get(self, intent_id: str) -> Intent | None:
        return await self._store.get(intent_id)

    async def resolve(
        self, intent_id: str, result: dict[str, Any] | None = None
    ) -> Intent:
        """Mark an intent resolved and re-fire the count signal.

        Returns the updated intent. Raises ``KeyError`` for an unknown id.
        Re-resolving an already-resolved intent is a no-op beyond refreshing
        ``result`` (kept idempotent so a retrying agent is safe).
        """
        intent = await self._store.get(intent_id)
        if intent is None:
            raise KeyError(intent_id)
        intent.status = RESOLVED
        intent.resolved_at = self._ts()
        if result is not None:
            intent.result = dict(result)
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent

    async def pending_count(self) -> int:
        return len(await self.list_pending())

    async def _signal_pending(self, origin_canvas_id: str | None) -> None:
        """Publish ``IntentPending {count}`` — count only, never the payload."""
        count = await self.pending_count()
        await self._bus.publish(
            DomainEvent(
                workspace_id=origin_canvas_id or PROJECT_SIGNAL_ID,
                type=INTENT_PENDING_EVENT,
                ts=self._ts(),
                payload={"count": count},
            )
        )
