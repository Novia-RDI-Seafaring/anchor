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

### Spec nodes carry structured rows, not prose

When an extraction yields several values — say every pump ID and its
diameter — put them in `data.rows`, one row per fact. Each row is
`{key, value, source_ref}`, where `source_ref` is `{slug, page, bbox?,
region_id?}` grounding that value to its source page. Rows render as a
clean table on the canvas, and every row stays clickable back to the
page it came from.

Do NOT pack those values into `data.description`. The description is a
short prose caption only; a multi-value answer dumped there shows up as
one blob of text with no per-value provenance and no table view.

```json
{
  "node_type": "spec",
  "label": "Pump diameters",
  "data": {
    "rows": [
      {"key": "P-101", "value": "150 mm", "source_ref": {"slug": "datasheet", "page": 3}},
      {"key": "P-102", "value": "200 mm", "source_ref": {"slug": "datasheet", "page": 3}}
    ]
  }
}
```

`canvas_add_node` returns a non-fatal `hint` when a `spec` node is
created with a `description` but no `rows` — a reminder to move tabular
facts into rows. The write still succeeds; prose-only specs are allowed.
