"""Declarative MCP tool catalog for canvas operations."""

from __future__ import annotations

from typing import Any


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
                "a non-overlapping spot and returns it under `position` - the "
                "preferred way to scaffold many nodes without piling them up. "
                "Pass explicit x/y to place exactly there.\n"
                "node_type is canonical; `type` is accepted as an alias so you "
                "can write back the `node_type` you read from canvas state.\n"
                "DATA FIELDS render per node_type - a key the renderer ignores "
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
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "place": {
                        "type": "string",
                        "enum": ["auto", "exact"],
                        "description": "'auto' (or omitting x/y) asks the server for a non-overlapping position, returned under `position`. 'exact' forces the given x/y.",
                    },
                    "parent": {"type": "string"},
                    "locked": {"type": "boolean"},
                    "visible": {"type": "boolean"},
                    "layer": {"type": "string", "enum": ["background", "content", "annotation"]},
                    "opacity": {"type": "number"},
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
                "fmu) ignore these fields - they ship their own style language."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
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
                    "locked": {"type": "boolean"},
                    "visible": {"type": "boolean"},
                    "layer": {"type": "string", "enum": ["background", "content", "annotation"]},
                    "opacity": {"type": "number"},
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
                "(parent->child, follow arrows forward), 'incoming' (reports-to, "
                "follow arrows backward), or 'any' (undirected - default, "
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
                "state}. Use for hierarchical canvases - e.g. a top-level Plant "
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
