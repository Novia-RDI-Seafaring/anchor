"""Claim edits retain audit links without retaining a grounding verdict."""
import asyncio
from copy import deepcopy

import pytest

from anchor.adapters.project_runtime import bind_workspace_sources
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.adapters.test_value_provenance_parity import _input, _regions


def test_verified_claim_edit_is_stale_and_deliberate_revalidation_is_required():
    async def run():
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions())
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        bind_workspace_sources(ws, docs)
        await ws.create_workspace("g7")
        state, _ = await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        original = deepcopy(state.nodes["spec"].data)
        row = original["rows"][0]
        assert row["evidence"]["status"] == "verified"
        edited = deepcopy(original)
        edited["rows"][0]["value"] = "999999"
        state, event = await ws.update_node("g7", "spec", {"data": edited})
        stale = state.nodes["spec"].data["rows"][0]
        assert stale["source_ref"] == row["source_ref"]
        assert stale["evidence"]["status"] == "stale"
        assert event.payload["fields"]["data"]["rows"][0] == stale
        edited["rows"][0]["revalidate_evidence"] = True
        state, _ = await ws.update_node("g7", "spec", {"data": edited})
        assert state.nodes["spec"].data["rows"][0]["evidence"]["status"] == "stale"
        # Restoring visible text (even with copied old metadata) is not undo.
        state, _ = await ws.update_node("g7", "spec", {"data": original})
        assert state.nodes["spec"].data["rows"][0]["evidence"]["status"] == "stale"
        original["rows"][0]["revalidate_evidence"] = True
        state, _ = await ws.update_node("g7", "spec", {"data": original})
        restored = state.nodes["spec"].data["rows"][0]
        assert restored["evidence"]["status"] == "verified"
        assert restored["source_ref"] == row["source_ref"]
        assert "revalidate_evidence" not in restored
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [("key", "Temperature"), ("value", "42.0"),
                                       ("value", "42 mm"), ("value", None)])
def test_substantive_edits_are_stale_even_without_a_producer(field, value):
    async def run():
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        await ws.create_workspace("g7")
        await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        patch = _input("exact")
        patch["rows"][0][field] = value
        state, _ = await ws.update_node("g7", "spec", {"data": patch})
        row = state.nodes["spec"].data["rows"][0]
        assert row["evidence"]["status"] == "stale"
        assert row["source_ref"] == _input("exact")["rows"][0]["source_ref"]
    asyncio.run(run())


@pytest.mark.parametrize("case", ["exact", "wrong_key", "wrong_value", "missing",
                                 "ambiguous", "precise", "no_source", "null", "no_store"])
def test_only_strict_validation_can_issue_a_binding(case):
    async def run():
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions(repeated=case == "ambiguous"))
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        if case != "no_store":
            bind_workspace_sources(ws, docs)
        await ws.create_workspace("g7")
        data = _input(case if case in {"wrong_key", "wrong_value", "missing", "ambiguous"} else "exact")
        row = data["rows"][0]
        if case == "precise":
            row["source_ref"]["bbox"] = [60, 50, 90, 60]
            row["value"] = "999999"
        if case == "no_source":
            row.pop("source_ref")
        if case == "null":
            row["value"] = None
        # A transport cannot grant itself a verified verdict.
        row["evidence"] = {"status": "verified", "claim": {"key": "pressure", "value": row["value"]}}
        state, _ = await ws.add_node("g7", id="spec", node_type="spec", data=data)
        result = state.nodes["spec"].data["rows"][0]
        assert (result.get("evidence", {}).get("status") == "verified") == (case == "exact")
    asyncio.run(run())


def test_historical_links_are_not_promoted_by_unrelated_edits():
    async def run():
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        await ws.create_workspace("g7")
        await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions())
        bind_workspace_sources(ws, docs)
        state, _ = await ws.update_node("g7", "spec", {"data": {"label": "Renamed"}})
        assert "evidence" not in state.nodes["spec"].data["rows"][0]
    asyncio.run(run())


def test_normalization_noop_is_idempotent_and_new_valid_source_can_verify():
    async def run():
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions())
        bind_workspace_sources(ws, docs)
        await ws.create_workspace("g7")
        state, _ = await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        original = deepcopy(state.nodes["spec"].data)
        patch = deepcopy(original)
        patch["rows"][0].update(key="  PRESSURE ", value=" 42  ")
        state, _ = await ws.update_node("g7", "spec", {"data": patch})
        assert state.nodes["spec"].data["rows"][0]["evidence"] == original["rows"][0]["evidence"]
        changed = _input("exact")
        changed["rows"][0].update(key="Temperature")
        changed["rows"][0]["source_ref"]["region_id"] = "temperature"
        state, _ = await ws.update_node("g7", "spec", {"data": changed})
        row = state.nodes["spec"].data["rows"][0]
        assert row["evidence"]["status"] == "verified"
        assert row["source_ref"]["bbox"] == [60, 10, 90, 20]
    asyncio.run(run())


def test_invalid_new_evidence_cannot_retain_verified_and_source_deletion_is_explicit():
    async def run():
        ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        docs = MemoryDocStore()
        await docs.write_gold_region_file("doc", 1, _regions())
        bind_workspace_sources(ws, docs)
        await ws.create_workspace("g7")
        state, _ = await ws.add_node("g7", id="spec", node_type="spec", data=_input("exact"))
        patch = deepcopy(state.nodes["spec"].data)
        patch["rows"][0]["value"] = "999999"
        patch["rows"][0]["source_ref"]["region_id"] = "missing-r9"
        state, _ = await ws.update_node("g7", "spec", {"data": patch})
        row = state.nodes["spec"].data["rows"][0]
        assert row["source_ref"]["region_id"] == "missing-r9"
        assert row["evidence"]["status"] == "stale"
        assert row["evidence"]["source_ref"]["region_id"] == "pressure"
        patch["rows"][0].pop("source_ref")
        state, _ = await ws.update_node("g7", "spec", {"data": patch})
        assert "evidence" not in state.nodes["spec"].data["rows"][0]
    asyncio.run(run())
