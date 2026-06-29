"""WorkspaceService references store — create / list / attach (#147 slice 1)."""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.workspace.references import ReferenceError, validate_source_ref
from anchor.core.workspace.workspace import CommandError
from tests.fixtures.services import make_in_memory_services


def test_create_reference_appears_in_list():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        ref = await s.workspace.create_reference(
            "w1",
            source_ref={"slug": "datasheet", "page": 3, "bbox": [1, 2, 3, 4]},
            label="Max inlet pressure",
        )
        assert ref["id"]  # server-assigned
        assert ref["label"] == "Max inlet pressure"
        assert ref["created_by"] == "human"
        # created_at is seeded from the injected clock -> deterministic shape.
        assert isinstance(ref["created_at"], float)
        listed = await s.workspace.list_references("w1")
        assert [r["id"] for r in listed] == [ref["id"]]

    asyncio.run(run())


def test_create_reference_emits_event():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        out: list = []

        async def collect():
            async for evt in s.bus.subscribe("w1"):
                out.append(evt)
                return out
            return out

        task = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await s.workspace.create_reference("w1", source_ref={"slug": "d", "page": 1})
        events = await asyncio.wait_for(task, timeout=1.0)
        assert events[0].type == "ReferenceCreated"
        assert events[0].payload["reference"]["source_ref"]["slug"] == "d"

    asyncio.run(run())


def test_attach_reference_sets_node_source_ref_and_pointer():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="n1", node_type="fact")
        ref = await s.workspace.create_reference(
            "w1", source_ref={"slug": "d", "page": 2, "region_id": "r1"},
        )
        state, env = await s.workspace.attach_reference("w1", ref["id"], node_id="n1")
        assert env.type == "ReferenceAttached"
        node = state.nodes["n1"]
        assert node.data["reference_id"] == ref["id"]
        assert node.data["source_ref"]["slug"] == "d"
        assert node.data["source_ref"]["region_id"] == "r1"

    asyncio.run(run())


def test_attach_reference_to_spec_row():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node(
            "w1", id="spec1", node_type="spec",
            data={"rows": [{"key": "P-101", "value": "150 mm"}]},
        )
        ref = await s.workspace.create_reference("w1", source_ref={"slug": "d", "page": 5})
        state, _ = await s.workspace.attach_reference(
            "w1", ref["id"], node_id="spec1", row_index=0,
        )
        row = state.nodes["spec1"].data["rows"][0]
        assert row["reference_id"] == ref["id"]
        assert row["source_ref"]["page"] == 5
        # The other row fields survive.
        assert row["key"] == "P-101" and row["value"] == "150 mm"

    asyncio.run(run())


def test_list_references_backward_compatible_empty():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        # A canvas that never had a reference behaves exactly as today.
        assert await s.workspace.list_references("w1") == []
        state = await s.workspace.get_state("w1")
        # No `references` key forced into metadata until one is created.
        assert "references" not in state["metadata"]

    asyncio.run(run())


def test_create_reference_rejects_malformed_source_ref():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with pytest.raises(CommandError):
            await s.workspace.create_reference("w1", source_ref={"page": 3})  # no slug
        with pytest.raises(CommandError):
            await s.workspace.create_reference("w1", source_ref={"slug": "d"})  # no page
        with pytest.raises(CommandError):
            await s.workspace.create_reference(
                "w1", source_ref={"slug": "d", "page": "three"},  # page not int
            )

    asyncio.run(run())


def test_attach_unknown_reference_errors():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="n1")
        with pytest.raises(CommandError):
            await s.workspace.attach_reference("w1", "ghost", node_id="n1")

    asyncio.run(run())


def test_attach_unknown_node_errors():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        ref = await s.workspace.create_reference("w1", source_ref={"slug": "d", "page": 1})
        with pytest.raises(CommandError):
            await s.workspace.attach_reference("w1", ref["id"], node_id="ghost")

    asyncio.run(run())


def test_validate_source_ref_rejects_non_dict():
    with pytest.raises(ReferenceError):
        validate_source_ref("not-a-dict")
    with pytest.raises(ReferenceError):
        validate_source_ref({"slug": "d", "page": True})  # bool is not a page


def test_validate_source_ref_passes_optional_detail():
    sref = validate_source_ref(
        {"slug": "d", "page": 1, "detail": {"quote": "max 5 bar"}},
    )
    assert sref.detail is not None
    assert sref.detail.quote == "max 5 bar"
