"""Producer preparation through the shared workspace mutation seam."""
import asyncio
import hashlib
from copy import deepcopy

import pytest

from anchor.adapters.project_runtime import bind_workspace_sources
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.adapters.test_value_provenance_parity import _input, _regions
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline


def test_no_store_preserves_create_and_update_and_binding_cannot_retarget():
    async def run():
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        bind_workspace_sources(ws, None)
        await ws.create_workspace("g6")
        first, _ = await ws.add_node("g6", id="spec", node_type="spec", data=_input("exact"))
        second, _ = await ws.update_node("g6", "spec", {"data": _input("exact")})
        assert first.nodes["spec"].data == second.nodes["spec"].data == _input("exact")
        store = MemoryDocStore()
        bind_workspace_sources(ws, store)
        bind_workspace_sources(ws, store)
        with pytest.raises(ValueError, match="already bound"):
            bind_workspace_sources(ws, MemoryDocStore())
    asyncio.run(run())


def test_historical_unstamped_geometry_is_not_promoted_by_the_bound_preparer():
    async def run():
        backing = MemoryWorkspaceStore()
        store = MemoryDocStore()
        await store.write_gold_region_file("doc", 1, _regions())
        ws = WorkspaceService(backing, MemoryEventBus())
        await ws.create_workspace("g6")
        await ws.add_node("g6", id="spec", node_type="spec", data=_input("exact"))
        legacy = await backing.load("g6")
        legacy.nodes["spec"].data["rows"][0]["source_ref"].pop("coord_origin")
        await backing.snapshot("g6", legacy)
        bind_workspace_sources(ws, store)
        updated, _ = await ws.update_node("g6", "spec", {"data": legacy.nodes["spec"].data})
        ref = updated.nodes["spec"].data["rows"][0]["source_ref"]
        assert ref["bbox"] == [0, 0, 100, 100]
        assert ref.get("coord_origin") is None
    asyncio.run(run())


def test_resolution_pins_one_document_generation_across_pages(tmp_path):
    async def run():
        armed = [False]

        class ReplacingStore(FsDocStore):
            async def get_regions(self, slug, page=None):
                result = await super().get_regions(slug, page)
                if page == 1 and armed[0]:
                    armed[0] = False
                    await pipeline(store, [["NEW"], ["NEW"]]).ingest_pdf(b"B", "doc.pdf", force=True)
                return result

        store = ReplacingStore(tmp_path)
        await pipeline(store, [["OLD"], ["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        for page in (1, 2):
            regions = deepcopy(_regions())
            for region in regions:
                region["page"] = page
            await store.write_gold_region_file("doc", page, regions)
        old = store.snapshot("doc")
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        bind_workspace_sources(ws, store)
        await ws.create_workspace("g6")
        data = _input("exact")
        data["rows"].append(deepcopy(data["rows"][0]))
        data["rows"][1]["source_ref"]["page"] = 2
        armed[0] = True
        state, _ = await ws.add_node("g6", id="spec", node_type="spec", data=data)
        assert [r["source_ref"]["bbox"] for r in state.nodes["spec"].data["rows"]] == [[60, 50, 90, 60]] * 2
        # B has published meanwhile, but it cannot split the earlier operation.
        assert (await store.get_index("doc"))["document"]["source"]["sha256"] == hashlib.sha256(b"B").hexdigest()
        assert (await old.get_regions("doc", 2))["pages"][2][0]["id"] == "temperature"
        later, _ = await ws.add_node("g6", id="later", node_type="spec", data=data)
        assert later.nodes["later"].data == data
        updated, _ = await ws.update_node("g6", "spec", {"data": data})
        assert updated.nodes["spec"].data == data
    asyncio.run(run())
