## Canvas tools — workspaces, nodes, edges

The canvas is the visible substrate humans and agents share. Each
workspace is an isolated folder under `canvases/`. Edits land in
real time on every connected client via SSE.

### Tools

- `canvas_create_workspace(slug, title?)` and `canvas_list_workspaces()`.
- `canvas_get_state(workspace_slug)` — full state for the workspace.
- `canvas_list_placeholders(workspace_slug)` — every node flagged
  `data.placeholder == true` with its `placeholder_hint`. The entry
  point when the user says "fill in the specs I marked".
- `canvas_add_node(workspace_slug, node_type, label, x, y, data?)`.
- `canvas_update_node(workspace_slug, id, ...)` and
  `canvas_remove_node(workspace_slug, id)`.
- `canvas_add_edge(workspace_slug, source, target, edge_type?, data?)`
  and `canvas_remove_edge(workspace_slug, id)`.
- `canvas_clear(workspace_slug)` — destructive; ask first.

### Picking a node type

| Node type | When to use |
| --- | --- |
| `document` | A whole PDF as a card on the canvas. |
| `spec` | A table of rows with values. Each row carries a `source_ref`. |
| `fact` | A free-form note tied to a source. |
| `image` | A region crop or screenshot. |
| `concept` / `entity` | Generic shapes for grouping or schematics. |
| `canvas` | A tile that links to a child canvas. |

The full list and the data shapes live in the on-disk substrate docs;
this is the shortlist of the ones agents touch most.
