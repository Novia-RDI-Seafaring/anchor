"""An intent whose every target was deleted is stale (#498 follow-up).

It stays pending, so whoever asked can still see it and remove it, but the
agent's inbox leaves it out: there is nothing left to look at.
"""
from __future__ import annotations

from anchor.core.clock import FixedClock
from anchor.core.events.actor import Actor, actor_scope
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_intent_store import MemoryIntentStore
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore

HUMAN = Actor(kind="human", id="u1", label="reader")


async def _setup(nodes=("n1", "n2")):
    bus = MemoryEventBus()
    clock = FixedClock(ts=100.0)
    ws = WorkspaceService(MemoryWorkspaceStore(), bus, clock=clock)
    svc = IntentService(MemoryIntentStore(), bus, now=clock.now, workspace=ws)
    await ws.create_workspace("cv")
    for n in nodes:
        await ws.add_node("cv", id=n, label=n.upper(), x=0, y=0)
    with actor_scope(HUMAN):
        intent = await svc.enqueue(
            "user_request", origin_canvas_id="cv", payload={"text": "specs"},
            targets=[{"workspace_id": "cv", "node_id": n} for n in nodes],
        )
    return svc, ws, intent


async def test_an_intent_is_live_while_any_target_remains():
    svc, ws, intent = await _setup()
    await ws.remove_node("cv", "n1")
    assert [i.id for i in await svc.list_pending()] == [intent.id]
    assert (await svc.list_pending())[0].stale is None


async def test_an_intent_whose_targets_are_all_gone_leaves_the_inbox():
    svc, ws, intent = await _setup()
    await ws.remove_node("cv", "n1")
    await ws.remove_node("cv", "n2")
    assert await svc.list_pending() == []
    assert await svc.next() is None
    assert await svc.pending_count() == 0
    stale = await svc.list_pending(include_stale=True)
    assert [i.id for i in stale] == [intent.id]
    assert stale[0].stale == "all 2 elements it points at were deleted"
    assert stale[0].to_dict()["stale"] == stale[0].stale
    # Still listed for the reader, with the reason, and still removable.
    everything = await svc.list_all()
    assert everything[0].stale is not None
    resolved = await svc.resolve(intent.id, {"dismissed": True})
    assert resolved.status == "resolved"
    assert "stale" not in resolved.to_dict()


async def test_stale_is_worked_out_not_stored():
    svc, ws, intent = await _setup(nodes=("n1",))
    await ws.remove_node("cv", "n1")
    stored = await svc.get(intent.id)
    assert stored is not None and stored.stale is None
    assert "stale" not in stored.to_dict()


async def test_an_intent_with_no_targets_is_never_stale():
    bus = MemoryEventBus()
    ws = WorkspaceService(MemoryWorkspaceStore(), bus, clock=FixedClock(ts=1.0))
    svc = IntentService(MemoryIntentStore(), bus, workspace=ws)
    await ws.create_workspace("cv")
    with actor_scope(HUMAN):
        intent = await svc.enqueue("user_request", origin_canvas_id="cv", payload={"text": "PX-10"})
    assert [i.id for i in await svc.list_pending()] == [intent.id]


async def test_a_deleted_canvas_makes_its_intents_stale():
    svc, ws, intent = await _setup(nodes=("n1",))
    await ws.delete_workspace("cv")
    assert await svc.list_pending() == []
    assert (await svc.list_pending(include_stale=True))[0].stale == "the element it points at was deleted"
