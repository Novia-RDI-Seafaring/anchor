"""Transport, persistence and SSE share one authoritative claim mutation."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from anchor.adapters.http.routers.sse import events
from anchor.adapters.project_runtime import bind_workspace_sources
from anchor.core.events.canvas import CanvasSnapshot
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.reducer import apply
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.adapters.test_spec_source_operations import CanvasOperations
from tests.adapters.test_value_provenance_parity import _input, _regions
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_edit_and_revalidate_with_restart(transport, tmp_path):
    ops = CanvasOperations(transport, AnchorConfig(data_dir=tmp_path), workspace="g7")
    asyncio.run(ops.runtime.workspace.create_workspace("g7"))
    asyncio.run(ops.runtime.doc_store.write_gold_region_file("doc", 1, _regions()))
    node = ops.call("add", _input("exact"))
    original = ops.read(node)
    assert original["rows"][0]["evidence"]["status"] == "verified"
    edited = deepcopy(original)
    edited["rows"][0]["value"] = "999999"
    ops.call("update", edited, node)
    stale = ops.read(node)
    assert stale["rows"][0]["evidence"]["status"] == "stale"
    assert stale["rows"][0]["source_ref"] == original["rows"][0]["source_ref"]
    edited["rows"][0]["revalidate_evidence"] = True
    ops.call("update", edited, node)
    assert ops.read(node) == stale
    original["rows"][0]["revalidate_evidence"] = True
    ops.call("update", original, node)
    row = ops.read(node)["rows"][0]
    assert row["evidence"]["status"] == "verified"
    assert row["source_ref"]["coord_origin"] == "top-left"


def test_two_sse_clients_receive_atomic_claim_and_status_and_snapshot_replay():
    async def run():
        bus = MemoryEventBus()
        ws = WorkspaceService(MemoryWorkspaceStore(), bus)
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions())
        bind_workspace_sources(ws, docs)
        await ws.create_workspace("g7")
        initial, _ = await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        async def connected():
            return False
        request.is_disconnected = connected
        streams = [(await events("g7", request, bus, ws)).body_iterator for _ in range(2)]
        for stream in streams:
            snapshot = await anext(stream)
            assert json.loads(snapshot["data"])["nodes"][0]["data"]["rows"][0]["evidence"]["status"] == "verified"
        edited = deepcopy(initial.nodes["spec"].data)
        edited["rows"][0]["value"] = "999999"
        changed, _ = await ws.update_node("g7", "spec", {"data": edited})
        for stream in streams:
            patch = await asyncio.wait_for(anext(stream), timeout=2)
            row = json.loads(patch["data"])["payload"]["fields"]["data"]["rows"][0]
            assert row["value"] == "999999" and row["evidence"]["status"] == "stale"
            await stream.aclose()
        # There is no public canvas undo/redo command. The actual snapshot
        # reducer restores the exact pair, with no text-based revalidation.
        def restore(target, saved):
            return apply(target, CanvasSnapshot(nodes=[n.model_dump() for n in saved.nodes.values()], edges=[]))
        undone = restore(changed, initial)
        redone = restore(undone, changed)
        assert undone.nodes["spec"].data == initial.nodes["spec"].data
        assert redone.nodes["spec"].data == changed.nodes["spec"].data
        assert initial.nodes["spec"].data["rows"][0]["evidence"]["status"] == "verified"
    asyncio.run(run())


def test_replacement_cannot_reuse_previous_generation_verification(tmp_path):
    ops = CanvasOperations("http", AnchorConfig(data_dir=tmp_path), workspace="g7")
    async def seed():
        await ops.runtime.workspace.create_workspace("g7")
        await pipeline(ops.runtime.doc_store, [["A"]]).ingest_pdf(b"A", "doc.pdf")
        await ops.runtime.doc_store.write_gold_region_file("doc", 1, _regions())
    asyncio.run(seed())
    node = ops.call("add", _input("exact"))
    before = ops.read(node)
    async def replace():
        await pipeline(ops.runtime.doc_store, [["B"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        await ops.runtime.doc_store.write_gold_region_file("doc", 1, _regions())
    asyncio.run(replace())
    ops.call("update", before, node)
    assert ops.read(node)["rows"][0]["evidence"]["status"] == "stale"
    before["rows"][0]["revalidate_evidence"] = True
    ops.call("update", before, node)
    after = ops.read(node)["rows"][0]
    assert after["evidence"]["status"] == "verified"
    assert after["evidence"]["validation"]["generation_id"] != before["rows"][0]["evidence"]["validation"]["generation_id"]
