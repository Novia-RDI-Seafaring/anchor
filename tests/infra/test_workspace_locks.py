from __future__ import annotations

import asyncio

from anchor.core.events.envelope import DomainEvent
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_workspace_store import MemoryWorkspaceStore
from anchor.infra.workspace_locks import InProcessWorkspaceLocks


class _YieldBeforeAppendStore(MemoryWorkspaceStore):
    async def append_event(self, slug: str, event: DomainEvent) -> int:
        await asyncio.sleep(0)
        return await super().append_event(slug, event)


async def test_concurrent_mutations_preserve_both_updates() -> None:
    store = _YieldBeforeAppendStore()
    service = WorkspaceService(
        store,
        MemoryEventBus(),
        locks=InProcessWorkspaceLocks(),
    )
    await service.create_workspace("shared")

    await asyncio.gather(
        service.add_node("shared", id="first", place="exact", x=0, y=0),
        service.add_node("shared", id="second", place="exact", x=100, y=100),
    )

    state = await service.get_state("shared")
    assert {node["id"] for node in state["nodes"]} == {"first", "second"}
    assert state["version"] == 2
