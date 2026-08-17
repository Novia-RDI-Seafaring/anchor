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

The structural shapes and cards an agent scaffolds by hand carry a *closed*
field list (``data_fields``), so a body packed into the wrong key raises the
"won't render" warning.

Producer node types (``spec``, ``document``, ``model3d`` / ``cad:model`` …)
carry rich, producer-defined ``data`` shapes (rows, source_ref, region ids,
model slugs). A closed field list would false-warn on those legitimate keys,
so they are registered *open* (``data_fields=None`` — no unknown-key warning,
matching v1). But they are still enumerated here, with a ``description`` that
names the keys that matter, so ``node-types <type>`` DESCRIBES them instead of
returning "unknown" — the discoverability an agent needs to learn that a CAD
node's slug key is ``cad_slug`` (not ``slug``) without reading the React
source. ``sysml:*`` and other extension types register themselves.
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


def _producer(name: str, description: str) -> NodeType:
    """An open producer type: no closed field list (``data_fields=None`` →
    no unknown-key warning on its rich shape) but still queryable via
    ``node-types`` so agents can discover its key names from ``description``."""
    return NodeType(name=name, description=description, data_fields=None)


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
    # Producer types: open shapes (no unknown-key warning) documented for
    # discoverability. Descriptions name the keys that matter.
    _producer(
        "spec",
        "Spec / dimension table (open shape). data.rows = list of "
        "{key, value, source_ref{slug,page,region_id,bbox}} rows; optional "
        "node-level data.source_ref. Extra keys allowed (no warning).",
    ),
    _producer(
        "document",
        "Ingested-PDF document card (open shape). data.slug = the document "
        "slug, data.page = current page. Extra keys allowed (no warning).",
    ),
    _producer(
        "model3d",
        "3D CAD viewport (open shape). data.cad_slug = slug of an uploaded "
        "CAD model (see `anchor cad`); data.kind = stl | obj | gltf | glb. "
        "NOTE: the slug key is cad_slug, NOT slug. Extra keys allowed.",
    ),
    _producer(
        "cad:model",
        "3D CAD viewport (open shape, alias of model3d). data.cad_slug = slug "
        "of an uploaded CAD model (see `anchor cad`); data.kind = "
        "stl | obj | gltf | glb. NOTE: the slug key is cad_slug, NOT slug. "
        "Extra keys allowed (no warning).",
    ),
]


def builtin_node_type_registry() -> NodeTypeRegistry:
    """A fresh registry pre-loaded with the built-in shape / card types.

    Wired into ``WorkspaceService`` by the adapters so every write surface
    gets the unknown-key warning and the queryable schema for free."""
    return NodeTypeRegistry(list(BUILTIN_NODE_TYPES))
