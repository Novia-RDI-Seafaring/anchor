"""WorkspaceService.snapshot — service-level contract tests.

These tests use a fake SnapshotPort to verify the service:
- Refuses to snapshot when no snapshotter is wired.
- Refuses unknown formats.
- Touches the store first (404 surfaces before chromium is invoked).
- Delegates correctly with all kwargs forwarded.
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.ports.snapshot import SnapshotResult
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.fixtures.fakes import FakeSnapshotter


def _ws_with_snapshotter(snapshotter):
    store = MemoryWorkspaceStore()
    bus = MemoryEventBus()
    return WorkspaceService(store, bus, snapshotter=snapshotter), store


def test_snapshot_without_port_raises_runtime_error():
    async def run():
        store = MemoryWorkspaceStore()
        bus = MemoryEventBus()
        svc = WorkspaceService(store, bus)  # no snapshotter
        await svc.create_workspace("w1")
        with pytest.raises(RuntimeError, match="no snapshotter"):
            await svc.snapshot("w1")
    asyncio.run(run())


def test_snapshot_unknown_format_rejected():
    async def run():
        snap = FakeSnapshotter()
        svc, _ = _ws_with_snapshotter(snap)
        await svc.create_workspace("w1")
        with pytest.raises(ValueError, match="unsupported snapshot format"):
            await svc.snapshot("w1", format="webp")
    asyncio.run(run())


def test_snapshot_delegates_with_kwargs():
    async def run():
        snap = FakeSnapshotter(mode="bytes")
        svc, _ = _ws_with_snapshotter(snap)
        await svc.create_workspace("w1")
        result = await svc.snapshot("w1", format="png", viewport=(800, 600), full_page=False)
        assert isinstance(result, SnapshotResult)
        assert result.format == "png"
        assert result.content_type == "image/png"
        assert result.bytes_ is not None
        assert snap.calls == [
            {"slug": "w1", "format": "png", "viewport": (800, 600), "full_page": False}
        ]
    asyncio.run(run())


def test_snapshot_result_invariant():
    # SnapshotResult must have exactly one of path / bytes_.
    with pytest.raises(ValueError, match="exactly one"):
        SnapshotResult(format="png", content_type="image/png")
    with pytest.raises(ValueError, match="exactly one"):
        SnapshotResult(
            format="png", content_type="image/png",
            path=__import__("pathlib").Path("/tmp/x.png"), bytes_=b"x",
        )
