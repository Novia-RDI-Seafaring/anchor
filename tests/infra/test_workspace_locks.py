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


def test_process_locks_survive_bundle_rebuild_for_same_data_dir(tmp_path):
    # #272: the registry is process-level and keyed by (data_dir, slug), so a
    # re-resolved project (e.g. after MCP LRU eviction) gets the same lock.
    from anchor.infra.workspace_locks import process_workspace_locks

    before = process_workspace_locks(tmp_path / "proj")
    after = process_workspace_locks(tmp_path / "proj")

    assert before is after
    assert before.lock("ws") is after.lock("ws")
    assert before.lock("ws") is not before.lock("other-ws")
    assert process_workspace_locks(tmp_path / "elsewhere") is not before


async def test_writers_serialize_across_evicted_and_rebuilt_runtimes(tmp_path):
    # Two WorkspaceService instances over one store stand in for a bundle
    # evicted mid-write and rebuilt: each resolves its locks independently,
    # and both writers must still serialize on the same per-slug lock.
    from anchor.infra.workspace_locks import process_workspace_locks

    store = _YieldBeforeAppendStore()
    data_dir = tmp_path / "proj"
    first = WorkspaceService(
        store, MemoryEventBus(), locks=process_workspace_locks(data_dir)
    )
    rebuilt = WorkspaceService(
        store, MemoryEventBus(), locks=process_workspace_locks(data_dir)
    )
    await first.create_workspace("shared")

    await asyncio.gather(
        first.add_node("shared", id="first", place="exact", x=0, y=0),
        rebuilt.add_node("shared", id="second", place="exact", x=100, y=100),
    )

    state = await first.get_state("shared")
    assert {node["id"] for node in state["nodes"]} == {"first", "second"}
    assert state["version"] == 2
