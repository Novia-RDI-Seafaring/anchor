"""MemoryEventBus — pub/sub semantics."""
from __future__ import annotations

import asyncio

from anchor.core.events.envelope import DomainEvent
from anchor.infra.bus.memory_bus import MemoryEventBus


def _evt(workspace_id: str, type_: str, payload=None) -> DomainEvent:
    return DomainEvent(workspace_id=workspace_id, type=type_, payload=payload or {})


def test_subscriber_receives_only_their_workspace():
    async def run():
        bus = MemoryEventBus()
        seen_w1 = []
        seen_all = []

        async def sub_w1():
            async for e in bus.subscribe("w1"):
                seen_w1.append(e)
                if len(seen_w1) >= 2:
                    return

        async def sub_all():
            async for e in bus.subscribe(None):
                seen_all.append(e)
                if len(seen_all) >= 3:
                    return

        t1 = asyncio.create_task(sub_w1())
        t2 = asyncio.create_task(sub_all())
        await asyncio.sleep(0)
        await bus.publish(_evt("w1", "X"))
        await bus.publish(_evt("w2", "Y"))
        await bus.publish(_evt("w1", "Z"))
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
        assert {e.type for e in seen_w1} == {"X", "Z"}
        assert len(seen_all) == 3

    asyncio.run(run())


def test_close_terminates_subscribers():
    async def run():
        bus = MemoryEventBus()

        async def sub():
            count = 0
            async for _ in bus.subscribe(None):
                count += 1
            return count

        task = asyncio.create_task(sub())
        await asyncio.sleep(0)
        await bus.close()
        result = await asyncio.wait_for(task, timeout=2.0)
        assert result == 0

    asyncio.run(run())
