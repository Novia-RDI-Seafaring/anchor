"""apply(state, event) → state — pure event-sourced reducer.

The reducer is total: every event in the canvas-event union has a branch.
Returns a NEW Workspace; the input is not mutated. This is what
`infra/bus/replay.py` uses to rebuild state from events.jsonl on cold boot.

`NodeRemoved` cascades to additional `EdgeRemoved` events the caller should
publish. We expose a helper (`cascade_events_for_remove`) so the workspace
service can emit them in the same atomic block.
"""
from __future__ import annotations

from pydantic import BaseModel

from anchor.core.events.canvas import (
    CanvasCleared,
    CanvasSnapshot,
    EdgeAdded,
    EdgeRemoved,
    EdgeUpdated,
    NodeAdded,
    NodeMoved,
    NodeRemoved,
    NodeReparented,
    NodeResized,
    NodeUpdated,
    ReferenceAttached,
    ReferenceCreated,
    ReferenceRemoved,
    ReferenceUpdated,
)
from anchor.core.workspace.edges import Edge
from anchor.core.workspace.merge import deep_merge
from anchor.core.workspace.nodes import Node
from anchor.core.workspace.workspace import Workspace


def apply(state: Workspace, evt: BaseModel) -> Workspace:
    """Apply one event to the state. Returns a new Workspace.

    Does NOT bump `version` — that's the caller's job (so version assignment
    matches the persisted envelope's version).
    """
    new = state.model_copy(deep=True)

    if isinstance(evt, NodeAdded):
        new.nodes[evt.id] = Node(
            id=evt.id, node_type=evt.node_type, label=evt.label,
            x=evt.x, y=evt.y, width=evt.width, height=evt.height,
            parent=evt.parent, data=dict(evt.data),
        )
    elif isinstance(evt, NodeRemoved):
        new.nodes.pop(evt.id, None)
        new.edges = {
            eid: e for eid, e in new.edges.items()
            if e.source != evt.id and e.target != evt.id
        }
    elif isinstance(evt, NodeMoved):
        if evt.id in new.nodes:
            n = new.nodes[evt.id]
            n.x = evt.x
            n.y = evt.y
    elif isinstance(evt, NodeResized):
        if evt.id in new.nodes:
            n = new.nodes[evt.id]
            n.width = evt.width
            n.height = evt.height
    elif isinstance(evt, NodeUpdated):
        if evt.id in new.nodes:
            n = new.nodes[evt.id]
            for k, v in evt.fields.items():
                if k == "data" and isinstance(v, dict):
                    # Deep-merge the patch into the node's existing data so
                    # unmentioned keys (e.g. source_ref) survive; a None
                    # value in the patch deletes that key. Replace-the-whole
                    # -dict was issue #192's data-loss footgun.
                    n.data = deep_merge(n.data, v)
                elif hasattr(n, k) and k not in {"id"}:
                    setattr(n, k, v)
                else:
                    n.data[k] = v
    elif isinstance(evt, NodeReparented):
        if evt.id in new.nodes:
            new.nodes[evt.id].parent = evt.parent
    elif isinstance(evt, EdgeAdded):
        new.edges[evt.id] = Edge(
            id=evt.id, source=evt.source, target=evt.target,
            label=evt.label, edge_type=evt.edge_type,
            sourceHandle=evt.sourceHandle, targetHandle=evt.targetHandle,
            data=dict(evt.data),
        )
    elif isinstance(evt, EdgeRemoved):
        new.edges.pop(evt.id, None)
    elif isinstance(evt, EdgeUpdated):
        if evt.id in new.edges:
            e = new.edges[evt.id]
            for k, v in evt.fields.items():
                if k == "data" and isinstance(v, dict):
                    # Same merge-not-replace contract as NodeUpdated (#192).
                    e.data = deep_merge(e.data, v)
                elif hasattr(e, k) and k not in {"id", "source", "target"}:
                    setattr(e, k, v)
                else:
                    e.data[k] = v
    elif isinstance(evt, ReferenceCreated):
        # Append to the canvas bibliography in metadata. Backward compatible:
        # a canvas with no `references` key gets one lazily here.
        refs = new.metadata.get("references")
        if not isinstance(refs, list):
            refs = []
        refs.append(dict(evt.reference))
        new.metadata["references"] = refs
    elif isinstance(evt, ReferenceRemoved):
        # Drop the matching entry from the bibliography. No-op (idempotent) when
        # the id is absent or there is no `references` list yet.
        refs = new.metadata.get("references")
        if isinstance(refs, list):
            new.metadata["references"] = [
                r for r in refs
                if not (isinstance(r, dict) and r.get("id") == evt.reference_id)
            ]
    elif isinstance(evt, ReferenceUpdated):
        # Edit the matching entry's label in place; the source_ref is immutable.
        refs = new.metadata.get("references")
        if isinstance(refs, list):
            updated = []
            for r in refs:
                if isinstance(r, dict) and r.get("id") == evt.reference_id:
                    r = {**r, "label": evt.label}
                updated.append(r)
            new.metadata["references"] = updated
    elif isinstance(evt, ReferenceAttached):
        # Point the target node (and optional spec row) at the reference so a
        # fact resolves to its citation by id and carries the source_ref that
        # drives the value-level highlight.
        node = new.nodes.get(evt.node_id)
        if node is not None:
            if evt.row_index is None:
                node.data["reference_id"] = evt.reference_id
                node.data["source_ref"] = dict(evt.source_ref)
            else:
                rows = node.data.get("rows")
                if isinstance(rows, list) and 0 <= evt.row_index < len(rows):
                    row = rows[evt.row_index]
                    if isinstance(row, dict):
                        row["reference_id"] = evt.reference_id
                        row["source_ref"] = dict(evt.source_ref)
    elif isinstance(evt, CanvasCleared):
        new.nodes = {}
        new.edges = {}
    elif isinstance(evt, CanvasSnapshot):
        new.nodes = {n["id"]: Node(**n) for n in evt.nodes}
        new.edges = {e["id"]: Edge(**e) for e in evt.edges}
        new.metadata = dict(evt.metadata)
    else:
        raise TypeError(f"unknown event type: {type(evt).__name__}")

    return new


def cascade_events_for_remove(state: Workspace, node_id: str) -> list[EdgeRemoved]:
    """Return the EdgeRemoved events that must accompany a NodeRemoved."""
    return [
        EdgeRemoved(id=eid)
        for eid, e in state.edges.items()
        if e.source == node_id or e.target == node_id
    ]
