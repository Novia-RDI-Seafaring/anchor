"""Node-type registry — runtime-extensible.

Applications register domain-specific node types here, providing optional
metadata (a Pydantic schema for the `data` field, a custom invariant
validator). Core uses the registry to validate `data` shapes when commands
arrive, and frontends use a parallel registry of React renderers keyed by
`node_type` (see `web/src/canvas/nodes/index.ts`).

Nothing in core hard-codes a vocabulary. If no registry is wired up, every
`node_type` is permitted with no extra validation — the v1 behaviour, but
explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


class _DataValidator(Protocol):
    def __call__(self, data: dict[str, Any]) -> None:
        """Raise NodeTypeError if data is invalid for this node type."""


class NodeTypeError(ValueError):
    """Raised when node data does not satisfy a registered node type."""


@dataclass(frozen=True)
class NodeType:
    """Registration record for a node type.

    `data_schema` is an optional Pydantic model used to validate the
    `node.data` payload at command time. `extra_validate` is an optional
    extra hook for cross-field invariants the schema can't express.
    """

    name: str
    description: str = ""
    data_schema: type[BaseModel] | None = None
    extra_validate: _DataValidator | None = None

    def validate(self, data: dict[str, Any]) -> None:
        if self.data_schema is not None:
            try:
                self.data_schema.model_validate(data)
            except Exception as exc:
                raise NodeTypeError(f"{self.name}: {exc}") from exc
        if self.extra_validate is not None:
            self.extra_validate(data)


class NodeTypeRegistry:
    """Open registry — add types at runtime, look them up at command time."""

    def __init__(self, types: list[NodeType] | None = None) -> None:
        self._types: dict[str, NodeType] = {t.name: t for t in (types or [])}

    def register(self, node_type: NodeType) -> None:
        if node_type.name in self._types:
            raise ValueError(f"node type {node_type.name!r} already registered")
        self._types[node_type.name] = node_type

    def unregister(self, name: str) -> None:
        self._types.pop(name, None)

    def get(self, name: str) -> NodeType | None:
        return self._types.get(name)

    def names(self) -> list[str]:
        return sorted(self._types)

    def validate(self, name: str, data: dict[str, Any]) -> None:
        """Validate `data` for `name` if registered; otherwise no-op."""
        nt = self._types.get(name)
        if nt is not None:
            nt.validate(data)


EMPTY_REGISTRY = NodeTypeRegistry()
