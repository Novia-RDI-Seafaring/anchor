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

    `data_fields` documents which ``data`` keys this node type's renderer
    actually reads, and `body_field` names the key that holds the visible
    body/prose (if any). These power the non-blocking "this key won't
    render" warning and the queryable ``node-types`` schema surface
    (issue #191). When `data_fields` is ``None`` the type is treated as
    open — no unknown-key warning is emitted (the v1 behaviour).
    """

    name: str
    description: str = ""
    data_schema: type[BaseModel] | None = None
    extra_validate: _DataValidator | None = None
    data_fields: tuple[str, ...] | None = None
    body_field: str | None = None

    def validate(self, data: dict[str, Any]) -> None:
        if self.data_schema is not None:
            try:
                self.data_schema.model_validate(data)
            except Exception as exc:
                raise NodeTypeError(f"{self.name}: {exc}") from exc
        if self.extra_validate is not None:
            self.extra_validate(data)

    def unknown_data_keys(self, data: dict[str, Any]) -> list[str]:
        """Return the ``data`` keys this type's renderer will ignore.

        Empty when the type is open (`data_fields is None`) or every key
        is recognised. Used to surface a non-blocking warning so a write
        never silently drops a dead field (issue #191)."""
        if self.data_fields is None:
            return []
        known = set(self.data_fields)
        return sorted(k for k in data if k not in known)


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

    def unknown_data_keys(self, name: str, data: dict[str, Any]) -> list[str]:
        """Return the ``data`` keys ``name``'s renderer ignores.

        Empty when ``name`` is unregistered or open, or when every key is
        recognised (issue #191)."""
        nt = self._types.get(name)
        if nt is None:
            return []
        return nt.unknown_data_keys(data)

    def schema(self, name: str | None = None) -> list[dict[str, Any]]:
        """Describe registered node types for the ``node-types`` surface.

        With ``name`` given, returns a one-element list for that type (empty
        if unregistered). Without it, returns every registered type. Each
        entry: ``{name, description, data_fields, body_field}``. This is the
        queryable per-node-type data contract agents were missing (#191)."""
        if name is not None:
            nt = self._types.get(name)
            return [_describe(nt)] if nt is not None else []
        return [_describe(self._types[k]) for k in sorted(self._types)]


def _describe(nt: NodeType) -> dict[str, Any]:
    return {
        "name": nt.name,
        "description": nt.description,
        "data_fields": list(nt.data_fields) if nt.data_fields is not None else None,
        "body_field": nt.body_field,
    }


EMPTY_REGISTRY = NodeTypeRegistry()
