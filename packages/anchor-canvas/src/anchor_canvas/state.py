"""Canvas state — in-memory graph with JSON file persistence and WebSocket broadcast."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CanvasNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    node_type: str = "concept"  # concept, entity, fact, document, spec, image, area, fmu, model, plot
    label: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasEdge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: str
    target: str
    label: str = ""
    edge_type: str = "floating"  # floating, anchored
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasState(BaseModel):
    nodes: dict[str, CanvasNode] = Field(default_factory=dict)
    edges: dict[str, CanvasEdge] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Canvas:
    """Manages canvas state with persistence and change notifications."""

    def __init__(self, state_file: Path | None = None):
        self.state = CanvasState()
        self.state_file = state_file
        self._listeners: list = []
        self._version = 0

        if state_file and state_file.exists():
            self._load()

    @property
    def version(self) -> int:
        return self._version

    def add_node(self, **kwargs: Any) -> CanvasNode:
        node = CanvasNode(**kwargs)
        self.state.nodes[node.id] = node
        self._changed("node_added", {"node": node.model_dump()})
        return node

    def update_node(self, node_id: str, **kwargs: Any) -> CanvasNode | None:
        node = self.state.nodes.get(node_id)
        if not node:
            return None
        for k, v in kwargs.items():
            if hasattr(node, k):
                setattr(node, k, v)
            else:
                node.data[k] = v
        self._changed("node_updated", {"node": node.model_dump()})
        return node

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self.state.nodes:
            return False
        del self.state.nodes[node_id]
        # Remove connected edges
        to_remove = [eid for eid, e in self.state.edges.items()
                     if e.source == node_id or e.target == node_id]
        for eid in to_remove:
            del self.state.edges[eid]
        self._changed("node_removed", {"id": node_id, "edges_removed": to_remove})
        return True

    def add_edge(self, **kwargs: Any) -> CanvasEdge | None:
        edge = CanvasEdge(**kwargs)
        # Validate endpoints exist
        if edge.source not in self.state.nodes or edge.target not in self.state.nodes:
            return None
        self.state.edges[edge.id] = edge
        self._changed("edge_added", {"edge": edge.model_dump()})
        return edge

    def remove_edge(self, edge_id: str) -> bool:
        if edge_id not in self.state.edges:
            return False
        del self.state.edges[edge_id]
        self._changed("edge_removed", {"id": edge_id})
        return True

    def get_state(self) -> dict:
        return {
            "version": self._version,
            "nodes": [n.model_dump() for n in self.state.nodes.values()],
            "edges": [e.model_dump() for e in self.state.edges.values()],
            "metadata": self.state.metadata,
        }

    def clear(self) -> None:
        self.state = CanvasState()
        self._changed("cleared", {})

    def on_change(self, listener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener) -> None:
        self._listeners = [l for l in self._listeners if l is not listener]

    def _changed(self, event: str, payload: dict) -> None:
        self._version += 1
        self._save()
        msg = {"event": event, "version": self._version, "ts": time.time(), **payload}
        for listener in self._listeners:
            listener(msg)

    def _save(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.get_state(), indent=2))

    def _load(self) -> None:
        data = json.loads(self.state_file.read_text())
        self._version = data.get("version", 0)
        self.state.metadata = data.get("metadata", {})
        for n in data.get("nodes", []):
            node = CanvasNode(**n)
            self.state.nodes[node.id] = node
        for e in data.get("edges", []):
            edge = CanvasEdge(**e)
            self.state.edges[edge.id] = edge
