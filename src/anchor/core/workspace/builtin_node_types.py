"""Built-in node-type data contract — the agent-reachable schema.

Issue #191: ``add_node`` used to accept arbitrary ``data`` with no schema,
so a body packed into the wrong key (``data.body`` on a ``fact`` that
renders ``data.text``) was silently dropped on render. This module names,
per built-in node type, exactly which ``data`` keys the web renderer reads
and which one is the visible body. It is the single source of truth for:

  - the non-blocking "this key won't render" warning the write adapters
    attach to their result, and
  - the queryable ``node-types`` schema surface (CLI / HTTP / MCP).

The field lists mirror the React shapes in ``web/src/canvas/shapes/*.tsx``
plus the shared colour / placeholder helpers (``web/src/canvas/colors.ts``,
``placeholder.ts``). Keep the two sides in sync: a key a renderer reads
must appear here, or agents get a false "won't render" warning.

Producer node types (``spec``, ``document``, ``model3d``, ``sysml:*`` …)
are intentionally NOT enumerated here — they carry rich, producer-defined
``data`` shapes (rows, source_ref, region ids) and registering a closed
field list for them would warn on legitimate keys. They stay open (no
warning), which matches the v1 behaviour. The structural shapes and cards
an agent scaffolds by hand are where the dead-field footgun bites, so those
are the ones we pin down.
"""
from __future__ import annotations

from anchor.core.workspace.node_types import NodeType, NodeTypeRegistry

# Cross-cutting data keys every shape/card renderer honours via the shared
# colour + placeholder + resize helpers. Promoted to a constant so each
# type's field list reads as "common + its own".
_COMMON_FIELDS: tuple[str, ...] = (
    "label",
    "dashed",
    "width",
    "height",
    "bg_color",
    "stroke_color",
    "text_color",
    "text_bold",
    "text_align",
    "text_family",
    "text_size",
    "placeholder",
    "placeholder_hint",
)


def _shape(name: str, description: str, *extra: str, body_field: str | None = None) -> NodeType:
    return NodeType(
        name=name,
        description=description,
        data_fields=_COMMON_FIELDS + extra,
        body_field=body_field,
    )


BUILTIN_NODE_TYPES: list[NodeType] = [
    _shape(
        "fact",
        "Single-assertion card. Renders data.label (heading) and data.text "
        "(body). Put the body/TLDR in data.text — data.body is NOT rendered.",
        "text",
        "pictogram",
        body_field="text",
    ),
    _shape(
        "concept",
        "Rounded-rectangle shape. Renders data.label and data.subtitle "
        "(short, truncated). There is no long-body field — use data.subtitle "
        "for a one-liner; data.body is NOT rendered.",
        "subtitle",
        "pictogram",
        body_field="subtitle",
    ),
    _shape(
        "note",
        "Free-form sticky note. Renders data.label (heading) and data.text "
        "(multi-line body).",
        "text",
        body_field="text",
    ),
    _shape(
        "entity",
        "Circular shape. Renders data.label and an optional data.pictogram.",
        "pictogram",
    ),
    _shape(
        "funnel",
        "Diamond shape. Renders data.label and an optional data.pictogram.",
        "pictogram",
    ),
    _shape(
        "area",
        "Dashed container/sub-graph. Renders data.label, data.subtitle, and "
        "data.tone (accent style).",
        "subtitle",
        "tone",
        body_field="subtitle",
    ),
]


def builtin_node_type_registry() -> NodeTypeRegistry:
    """A fresh registry pre-loaded with the built-in shape / card types.

    Wired into ``WorkspaceService`` by the adapters so every write surface
    gets the unknown-key warning and the queryable schema for free."""
    return NodeTypeRegistry(list(BUILTIN_NODE_TYPES))
