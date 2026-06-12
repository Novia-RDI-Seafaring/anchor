from __future__ import annotations

import asyncio

from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.event_tailer import EventTailer
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore


async def _next_event(bus: MemoryEventBus, slug: str):
    subscription = bus.subscribe(slug)
    events = subscription.__aiter__()
    try:
        return await asyncio.wait_for(anext(events), timeout=1)
    finally:
        await events.aclose()


def test_event_tailer_publishes_events_written_by_another_service(tmp_path):
    async def run():
        root = tmp_path / "canvases"
        serve_bus = MemoryEventBus()
        external = WorkspaceService(FsWorkspaceStore(root), MemoryEventBus())

        await external.create_workspace("w1")
        tailer = EventTailer(
            slug="w1",
            events_path=root / "w1" / "events.jsonl",
            bus=serve_bus,
            poll_interval=0.01,
        )

        listener = asyncio.create_task(_next_event(serve_bus, "w1"))
        await asyncio.sleep(0)
        tailer.start()
        try:
            await external.add_node("w1", id="external-node", label="External")
            event = await listener
        finally:
            await tailer.stop()

        assert event.type == "NodeAdded"
        assert event.payload["id"] == "external-node"

    asyncio.run(run())


def test_event_tailer_replays_events_after_snapshot_version(tmp_path):
    async def run():
        root = tmp_path / "canvases"
        serve_bus = MemoryEventBus()
        external = WorkspaceService(FsWorkspaceStore(root), MemoryEventBus())

        await external.create_workspace("w1")
        await external.add_node("w1", id="snapshot-node", label="Snapshot")
        snapshot_version = 1

        listener = asyncio.create_task(_next_event(serve_bus, "w1"))
        await asyncio.sleep(0)
        await external.add_node("w1", id="late-node", label="Late")

        tailer = EventTailer(
            slug="w1",
            events_path=root / "w1" / "events.jsonl",
            bus=serve_bus,
            poll_interval=0.01,
        )
        tailer.start(replay_after_version=snapshot_version)
        try:
            event = await listener
        finally:
            await tailer.stop()

        assert event.type == "NodeAdded"
        assert event.version == 2
        assert event.payload["id"] == "late-node"

    asyncio.run(run())
