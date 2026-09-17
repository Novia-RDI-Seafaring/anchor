"""Fold the event log into a "what changed since" summary (#325).

``fold_changes`` is a pure server-side fold over a window of ``DomainEvent``
envelopes: it collapses per-element event runs (add + N updates + maybe a
remove) into one net entry per element, grouped by the actor responsible.
No storage change — the fold reads the same ``events.jsonl`` records replay
uses.

Net-effect rules per element (node or edge):

- did not exist at the window start, exists at the end  → **added**
- existed at the start, still exists, was touched       → **updated**
- existed at the start, gone at the end                 → **removed**
- did not exist at the start, gone at the end           → omitted (net zero)

Attribution per entry follows the *defining* event: an added element is
credited to the actor of its add, a removed one to its remover, and an
updated one to the last actor who touched it. Events recorded before actor
attribution existed (#322) carry ``actor=None`` and group under the ``None``
actor, which UIs render as "earlier".

``last_touched_by`` powers persisted per-node attribution: the last actor
to touch each surviving node across the whole log, so the "edited by" chip
has an answer after a cold boot, not just for this session's SSE stream.
"""
from __future__ import annotations

from typing import Any

from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.workspace import Workspace

# Events that count as "touching" a node — mirrors the web store's live
# NODE_TOUCHING_EVENTS set so session attribution and persisted attribution
# agree on what a touch is.
NODE_TOUCH_EVENTS = frozenset({
    "NodeAdded", "NodeMoved", "NodeResized", "NodeUpdated", "NodeReparented",
})
NODE_EVENTS = NODE_TOUCH_EVENTS | {"NodeRemoved"}
EDGE_EVENTS = frozenset({"EdgeAdded", "EdgeRemoved", "EdgeUpdated"})

_ADD_EVENTS = frozenset({"NodeAdded", "EdgeAdded"})
_REMOVE_EVENTS = frozenset({"NodeRemoved", "EdgeRemoved"})

_ActorKey = tuple[str, str | None, str | None] | None


def _actor_dict(event: DomainEvent) -> dict[str, Any] | None:
    """The wire shape of an event's actor: ``{kind, label}`` or ``None``."""
    if event.actor is None:
        return None
    return {"kind": event.actor.kind, "label": event.actor.label}


def _actor_key(event: DomainEvent) -> _ActorKey:
    """Grouping key for an actor. ``None`` groups the legacy actor-less
    events (recorded before #322) into the "earlier" bucket."""
    if event.actor is None:
        return None
    return (event.actor.kind, event.actor.id, event.actor.label)


class _ElementTrack:
    """Per-element accumulator while walking the window in order."""

    __slots__ = (
        "first_event_is_add", "removed", "add_event", "remove_event",
        "last_touch_event", "label", "node_type", "source", "target",
    )

    def __init__(self, *, first_event_is_add: bool) -> None:
        self.first_event_is_add = first_event_is_add
        self.removed = False
        self.add_event: DomainEvent | None = None
        self.remove_event: DomainEvent | None = None
        self.last_touch_event: DomainEvent | None = None
        self.label: str | None = None
        self.node_type: str | None = None
        self.source: str | None = None
        self.target: str | None = None


def _remember_labels(t: _ElementTrack, event: DomainEvent) -> None:
    """Keep the freshest label/type/topology seen in the window so a removed
    element (absent from the final state) still renders with a name."""
    p = event.payload
    if event.type in _ADD_EVENTS:
        if isinstance(p.get("label"), str):
            t.label = p["label"]
        if isinstance(p.get("node_type"), str):
            t.node_type = p["node_type"]
        if isinstance(p.get("source"), str):
            t.source = p["source"]
        if isinstance(p.get("target"), str):
            t.target = p["target"]
    elif event.type in {"NodeUpdated", "EdgeUpdated"}:
        fields = p.get("fields")
        if isinstance(fields, dict) and isinstance(fields.get("label"), str):
            t.label = fields["label"]


def fold_changes(
    events: list[DomainEvent],
    state: Workspace,
    *,
    from_version: int = 0,
) -> dict[str, Any]:
    """Fold a window of events into the grouped changes summary.

    ``events`` must be the window itself (already filtered to versions after
    the caller's boundary), in ascending version order. ``state`` is the
    workspace's CURRENT state, used to resolve labels for elements that
    still exist; elements gone from the state fall back to the freshest
    label their window events carried.
    """
    node_tracks: dict[str, _ElementTrack] = {}
    edge_tracks: dict[str, _ElementTrack] = {}
    # CanvasCleared wipes every element — including pre-window elements the
    # per-element fold cannot honestly enumerate — so a clear is surfaced as
    # a `canvas_cleared` flag on the clearing actor's group instead.
    clears: list[DomainEvent] = []

    for event in events:
        if event.type == "CanvasCleared":
            clears.append(event)
            for t in [*node_tracks.values(), *edge_tracks.values()]:
                t.removed = True
                t.remove_event = event
            continue
        element_id = event.payload.get("id")
        if not isinstance(element_id, str):
            continue
        if event.type in NODE_EVENTS:
            tracks = node_tracks
        elif event.type in EDGE_EVENTS:
            tracks = edge_tracks
        else:
            continue
        t = tracks.get(element_id)
        if t is None:
            t = _ElementTrack(first_event_is_add=event.type in _ADD_EVENTS)
            tracks[element_id] = t
        _remember_labels(t, event)
        if event.type in _ADD_EVENTS:
            t.add_event = event
            t.last_touch_event = event
            t.removed = False
        elif event.type in _REMOVE_EVENTS:
            t.remove_event = event
            t.removed = True
        else:
            t.last_touch_event = event

    groups: dict[_ActorKey, dict[str, Any]] = {}
    group_order: dict[_ActorKey, int] = {}

    def group_for(event: DomainEvent) -> dict[str, Any]:
        key = _actor_key(event)
        g = groups.get(key)
        if g is None:
            g = {
                "actor": _actor_dict(event),
                "nodes_added": [],
                "nodes_updated": [],
                "nodes_removed": [],
                "edges_added": [],
                "edges_updated": [],
                "edges_removed": [],
            }
            groups[key] = g
            group_order[key] = event.version
        return g

    def node_entry(element_id: str, t: _ElementTrack) -> dict[str, Any]:
        node = state.nodes.get(element_id)
        if node is not None:
            return {"id": element_id, "label": node.label, "node_type": node.node_type}
        return {
            "id": element_id,
            "label": t.label or "",
            "node_type": t.node_type or "",
        }

    def edge_entry(element_id: str, t: _ElementTrack) -> dict[str, Any]:
        edge = state.edges.get(element_id)
        if edge is not None:
            return {
                "id": element_id, "label": edge.label,
                "source": edge.source, "target": edge.target,
            }
        return {
            "id": element_id, "label": t.label or "",
            "source": t.source or "", "target": t.target or "",
        }

    def place(
        t: _ElementTrack,
        entry: dict[str, Any],
        *,
        kind: str,
        exists_after: bool,
    ) -> None:
        existed_before = not t.first_event_is_add
        if not existed_before and exists_after:
            # Born in the window: credit the adder.
            if t.add_event is not None:
                group_for(t.add_event)[f"{kind}_added"].append(entry)
        elif existed_before and exists_after:
            # Touched (possibly removed and re-added): credit the last touch.
            source = t.last_touch_event or t.add_event
            if source is not None:
                group_for(source)[f"{kind}_updated"].append(entry)
        elif existed_before and not exists_after:
            # Gone: credit the remover.
            if t.remove_event is not None:
                group_for(t.remove_event)[f"{kind}_removed"].append(entry)
        # not existed_before and not exists_after → net zero, omitted.

    for element_id, t in node_tracks.items():
        exists_after = not t.removed and element_id in state.nodes
        place(t, node_entry(element_id, t), kind="nodes", exists_after=exists_after)
    for element_id, t in edge_tracks.items():
        exists_after = not t.removed and element_id in state.edges
        place(t, edge_entry(element_id, t), kind="edges", exists_after=exists_after)
    for event in clears:
        group_for(event)["canvas_cleared"] = True

    ordered = [groups[key] for key in sorted(groups, key=lambda k: group_order[k])]
    return {
        "from_version": from_version,
        "to_version": state.version,
        "groups": ordered,
    }


def last_touched_by(
    events: list[DomainEvent], state: Workspace,
) -> dict[str, dict[str, Any] | None]:
    """Per-node "last touched by" over the whole log (#325 persisted
    attribution). Only nodes present in the final state are answered; a
    node whose last touch predates actor attribution maps to ``None`` so a
    UI can honestly say "unknown / earlier" rather than guessing."""
    touched: dict[str, dict[str, Any] | None] = {}
    for event in events:
        if event.type not in NODE_TOUCH_EVENTS:
            continue
        node_id = event.payload.get("id")
        if isinstance(node_id, str):
            touched[node_id] = _actor_dict(event)
    return {
        node_id: actor
        for node_id, actor in touched.items()
        if node_id in state.nodes
    }
