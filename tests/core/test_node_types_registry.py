"""Node-type registry — runtime extensibility for new node types."""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from anchor.core.events.canvas import NodeAdded, NodeUpdated
from anchor.core.workspace import (
    CommandError,
    NodeType,
    NodeTypeError,
    NodeTypeRegistry,
    Workspace,
    apply,
    validate_command,
)


def test_open_default_accepts_any_node_type():
    state = Workspace(slug="w1")
    cmd = NodeAdded(id="a", node_type="totally-new-thing", data={"foo": "bar"})
    validate_command(state, cmd)


def test_registered_type_with_pydantic_schema():
    class FmuData(BaseModel):
        filename: str
        variables: list[str] = Field(default_factory=list)

    reg = NodeTypeRegistry([
        NodeType(name="fmu", description="An FMU model node", data_schema=FmuData),
    ])
    state = Workspace(slug="w1")

    with pytest.raises(CommandError):
        validate_command(state, NodeAdded(id="a", node_type="fmu", data={}), node_types=reg)

    validate_command(
        state,
        NodeAdded(id="b", node_type="fmu", data={"filename": "pump.fmu"}),
        node_types=reg,
    )


def test_extra_validate_runs():
    seen: list[dict] = []

    def must_have_at_least_one_var(data):
        seen.append(data)
        if not data.get("variables"):
            raise NodeTypeError("fmu: variables[] cannot be empty")

    reg = NodeTypeRegistry([
        NodeType(name="fmu", extra_validate=must_have_at_least_one_var),
    ])
    state = Workspace(slug="w1")

    with pytest.raises(CommandError, match="variables"):
        validate_command(
            state,
            NodeAdded(id="a", node_type="fmu", data={"variables": []}),
            node_types=reg,
        )
    validate_command(
        state,
        NodeAdded(id="b", node_type="fmu", data={"variables": ["x"]}),
        node_types=reg,
    )
    assert len(seen) >= 1


def test_node_update_revalidates_data_against_registered_type():
    class FmuData(BaseModel):
        filename: str

    reg = NodeTypeRegistry([NodeType(name="fmu", data_schema=FmuData)])
    state = Workspace(slug="w1")
    state = apply(state, NodeAdded(id="a", node_type="fmu", data={"filename": "x.fmu"}))

    with pytest.raises(CommandError):
        validate_command(
            state,
            NodeUpdated(id="a", fields={"data": {"filename": 123}}),
            node_types=reg,
        )


def test_unregistered_type_passes_through_even_with_registry():
    reg = NodeTypeRegistry([NodeType(name="fmu")])
    state = Workspace(slug="w1")
    validate_command(
        state,
        NodeAdded(id="a", node_type="my-custom-type", data={"anything": True}),
        node_types=reg,
    )


def test_registry_register_unregister_listing():
    reg = NodeTypeRegistry()
    reg.register(NodeType(name="fmu"))
    reg.register(NodeType(name="plot"))
    assert reg.names() == ["fmu", "plot"]
    with pytest.raises(ValueError, match="already registered"):
        reg.register(NodeType(name="fmu"))
    reg.unregister("fmu")
    assert reg.names() == ["plot"]
