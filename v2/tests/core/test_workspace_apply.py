"""Tests for the workspace reducer — pure event sourcing."""
from __future__ import annotations

import pytest

from anchor.core.events.canvas import (
    CanvasCleared,
    CanvasSnapshot,
    EdgeAdded,
    EdgeRemoved,
    NodeAdded,
    NodeMoved,
    NodeRemoved,
    NodeReparented,
    NodeUpdated,
)
from anchor.core.workspace import (
    CommandError,
    Workspace,
    apply,
    cascade_events_for_remove,
    validate_command,
)


def make_workspace(slug: str = "test") -> Workspace:
    return Workspace(slug=slug)


def test_node_added_inserts_node():
    state = make_workspace()
    state2 = apply(state, NodeAdded(id="a", node_type="concept", label="A"))
    assert "a" in state2.nodes
    assert state2.nodes["a"].label == "A"
    assert "a" not in state.nodes  # original not mutated


def test_node_moved_updates_position():
    state = apply(make_workspace(), NodeAdded(id="a"))
    state2 = apply(state, NodeMoved(id="a", x=100, y=200))
    assert state2.nodes["a"].x == 100
    assert state2.nodes["a"].y == 200


def test_node_updated_writes_known_attrs_and_passes_unknown_to_data():
    state = apply(make_workspace(), NodeAdded(id="a"))
    state2 = apply(state, NodeUpdated(id="a", fields={"label": "new", "custom": "value"}))
    assert state2.nodes["a"].label == "new"
    assert state2.nodes["a"].data["custom"] == "value"


def test_node_removed_drops_node_and_connected_edges():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, NodeAdded(id="b"))
    s = apply(s, EdgeAdded(id="e1", source="a", target="b"))
    s = apply(s, NodeRemoved(id="a"))
    assert "a" not in s.nodes
    assert "e1" not in s.edges


def test_cascade_helper_lists_edges_to_remove():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, NodeAdded(id="b"))
    s = apply(s, EdgeAdded(id="e1", source="a", target="b"))
    s = apply(s, EdgeAdded(id="e2", source="b", target="a"))
    cascade = cascade_events_for_remove(s, "a")
    assert {e.id for e in cascade} == {"e1", "e2"}


def test_edge_added_creates_edge():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, NodeAdded(id="b"))
    s = apply(s, EdgeAdded(id="e", source="a", target="b", label="rel"))
    assert s.edges["e"].label == "rel"


def test_edge_removed_drops_edge():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, NodeAdded(id="b"))
    s = apply(s, EdgeAdded(id="e", source="a", target="b"))
    s = apply(s, EdgeRemoved(id="e"))
    assert "e" not in s.edges


def test_node_reparented_changes_parent():
    s = make_workspace()
    s = apply(s, NodeAdded(id="parent"))
    s = apply(s, NodeAdded(id="child"))
    s = apply(s, NodeReparented(id="child", parent="parent"))
    assert s.nodes["child"].parent == "parent"


def test_canvas_cleared_drops_all():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, CanvasCleared())
    assert s.nodes == {} and s.edges == {}


def test_snapshot_replaces_state():
    s = apply(make_workspace(), NodeAdded(id="a"))
    snap = CanvasSnapshot(
        nodes=[{"id": "x", "node_type": "fact", "label": "X"}],
        edges=[],
        metadata={"foo": "bar"},
    )
    s2 = apply(s, snap)
    assert "a" not in s2.nodes
    assert "x" in s2.nodes
    assert s2.metadata == {"foo": "bar"}


def test_validate_rejects_edge_to_missing_endpoint():
    s = apply(make_workspace(), NodeAdded(id="a"))
    with pytest.raises(CommandError):
        validate_command(s, EdgeAdded(id="e", source="a", target="b"))


def test_validate_requires_source_ref_on_evidence_edges():
    s = make_workspace()
    s = apply(s, NodeAdded(id="a"))
    s = apply(s, NodeAdded(id="b"))
    bad = EdgeAdded(id="e", source="a", target="b", edge_type="anchored", data={"kind": "evidence"})
    with pytest.raises(CommandError, match="source_ref"):
        validate_command(s, bad)
    good = EdgeAdded(
        id="e", source="a", target="b", edge_type="anchored",
        data={"kind": "evidence", "source_ref": {"page": 2, "bbox": [0, 0, 1, 1]}},
    )
    validate_command(s, good)


def test_validate_rejects_duplicate_node():
    s = apply(make_workspace(), NodeAdded(id="a"))
    with pytest.raises(CommandError, match="already exists"):
        validate_command(s, NodeAdded(id="a"))


def test_validate_rejects_remove_of_missing_node():
    s = make_workspace()
    with pytest.raises(CommandError, match="does not exist"):
        validate_command(s, NodeRemoved(id="ghost"))


def test_validate_rejects_reparent_to_missing_parent():
    s = apply(make_workspace(), NodeAdded(id="a"))
    with pytest.raises(CommandError):
        validate_command(s, NodeReparented(id="a", parent="ghost"))


def test_unknown_event_raises():
    class Bogus:
        pass

    with pytest.raises(TypeError):
        apply(make_workspace(), Bogus())  # type: ignore[arg-type]


def test_get_state_serialises_to_wire_shape():
    s = apply(make_workspace(slug="my"), NodeAdded(id="a", label="A"))
    state = s.get_state()
    assert state["slug"] == "my"
    assert state["nodes"][0]["id"] == "a"
    assert "edges" in state and "metadata" in state
