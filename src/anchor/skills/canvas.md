## Canvas tools — workspaces, nodes, edges

The canvas is the visible substrate humans and agents share. Each
workspace is an isolated folder under `canvases/`. Edits land in
real time on every connected client via SSE.

### Tools

- `canvas_create_workspace(slug, title?)` and `canvas_list_workspaces()`.
- `canvas_get_state(workspace_slug)` — full state for the workspace.
- `canvas_changes(workspace_slug, since_version?)` — what changed after a
  version you last saw, one net entry per element grouped by actor. Call
  it to catch up on a canvas you worked on before instead of diffing two
  full states.
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
| `text` | Words with no box: a title, a caption, a paragraph. |
| `markdown` | Prose with structure — headings, lists, tables, code. `data.text` holds the Markdown source. |
| `concept` / `entity` | Generic shapes for grouping or schematics. |
| `canvas` | A tile that links to a child canvas. |

The full list and the data shapes live in the on-disk substrate docs;
this is the shortlist of the ones agents touch most.

### Say it in Markdown when it has structure

Most of what an agent writes onto a canvas is not one sentence. It is a
short list of findings, two options side by side, a snippet of a config,
a link back to where a number came from. That is a `markdown` node:
`data.text` holds the Markdown source and the card renders it as rich
text, with GitHub-flavoured tables and task lists.

Reach for it over a `note` as soon as the content has more than one
part. A `note` is a remark; a `markdown` card is an explanation. Values
that are really rows of a table still belong in a `spec` node, where
each row carries its own `source_ref` — a Markdown table of numbers
looks right and loses every link back to the page it came from.

Raw HTML in the source is escaped, never rendered.

### Point prose at its source with an `anchor:` link

A value quoted in a sentence can carry its provenance the same way a spec
row does. Write an ordinary Markdown link whose target is `anchor:`:

```markdown
Rated head is [24 m](anchor:lkh-5?page=3&region=r2) at 8 m3/h.
```

The card renders the words with an anchor glyph after them; clicking
opens that document at that page with the region highlighted. The query
maps onto `source_ref` field for field, including the selectors that
point below a region:

| Written | Points at |
| --- | --- |
| `anchor:<slug>?page=3` | the page |
| `anchor:<slug>?page=3&region=r2` | one gold region |
| `anchor:<slug>?page=3&item=p3-i0` | one silver item |
| `anchor:<slug>?page=3&cell=4,1` | one table cell |

A ref naming no document or no page renders struck through, so a pointer
you got wrong is visible rather than silently reading as sourced.

An inline ref is a pointer for whoever reads the card. It is **not** an
evidence edge. The edge is the reviewable claim that a value came from a
region, and rows of values still belong in a `spec` node where each row
carries its own `source_ref`. Use the link for prose that mentions a
source in passing; use an edge, or a spec row, when the relation itself
is the point. Doing both is fine.

### Review states

Some workspaces run in review mode (`metadata.review_mode == true`). In
those, every node you create is stamped `data.review = {state:
"proposed", by, at}` automatically — you do not set it yourself. Do not
set or change a node's `review` state unless the user asks you to. A
node with `review.state == "rejected"` is feedback: the human turned it
down, so revise or replace it rather than ignoring or deleting the
verdict. `accepted` means the human signed off. Evidence edges and
`source_ref` remain how a value is checked; `review` only records the
outcome of that check. A whole proposal set carries one verdict for every
element in it (see below).

### Group what you add, so a human reviews it as one thing

When you add more than a couple of elements in one go, draw them, then
call `canvas_propose_set(workspace_slug, reason, members)` to group them.
`reason` is shown to the reviewer: say what you added and why, in your own
words. Without a set, a human rules on thirty-five nodes one at a time and
nothing records which of them belong together.

Add more with `canvas_add_to_proposal_set`; re-adding a member is a no-op.
Check back with `canvas_list_proposal_sets(workspace_slug, state="open")`
to see what is still waiting, and read the verdict on a set you proposed
earlier: `rejected` is feedback, so revise rather than re-propose the same
thing. `canvas_review_proposal_set` is the human's verdict. Only call it
when the user asks you to.

A thread suggestion (`intent_add_item`) already is a batch and needs no
set: use a set for what you add outside a thread.

### Elements under a scoped ask are read-only to you

When an intent in your inbox carries `targets`, those elements belong to
a thread. Do not call `canvas_update_node` / `canvas_remove_node` /
`canvas_add_edge` on them. Stage the change as a `suggestion` item on
the thread instead (`intent_add_item`); the ops use the same payload
shapes as these tools. On approval the batch is applied with you as the
actor, and every element it creates lands with `data.review = {state:
"accepted", by: <the approver>}`.

### Make it readable at the zoom it will be read at

A `text` element is the one to reach for when the thing you are adding is
prose, a heading or a caption: it renders `data.text` alone, with no border
and no background, so an explanation does not arrive as one more card.

Every element honours `data.text_size`: `xs`, `sm`, `md` (default), `lg`,
`xl`, `2xl`, `3xl`. The heading grows with the body from `lg` up. A canvas
someone reads on a shared screen, or a headline you want legible zoomed
out, wants `xl` or larger with a wider `width`; a dense reference table
stays at the default. Pick the size when you create the element rather
than leaving everything at the default and making the human zoom.

### Spec nodes carry structured rows, not prose

When an extraction yields several values — say every pump ID and its
diameter — put them in `data.rows`, one row per fact. Each row is
`{key, value, source_ref}`, where `source_ref` is `{slug, page, bbox?,
region_id?, item_id?, cell?}` grounding that value to its source page.
The optional selectors point below the region: `item_id` names one
silver item (`p<page>-i<n>`, listed by `inspect_region` under
`members`), and `cell` is `{row, col}` of a table. Resolution
precedence is cell > item > region > bbox — `resolve_source_ref`
answers with the tightest stored bbox and names the layer that
resolved. Enriched spec rows record the matched cell automatically:
when a row's value matches one gold table cell, the row's ref gains
`cell: {row, col}` alongside the cached cell bbox. Rows render as a
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
