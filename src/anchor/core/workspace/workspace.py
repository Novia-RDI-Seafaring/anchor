"""Workspace aggregate — pure domain.

Holds the current state of one canvas. Mutations are expressed as events
that go through `apply()`. Invariants are enforced inside this module:
no I/O, no transport, no event bus, no persistence.

Node types are *open*: validation consults a `NodeTypeRegistry` provided
by the application. If no registry is wired (the default), every
`node_type` is permitted with no extra checks. See `node_types.py` for
how to register a new type with its own data schema and renderer.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anchor.core.events.canvas import (
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
)
from anchor.core.workspace.edges import Edge  # noqa: F401  (re-exported)
from anchor.core.workspace.merge import deep_merge
from anchor.core.workspace.node_types import (
    EMPTY_REGISTRY,
    NodeTypeError,
    NodeTypeRegistry,
)
from anchor.core.workspace.nodes import Node  # noqa: F401  (re-exported)


class WorkspaceMeta(BaseModel):
    slug: str
    title: str = ""
    created_at: float = 0.0


class Workspace(BaseModel):
    """A canvas. Mutated only by applying events."""

    slug: str
    title: str = ""
    version: int = 0
    nodes: dict[str, Node] = Field(default_factory=dict)
    edges: dict[str, Edge] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_event_id: str | None = None

    def get_state(self) -> dict[str, Any]:
        """Wire shape — what the SSE/HTTP client sees."""
        return {
            "slug": self.slug,
            "title": self.title,
            "version": self.version,
            "nodes": [n.model_dump() for n in self.nodes.values()],
            "edges": [e.model_dump() for e in self.edges.values()],
            "metadata": self.metadata,
        }


class CommandError(ValueError):
    """Raised when a command violates a workspace invariant."""


def validate_command(
    state: Workspace,
    cmd: BaseModel,
    *,
    node_types: NodeTypeRegistry | None = None,
) -> None:
    """Check the command against state invariants and (optionally) node-type rules."""
    types = node_types or EMPTY_REGISTRY

    if isinstance(cmd, EdgeAdded):
        if cmd.source not in state.nodes:
            raise CommandError(f"edge source {cmd.source!r} does not exist")
        if cmd.target not in state.nodes:
            raise CommandError(f"edge target {cmd.target!r} does not exist")
        if cmd.edge_type == "anchored" and cmd.data.get("kind") == "evidence":
            if not cmd.data.get("source_ref"):
                raise CommandError("evidence edge requires data.source_ref")
    elif isinstance(cmd, NodeReparented):
        if cmd.parent is not None and cmd.parent not in state.nodes:
            raise CommandError(f"parent {cmd.parent!r} does not exist")
        if cmd.id not in state.nodes:
            raise CommandError(f"node {cmd.id!r} does not exist")
    elif isinstance(cmd, NodeUpdated):
        if cmd.id not in state.nodes:
            raise CommandError(f"node {cmd.id!r} does not exist")
        if "data" in cmd.fields and isinstance(cmd.fields["data"], dict):
            existing = state.nodes[cmd.id]
            # Validate the post-merge data so the registry sees exactly what
            # the reducer will store (deep-merge, None deletes — issue #192).
            new_data: dict[str, Any] = deep_merge(existing.data, cmd.fields["data"])
            try:
                types.validate(existing.node_type, new_data)
            except NodeTypeError as e:
                raise CommandError(str(e)) from e
    elif isinstance(cmd, (NodeRemoved, NodeMoved, NodeResized)):
        if cmd.id not in state.nodes:
            raise CommandError(f"node {cmd.id!r} does not exist")
    elif isinstance(cmd, NodeAdded):
        if cmd.parent is not None and cmd.parent not in state.nodes:
            raise CommandError(f"parent {cmd.parent!r} does not exist")
        if cmd.id in state.nodes:
            raise CommandError(f"node {cmd.id!r} already exists")
        try:
            types.validate(cmd.node_type, cmd.data)
        except NodeTypeError as e:
            raise CommandError(str(e)) from e
    elif isinstance(cmd, (EdgeRemoved, EdgeUpdated)):
        if cmd.id not in state.edges:
            raise CommandError(f"edge {cmd.id!r} does not exist")
    elif isinstance(cmd, ReferenceAttached):
        if cmd.node_id not in state.nodes:
            raise CommandError(f"node {cmd.node_id!r} does not exist")
        if cmd.row_index is not None:
            node = state.nodes[cmd.node_id]
            rows = node.data.get("rows")
            if not isinstance(rows, list) or not (0 <= cmd.row_index < len(rows)):
                raise CommandError(
                    f"row_index {cmd.row_index} out of range for node {cmd.node_id!r}"
                )
