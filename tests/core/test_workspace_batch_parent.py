"""Batch reparenting validates references before touching the real store."""
from __future__ import annotations

from copy import deepcopy

import pytest

from anchor.core.events.actor import Actor
from anchor.core.services.workspace_batch import BatchApplyError
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

AGENT = Actor(kind="agent", label="test")
HUMAN = Actor(kind="human", label="reviewer")


async def _workspace(tmp_path):
    store = FsWorkspaceStore(tmp_path / "canvases")
    ws = WorkspaceService(store, MemoryEventBus())
    await ws.create_workspace("cv")
    await ws.add_node("cv", id="parent", label="Parent", x=0, y=0)
    await ws.add_node("cv", id="child", label="Before", parent="parent", x=0, y=0)
    return ws, store


async def _apply(ws, ops):
    return await ws.apply_batch("cv", ops, actor=AGENT, approver=HUMAN, causation_id="test")


@pytest.mark.parametrize("remove_parent", [False, True])
async def test_batch_updated_missing_parent_refuses_every_op_without_persisting(tmp_path, remove_parent):
    ws, store = await _workspace(tmp_path)
    before = await store.load("cv")
    files = [store.root / "cv" / filename for filename in ("state.json", "events.jsonl")]
    before_bytes = [path.read_bytes() for path in files]
    before_events = await store.read_events("cv")
    ops = [{"type": "NodeUpdated", "payload": {"id": "child", "fields": {"label": "Must not persist"}}}]
    if remove_parent:
        ops.append({"type": "NodeRemoved", "payload": {"id": "parent"}})
    parent = "parent" if remove_parent else "missing"
    ops.append({"type": "NodeUpdated", "payload": {"id": "child", "fields": {"parent": parent}}})
    original = deepcopy(ops)

    with pytest.raises(BatchApplyError) as exc:
        await _apply(ws, ops)

    assert exc.value.failing_index == len(ops) - 1
    assert exc.value.stale is True
    assert exc.value.reason == f"parent {parent!r} does not exist"
    assert await store.load("cv") == before
    assert await store.read_events("cv") == before_events
    assert [path.read_bytes() for path in files] == before_bytes
    assert ops == original


async def test_batch_updated_parent_resolves_a_parent_added_earlier(tmp_path):
    ws, store = await _workspace(tmp_path)
    ops = [
        {"type": "NodeAdded", "payload": {"id": "new-parent", "label": "New parent"}},
        {"type": "NodeUpdated", "payload": {"id": "child", "fields": {"parent": "new-parent"}}},
    ]
    original = deepcopy(ops)
    state, events, ids = await _apply(ws, ops)
    assert state.nodes["child"].parent == ids["new-parent"]
    assert events[-1].payload["fields"]["parent"] == ids["new-parent"]
    assert (await store.load("cv")).nodes["child"].parent == ids["new-parent"]
    assert ops == original


async def test_batch_updated_existing_parent_and_null_clear_remain_valid(tmp_path):
    ws, store = await _workspace(tmp_path)
    await ws.add_node("cv", id="other-parent", label="Other parent", x=0, y=0)
    state, _, _ = await _apply(ws, [
        {"type": "NodeUpdated", "payload": {"id": "child", "fields": {"parent": "other-parent"}}},
    ])
    assert state.nodes["child"].parent == "other-parent"
    cleared, events, _ = await _apply(ws, [
        {"type": "NodeUpdated", "payload": {"id": "child", "fields": {"parent": None}}},
    ])
    assert cleared.nodes["child"].parent is None
    assert events[-1].payload["fields"]["parent"] is None
    assert (await store.load("cv")).nodes["child"].parent is None
