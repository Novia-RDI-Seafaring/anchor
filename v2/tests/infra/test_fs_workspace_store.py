"""FsWorkspaceStore — atomic snapshot writes + append-only events.jsonl."""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.events.canvas import NodeAdded, NodeMoved
from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.workspace import Workspace
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore


@pytest.fixture
def root(tmp_path):
    return tmp_path / "canvases"


def _envelope(slug: str, evt) -> DomainEvent:
    return DomainEvent(workspace_id=slug, type=evt.type, payload=evt.model_dump())


def test_create_and_load_empty_workspace(root):
    async def run():
        store = FsWorkspaceStore(root)
        meta = await store.create("w1", title="One")
        ws = await store.load("w1")
        assert meta.slug == "w1"
        assert ws.slug == "w1"
        assert ws.nodes == {} and ws.edges == {}

    asyncio.run(run())


def test_append_event_assigns_monotonic_versions(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("w1")
        v1 = await store.append_event("w1", _envelope("w1", NodeAdded(id="a")))
        v2 = await store.append_event("w1", _envelope("w1", NodeMoved(id="a", x=10, y=20)))
        assert v1 == 1 and v2 == 2

    asyncio.run(run())


def test_append_event_idempotent_on_id(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("w1")
        env = _envelope("w1", NodeAdded(id="x"))
        v1 = await store.append_event("w1", env)
        v2 = await store.append_event("w1", env)
        assert v1 == v2

    asyncio.run(run())


def test_snapshot_roundtrips(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("w1")
        ws = Workspace(slug="w1", version=42, metadata={"foo": "bar"})
        await store.snapshot("w1", ws)
        loaded = await store.load("w1")
        assert loaded.version == 42
        assert loaded.metadata == {"foo": "bar"}

    asyncio.run(run())


def test_load_replays_events_after_snapshot(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("w1")
        await store.append_event("w1", _envelope("w1", NodeAdded(id="a", label="A")))
        await store.append_event("w1", _envelope("w1", NodeMoved(id="a", x=99, y=88)))
        ws = await store.load("w1")
        assert ws.version == 2
        assert ws.nodes["a"].x == 99

    asyncio.run(run())


def test_list_workspaces(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("alpha")
        await store.create("beta")
        names = sorted(m.slug for m in await store.list_workspaces())
        assert names == ["alpha", "beta"]

    asyncio.run(run())


def test_events_jsonl_is_append_only(root):
    async def run():
        store = FsWorkspaceStore(root)
        await store.create("w1")
        for i in range(5):
            await store.append_event("w1", _envelope("w1", NodeAdded(id=f"c{i}")))
        events_path = root / "w1" / "events.jsonl"
        lines = [line for line in events_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 5
        records = [json.loads(line) for line in lines]
        assert [r["version"] for r in records] == [1, 2, 3, 4, 5]

    asyncio.run(run())
