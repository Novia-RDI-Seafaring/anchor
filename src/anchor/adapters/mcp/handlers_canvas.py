"""MCP tool definitions backed by WorkspaceService.

Tool names keep the v1 `canvas_*` prefix so existing agent prompts continue
to work; every tool now takes `workspace_slug` as its first arg.
"""
from __future__ import annotations

import base64
import json
import mimetypes
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError


# ── Byte-fetch envelope ─────────────────────────────────────────────────────
#
# Mirrors the contract used by anchor_pdfs.mcp_handlers._byte_envelope.
# Duplicated rather than imported because adapters/mcp/handlers_canvas
# is in core-adjacent code that shouldn't depend on an extension. The
# contract is *the* shared piece — keep these two implementations in sync.
def _byte_envelope_from_result(*, path: Path | None, bytes_: bytes | None, content_type: str, fmt: str) -> str:
    if fmt == "path":
        if path is None:
            return json.dumps({"error": "snapshot returned inline bytes; request format='base64'"})
        return json.dumps({
            "format": "path", "value": str(path), "content_type": content_type,
            "size_bytes": path.stat().st_size if path.exists() else None,
        })
    if fmt == "base64":
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    if fmt == "inline":
        # Hand the raw bytes back via the special _mcp_image_b64 marker so
        # the MCP server wrapper can promote the result to an MCP
        # ImageContent block and have the host harness display it inline.
        # SVG is not an image content type in MCP today; emit it as text.
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        if content_type.startswith("image/") and content_type != "image/svg+xml":
            return json.dumps({
                "_mcp_image_b64": base64.b64encode(raw).decode("ascii"),
                "_mcp_mime": content_type,
            })
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    return json.dumps({"error": f"unknown format: {fmt!r} (use 'path', 'base64', or 'inline')"})


def _ctype_for(name: str) -> str:
    guess, _ = mimetypes.guess_type(name)
    return guess or "application/octet-stream"


# Non-fatal nudge for the #131 failure mode: an agent dumps tabular facts into
# a spec node's prose `description` instead of structured `data.rows`. Prose is
# still allowed (some specs really are a caption), so this never blocks the
# write -- it only attaches a `hint` to the tool result steering the next call
# toward rows. Returns None when no nudge applies.
_SPEC_ROWS_HINT = (
    "This `spec` node has a prose `description` but no `data.rows`. "
    "If it holds tabular facts (IDs, values, measurements), move them into "
    "`data.rows` as [{key, value, source_ref}] so they render as a clean, "
    "source-clickable table. Keep `description` only for a short caption."
)


def _alias_type(args: dict[str, Any], canonical: str) -> None:
    """Accept ``type`` as an alias for ``node_type`` / ``edge_type`` (#186).

    Canvas state JSON exposes ``node_type`` / ``edge_type``; the write
    surfaces historically diverged. We now accept BOTH on every write
    surface so an agent can read a record's ``node_type`` and write it
    straight back. ``node_type`` / ``edge_type`` is canonical and wins if
    both are present; a bare ``type`` is promoted to the canonical key."""
    if "type" in args:
        alias = args.pop("type")
        args.setdefault(canonical, alias)


def _data_warning(svc: WorkspaceService, node_type: str | None, data: dict[str, Any] | None) -> str | None:
    """Non-blocking warning listing data keys the node type won't render (#191)."""
    if not node_type:
        return None
    unknown = svc.unknown_data_keys(node_type, data)
    if not unknown:
        return None
    keys = ", ".join(unknown)
    return (
        f"node_type {node_type!r} does not render these data keys: {keys}. "
        f"They are stored but never shown. Call canvas_node_types to see "
        f"which data fields {node_type!r} renders (e.g. its body field)."
    )


def _spec_rows_hint(node_type: str | None, data: dict[str, Any] | None) -> str | None:
    if node_type != "spec":
        return None
    data = data or {}
    has_rows = bool(data.get("rows"))
    has_description = bool(str(data.get("description") or "").strip())
    if has_description and not has_rows:
        return _SPEC_ROWS_HINT
    return None


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "canvas_get_state",
            "description": "Return the full canvas state (version, nodes, edges, metadata).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_add_node",
            "description": (
                "Add (create / place) a new node by node_type, label, x, y, parent, data.\n"
                "POSITION: omit x/y (or pass place='auto') and the server picks "
                "a non-overlapping spot and returns it under `position` — the "
                "preferred way to scaffold many nodes without piling them up. "
                "Pass explicit x/y to place exactly there.\n"
                "node_type is canonical; `type` is accepted as an alias so you "
                "can write back the `node_type` you read from canvas state.\n"
                "DATA FIELDS render per node_type — a key the renderer ignores "
                "is stored but invisible, and the result carries a `warning`. "
                "fact -> data.text (body); concept -> data.subtitle (short); "
                "note -> data.text; area -> data.subtitle. There is no generic "
                "`data.body`. Call canvas_node_types for the full contract.\n"
                "A `spec` node is a TABLE, not prose: put tabular facts in "
                "`data.rows`, a list of {key, value, source_ref} objects, one "
                "row per fact. `source_ref` is {slug, page, bbox?, region_id?} "
                "grounding that row to its source page. Use `data.description` "
                "only for a short prose caption; do NOT pack multiple values "
                "into it -- rows render as a clean table and each row stays "
                "clickable back to its source, free text does not. "
                'Example for "list every pump ID and diameter": '
                '{"node_type": "spec", "label": "Pump diameters", "data": '
                '{"rows": [{"key": "P-101", "value": "150 mm", "source_ref": '
                '{"slug": "datasheet", "page": 3}}, {"key": "P-102", "value": '
                '"200 mm", "source_ref": {"slug": "datasheet", "page": 3}}]}}.'
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "node_type": {"type": "string", "description": "Canonical node type (e.g. 'fact', 'concept', 'spec')."},
                    "type": {"type": "string", "description": "Alias for node_type (back-compat with canvas-state JSON keys)."},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "place": {
                        "type": "string",
                        "enum": ["auto", "exact"],
                        "description": "'auto' (or omitting x/y) asks the server for a non-overlapping position, returned under `position`. 'exact' forces the given x/y.",
                    },
                    "parent": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_node_types",
            "description": (
                "List the per-node-type data-field contract: which `data` keys "
                "each built-in node type renders and which key is its visible "
                "body. Use this before add_node/update_node so you put the body "
                "in the right key (fact -> text, concept -> subtitle, ...) "
                "instead of a key that's silently dropped. Pass node_type to "
                "narrow to one. Each entry: {name, description, data_fields, "
                "body_field}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"node_type": {"type": "string"}},
            },
        },
        {
            "name": "canvas_update_node",
            "description": (
                "Update (edit / modify / patch) an existing node's label, "
                "position, parent, or content. "
                "The `data` field is DEEP-MERGED into the node's existing data: "
                "unmentioned keys (e.g. source_ref) are preserved, nested dicts "
                "merge recursively, and a key set to null is deleted. You no "
                "longer need to read-modify-write the whole dict to patch one "
                "field. Shape / "
                "card primitives honour `data.bg_color` and `data.stroke_color` "
                "(CSS colour strings, e.g. `#fef3c7`, `rgb(...)`); these tint "
                "the background and the border + label colour respectively. "
                "Producer primitives (spec / document / model3d / cad / sysml / "
                "fmu) ignore these fields — they ship their own style language."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "parent": {
                        "type": ["string", "null"],
                        "description": (
                            "Reparent the node onto another node (typically an "
                            "Area container). Pass `null` to detach. A pure-"
                            "parent patch emits `NodeReparented`; mixed with "
                            "other fields, the reparent still flows through the "
                            "dedicated command for invariant checking."
                        ),
                    },
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_remove_node",
            "description": "Delete a node by id (cascades connected edges).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_add_edge",
            "description": (
                "Explicitly wire two nodes. Use only when the user's main intent is "
                "to change wiring, relationships, provenance visualization, layout "
                "connections, or graph structure. Do not use for ordinary content "
                "updates; source_ref data is enough for grounding."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string"},
                    "edge_type": {"type": "string", "enum": ["floating", "anchored"]},
                    "type": {"type": "string", "enum": ["floating", "anchored"], "description": "Alias for edge_type (back-compat with canvas-state JSON keys)."},
                    "sourceHandle": {"type": "string"},
                    "targetHandle": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "source", "target"],
            },
        },
        {
            "name": "canvas_remove_edge",
            "description": "Delete an edge by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_update_edge",
            "description": (
                "Patch an existing edge's fields. Use only when the user's main "
                "intent is a wiring, routing, relationship, provenance-visualization, "
                "or graph-structure change."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "edge_type": {"type": "string", "enum": ["floating", "anchored"]},
                    "type": {"type": "string", "enum": ["floating", "anchored"], "description": "Alias for edge_type (back-compat with canvas-state JSON keys)."},
                    "sourceHandle": {"type": "string"},
                    "targetHandle": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_clear",
            "description": "Wipe the canvas (cards + edges).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_create_workspace",
            "description": "Create a new workspace folder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "canvas_delete_workspace",
            "description": (
                "Delete a workspace folder and its saved canvas state. "
                "Canvas-link nodes in other workspaces are not removed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_list_workspaces",
            "description": (
                "List all workspaces with node/edge counts and the canvas "
                "reference graph. Each entry: {slug, title, created_at, "
                "node_count, edge_count, references, referenced_by} where "
                "references are the slugs this canvas's `canvas`-typed nodes "
                "point at, and referenced_by is the reverse map. Use this to "
                "render a folder tree of nested canvases."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "canvas_organize_subtree",
            "description": (
                "Re-lay-out the subtree under root_id into a tidy tree. Emits one "
                "NodeMoved per descendant whose position changes; the root stays put. "
                "orientation = 'vertical' (default) or 'horizontal'. "
                "direction controls how the BFS walks edges: 'outgoing' "
                "(parent→child, follow arrows forward), 'incoming' (reports-to, "
                "follow arrows backward), or 'any' (undirected — default, "
                "preserves v1 behaviour). Pick 'incoming' on a reports-to org "
                "chart to scope strictly to subordinates."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "root_id": {"type": "string"},
                    "orientation": {
                        "type": "string",
                        "enum": ["vertical", "horizontal"],
                        "default": "vertical",
                    },
                    "algo": {
                        "type": "string",
                        "enum": ["dagre"],
                        "default": "dagre",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["outgoing", "incoming", "any"],
                        "default": "any",
                    },
                },
                "required": ["workspace_slug", "root_id"],
            },
        },
        {
            "name": "canvas_align",
            "description": (
                "Align the listed nodes' positions to a shared edge or midline. "
                "anchor = 'top' | 'bottom' | 'left' | 'right' | 'center-h' | "
                "'center-v'. Emits one NodeMoved per node that genuinely moves; "
                "all share a single causation_id so the SSE feed groups them."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                    },
                    "anchor": {
                        "type": "string",
                        "enum": ["top", "bottom", "left", "right", "center-h", "center-v"],
                        "default": "top",
                    },
                },
                "required": ["workspace_slug", "ids", "anchor"],
            },
        },
        {
            "name": "canvas_distribute",
            "description": (
                "Distribute the listed nodes' centres evenly along an axis. "
                "axis = 'horizontal' | 'vertical'. End nodes stay anchored; "
                "intermediate nodes get equally-spaced centres. Needs at "
                "least three ids."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                    },
                    "axis": {
                        "type": "string",
                        "enum": ["horizontal", "vertical"],
                        "default": "horizontal",
                    },
                },
                "required": ["workspace_slug", "ids", "axis"],
            },
        },
        {
            "name": "canvas_create_sub_canvas",
            "description": (
                "Create a child workspace and drop a 'canvas'-typed linking node "
                "onto the parent in one atomic step. Returns {child, node, event, "
                "state}. Use for hierarchical canvases — e.g. a top-level Plant "
                "canvas with sub-canvases for Pump loop / Heat exchanger."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_slug": {"type": "string"},
                    "slug": {"type": "string", "description": "Slug for the new child canvas."},
                    "title": {"type": "string"},
                    "x": {"type": "number", "default": 0},
                    "y": {"type": "number", "default": 0},
                },
                "required": ["parent_slug", "slug"],
            },
        },
        {
            "name": "canvas_list_placeholders",
            "description": (
                "List every node on the workspace flagged "
                "`data.placeholder == true`. Each entry: "
                "{id, node_type, label, hint, x, y, data}. `hint` mirrors "
                "`data.placeholder_hint` so you can pick the right doc "
                "lookup for each slot. Pair with `search_documents` / "
                "`get_gold_regions` and finish by calling "
                "`canvas_update_node` with the resolved value + a "
                "`source_ref` and `placeholder: false` in the data dict "
                "to clear the flag."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_create_reference",
            "description": (
                "Author a reference (citation) and add it to the canvas "
                "bibliography. Capture where a fact came from: `source_ref` is "
                "{slug, page, bbox?, region_id?, detail?} where detail can carry "
                "{quote, cell_bbox, match}. slug + page are required. `label` is "
                "a human caption (e.g. 'Max inlet pressure, LKH-5'); `created_by` "
                "is 'human' or 'agent' (default 'human' from the UI; pass 'agent' "
                "when you author it). Returns the stored reference with its "
                "server-assigned `id`. Attach it to a fact later with "
                "canvas_attach_reference."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "source_ref": {
                        "type": "object",
                        "description": "{slug, page, bbox?, region_id?, detail?}. slug + page required.",
                    },
                    "label": {"type": "string"},
                    "created_by": {
                        "type": "string",
                        "enum": ["human", "agent"],
                        "default": "agent",
                    },
                },
                "required": ["workspace_slug", "source_ref"],
            },
        },
        {
            "name": "canvas_list_references",
            "description": (
                "List the canvas bibliography (every reference authored on this "
                "workspace). Each entry: {id, label?, source_ref, created_by, "
                "created_at}. Use this to find a reference id to attach to a fact, "
                "or to compile a bibliography."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_remove_reference",
            "description": (
                "Remove a reference (citation) from the canvas bibliography. "
                "Pass the `reference_id` from canvas_list_references. Idempotent "
                "at the data level but errors on an unknown id so you notice a "
                "stale id. Does not detach the reference from any node/row it was "
                "attached to (that pointer is a cached copy)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "reference_id": {"type": "string"},
                },
                "required": ["workspace_slug", "reference_id"],
            },
        },
        {
            "name": "canvas_update_reference",
            "description": (
                "Edit a reference's human caption (`label`). Only the label is "
                "editable; the `source_ref` locator is immutable. Pass `label` "
                "= null to clear the caption. Use the `reference_id` from "
                "canvas_list_references."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "reference_id": {"type": "string"},
                    "label": {"type": ["string", "null"]},
                },
                "required": ["workspace_slug", "reference_id"],
            },
        },
        {
            "name": "canvas_attach_reference",
            "description": (
                "Attach a stored reference to a fact: a node (and optionally one "
                "spec row by `row_index`). Sets the target's `reference_id` "
                "pointer and copies the reference's `source_ref` onto it so the "
                "value resolves to its citation and drives the value-level "
                "highlight (yellow marker + source detail highlight). Pass the "
                "`reference_id` from canvas_create_reference / canvas_list_"
                "references and the target `node_id`."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "reference_id": {"type": "string"},
                    "node_id": {"type": "string"},
                    "row_index": {
                        "type": "integer",
                        "description": "Optional: target one row inside a spec node's data.rows.",
                    },
                },
                "required": ["workspace_slug", "reference_id", "node_id"],
            },
        },
        {
            "name": "canvas_snapshot",
            "description": (
                "Render a workspace canvas to PNG and return the bytes "
                "(as a path or base64). Use format='base64' from off-machine "
                "agents; same envelope as get_page_image / get_crop."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["path", "base64", "inline"],
                        "default": "inline",
                        "description": "'inline' renders the snapshot as an MCP ImageContent block so the host harness (Claude Code, Cursor, ...) displays it inline. 'path' returns the file path; 'base64' returns raw base64 inside the JSON envelope.",
                    },
                    "image_format": {"type": "string", "enum": ["png", "svg"], "default": "png"},
                    "viewport": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[width, height] in CSS pixels.",
                    },
                    "full_page": {"type": "boolean", "default": True},
                },
                "required": ["workspace_slug"],
            },
        },
    ]


NodeFieldsEnricher = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def call_tool(
    svc: WorkspaceService,
    name: str,
    args: dict[str, Any],
    *,
    enrich_node_fields: NodeFieldsEnricher | None = None,
) -> str:
    try:
        if name == "canvas_get_state":
            return json.dumps(await svc.get_state(args["workspace_slug"]))
        if name == "canvas_create_workspace":
            return json.dumps(await svc.create_workspace(args["slug"], title=args.get("title", "")))
        if name == "canvas_delete_workspace":
            return json.dumps(await svc.delete_workspace(args["workspace_slug"]))
        if name == "canvas_list_workspaces":
            return json.dumps(await svc.list_workspaces())
        if name == "canvas_add_node":
            slug = args.pop("workspace_slug")
            _alias_type(args, "node_type")
            place = args.pop("place", None)
            hint = _spec_rows_hint(args.get("node_type"), args.get("data"))
            warning = _data_warning(svc, args.get("node_type"), args.get("data"))
            state, env = await svc.add_node(slug, place=place, **args)
            result: dict[str, Any] = {"event": env.model_dump(), "state": state.get_state()}
            # Echo the resolved position so the agent can track layout (#189).
            result["position"] = {"x": env.payload.get("x"), "y": env.payload.get("y")}
            if hint is not None:
                result["hint"] = hint
            if warning is not None:
                result["warning"] = warning
            return json.dumps(result)
        if name == "canvas_node_types":
            return json.dumps(svc.node_types_schema(args.get("node_type")))
        if name == "canvas_update_node":
            slug = args.pop("workspace_slug")
            node_id = args.pop("id")
            data_patch = args.get("data") if isinstance(args.get("data"), dict) else None
            # `parent` is allowed to be explicitly None (means "unparent");
            # only strip the OTHER fields if they're None. The dispatcher
            # mirrors the HTTP route so HTTP / MCP / CLI behave identically.
            parent_present = "parent" in args
            parent_val = args.pop("parent", None)
            if parent_present and parent_val == node_id:
                return json.dumps({"error": "node cannot be its own parent"})
            fields = {k: v for k, v in args.items() if v is not None}
            if {"x", "y"} <= fields.keys() and len(fields) == 2 and not parent_present:
                state, env = await svc.move_node(slug, node_id, fields["x"], fields["y"])
            elif parent_present and not fields:
                state, env = await svc.reparent_node(slug, node_id, parent_val)
            else:
                if parent_present:
                    if enrich_node_fields:
                        fields = await enrich_node_fields(fields)
                    await svc.update_node(slug, node_id, fields)
                    state, env = await svc.reparent_node(slug, node_id, parent_val)
                else:
                    if not fields:
                        return json.dumps({"error": "nothing to update"})
                    if enrich_node_fields:
                        fields = await enrich_node_fields(fields)
                    state, env = await svc.update_node(slug, node_id, fields)
            result = {"event": env.model_dump(), "state": state.get_state()}
            if data_patch is not None:
                node = state.nodes.get(node_id)
                warning = _data_warning(
                    svc, node.node_type if node else None, data_patch,
                )
                if warning is not None:
                    result["warning"] = warning
            return json.dumps(result)
        if name == "canvas_remove_node":
            state, envelopes = await svc.remove_node(args["workspace_slug"], args["id"])
            return json.dumps({"events": [e.model_dump() for e in envelopes], "state": state.get_state()})
        if name == "canvas_add_edge":
            slug = args.pop("workspace_slug")
            _alias_type(args, "edge_type")
            state, env = await svc.add_edge(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_edge":
            state, env = await svc.remove_edge(args["workspace_slug"], args["id"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_edge":
            slug = args.pop("workspace_slug")
            edge_id = args.pop("id")
            _alias_type(args, "edge_type")
            fields = {k: v for k, v in args.items() if v is not None}
            state, env = await svc.update_edge(slug, edge_id, fields)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_clear":
            state, env = await svc.clear(args["workspace_slug"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_organize_subtree":
            try:
                state, envelopes = await svc.organize_subtree(
                    args["workspace_slug"], args["root_id"],
                    orientation=args.get("orientation", "vertical"),
                    algo=args.get("algo", "dagre"),
                    direction=args.get("direction", "any"),
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_align":
            try:
                state, envelopes = await svc.align_nodes(
                    args["workspace_slug"], list(args["ids"]), args["anchor"],
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_distribute":
            try:
                state, envelopes = await svc.distribute_nodes(
                    args["workspace_slug"], list(args["ids"]), args["axis"],
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_create_sub_canvas":
            return json.dumps(await svc.create_sub_canvas(
                args["parent_slug"], args["slug"],
                title=args.get("title", ""),
                x=float(args.get("x", 0.0)),
                y=float(args.get("y", 0.0)),
            ))
        if name == "canvas_list_placeholders":
            return json.dumps(await svc.list_placeholders(args["workspace_slug"]))
        if name == "canvas_create_reference":
            ref = await svc.create_reference(
                args["workspace_slug"],
                source_ref=args["source_ref"],
                label=args.get("label"),
                created_by=args.get("created_by", "agent"),
            )
            return json.dumps({"reference": ref})
        if name == "canvas_list_references":
            return json.dumps(await svc.list_references(args["workspace_slug"]))
        if name == "canvas_remove_reference":
            state, env = await svc.remove_reference(
                args["workspace_slug"], args["reference_id"],
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_reference":
            state, env = await svc.update_reference(
                args["workspace_slug"],
                args["reference_id"],
                label=args.get("label"),
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_attach_reference":
            state, env = await svc.attach_reference(
                args["workspace_slug"],
                args["reference_id"],
                node_id=args["node_id"],
                row_index=args.get("row_index"),
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_snapshot":
            envelope_fmt = args.get("format", "path")
            image_fmt = args.get("image_format", "png")
            viewport = args.get("viewport")
            if viewport is not None:
                viewport = (int(viewport[0]), int(viewport[1]))
            full_page = bool(args.get("full_page", True))
            try:
                result = await svc.snapshot(
                    args["workspace_slug"],
                    format=image_fmt,
                    viewport=viewport,
                    full_page=full_page,
                )
            except NotImplementedError as e:
                return json.dumps({"error": str(e)})
            except RuntimeError as e:
                return json.dumps({"error": str(e)})
            except ValueError as e:
                return json.dumps({"error": str(e)})
            return _byte_envelope_from_result(
                path=result.path, bytes_=result.bytes_,
                content_type=result.content_type, fmt=envelope_fmt,
            )
    except CommandError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
