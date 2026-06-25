"""IntentService: enqueue / list / resolve, cross-canvas visibility within a
project, and the lightweight IntentPending count signal (issue #148)."""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.clock import FixedClock
from anchor.core.intents.intent import (
    INTENT_PENDING_EVENT,
    PENDING,
    RESOLVED,
)
from anchor.core.services.intent_service import (
    PROJECT_SIGNAL_ID,
    IntentService,
    UnknownIntentKindError,
)
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_intent_store import MemoryIntentStore


def _svc(clock=None):
    clock = clock or FixedClock(ts=100.0)
    bus = MemoryEventBus()
    return IntentService(MemoryIntentStore(), bus, now=clock.now), bus, clock


async def _collect(bus, n, *, workspace_id=None):
    """Collect the next ``n`` events off the bus (with a short deadline)."""
    out = []
    sub = bus.subscribe(workspace_id)
    it = sub.__aiter__()
    try:
        for _ in range(n):
            out.append(await asyncio.wait_for(it.__anext__(), timeout=1.0))
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            await aclose()
    return out


async def test_enqueue_list_resolve_round_trip():
    svc, _bus, clock = _svc()
    intent = await svc.enqueue(
        "drop_to_ingest",
        origin_canvas_id="canvas-a",
        payload={"slug": "pump", "node_id": "n1"},
    )
    assert intent.status == PENDING
    assert intent.created_at == 100.0

    pending = await svc.list_pending()
    assert [i.id for i in pending] == [intent.id]
    assert pending[0].payload["slug"] == "pump"

    clock.advance(5.0)
    resolved = await svc.resolve(intent.id, {"produced_slug": "pump"})
    assert resolved.status == RESOLVED
    assert resolved.resolved_at == 105.0
    assert resolved.result == {"produced_slug": "pump"}

    assert await svc.list_pending() == []
    # Still retrievable for audit.
    assert (await svc.get(intent.id)).status == RESOLVED


async def test_cross_canvas_visibility_within_project():
    """An intent raised on canvas A is visible from the project view and from
    the canvas it targets, but not from an unrelated canvas's filtered view."""
    svc, _bus, _clock = _svc()
    raised = await svc.enqueue(
        "drop_to_ingest", origin_canvas_id="canvas-a", target="canvas-b"
    )

    # Project-level view sees it.
    assert raised.id in {i.id for i in await svc.list_pending()}
    # The origin canvas sees it.
    assert raised.id in {i.id for i in await svc.list_pending(canvas="canvas-a")}
    # The target canvas sees it too (cross-canvas).
    assert raised.id in {i.id for i in await svc.list_pending(canvas="canvas-b")}
    # An unrelated canvas does not.
    assert await svc.list_pending(canvas="canvas-z") == []


async def test_next_is_oldest_first():
    clock = FixedClock(ts=1.0)
    svc, _bus, _ = _svc(clock)
    first = await svc.enqueue("drop_to_ingest", origin_canvas_id="c")
    clock.advance(1.0)
    await svc.enqueue("drop_to_ingest", origin_canvas_id="c")
    nxt = await svc.next()
    assert nxt.id == first.id


async def test_intent_pending_signal_fires_with_count_only():
    svc, bus, _clock = _svc()
    # Subscribe to the canvas the intent will be raised on.
    task = asyncio.create_task(_collect(bus, 1, workspace_id="canvas-a"))
    await asyncio.sleep(0)  # let the subscriber register
    await svc.enqueue("drop_to_ingest", origin_canvas_id="canvas-a")
    events = await task
    assert len(events) == 1
    evt = events[0]
    assert evt.type == INTENT_PENDING_EVENT
    assert evt.payload == {"count": 1}
    # The signal carries the count only -- never the intent payload.
    assert "slug" not in evt.payload
    assert "payload" not in evt.payload


async def test_resolve_signal_decrements_count():
    svc, bus, _clock = _svc()
    a = await svc.enqueue("drop_to_ingest", origin_canvas_id="c")
    await svc.enqueue("drop_to_ingest", origin_canvas_id="c")
    assert await svc.pending_count() == 2

    task = asyncio.create_task(_collect(bus, 1, workspace_id="c"))
    await asyncio.sleep(0)
    await svc.resolve(a.id)
    events = await task
    assert events[0].payload == {"count": 1}


async def test_project_level_intent_uses_sentinel_workspace_id():
    svc, bus, _clock = _svc()
    task = asyncio.create_task(_collect(bus, 1, workspace_id=PROJECT_SIGNAL_ID))
    await asyncio.sleep(0)
    await svc.enqueue("drop_to_ingest")  # no origin canvas
    events = await task
    assert events[0].workspace_id == PROJECT_SIGNAL_ID


async def test_unknown_kind_rejected():
    svc, _bus, _clock = _svc()
    with pytest.raises(UnknownIntentKindError):
        await svc.enqueue("teleport_document")
    assert await svc.list_pending() == []


async def test_supported_reference_kinds_persist_without_authoring():
    """make_reference / attach_to_fact are recognized kinds the queue STORES
    (the generic mechanism), even though their authoring UX is #147."""
    svc, _bus, _clock = _svc()
    a = await svc.enqueue("make_reference", origin_canvas_id="c", payload={"x": 1})
    b = await svc.enqueue("attach_to_fact", origin_canvas_id="c", payload={"y": 2})
    kinds = {i.kind for i in await svc.list_pending()}
    assert kinds == {"make_reference", "attach_to_fact"}
    assert (await svc.get(a.id)).payload == {"x": 1}
    assert (await svc.get(b.id)).payload == {"y": 2}


async def test_resolve_unknown_id_raises():
    svc, _bus, _clock = _svc()
    with pytest.raises(KeyError):
        await svc.resolve("nope")
