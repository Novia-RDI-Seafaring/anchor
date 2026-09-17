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
| `area` | A dashed container that encloses other nodes. The grouping primitive: name a step or a theme and put its cards inside. |
| `concept` / `entity` | Small labelled shapes for schematics. NOT containers. |
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

The link works in every text-bearing element, not only in `markdown`:
`text`, `fact` and `note` render `anchor:` links the same way. They do
not render the rest of Markdown -- `**bold**` stays asterisks in a
`fact` -- so pick `markdown` when the content needs formatting and any
card you like when it just needs to point at its source. There is no
element where a claim has to go unanchored.

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

### Two different jobs, two different canvases

A canvas is used for two things, and they do not look alike.

One is a **place to keep what a document says**: a document card, spec
tables, crops, evidence edges. The layout barely matters because the
value is in the grounding.

The other is **a case somebody has to act on**: which pump, which
material, is this design within limits. Here the layout IS the answer.
The reader wants to know what was asked, what the options were, what you
picked and what is still unresolved, in that order. Extracted values are
the supporting evidence, not the point.

The failure mode is answering the second with the first: every table you
extracted, dropped on an empty board. Everything is present and nothing
is legible. If the user asked a question rather than asked you to pull
data, compose the answer.

### Compose it so it can be read

**Enclose, do not merely place.** Proximity is a weak grouping cue and a
freeform board has no reading order of its own. Put each step of the
argument in an `area` with a `label` and a one-line `subtitle`, and place
its cards inside. A reader then sees the shape of the answer before
reading a single card.

**Say the reading order out loud.** A `text` element at `text_size` `xl`
or `2xl` across the top, with a `sm` line under it naming the order and
any colour convention you used ("read left to right: what we need, what
fits, what we chose, what is still open"). A canvas that has to be
deciphered costs more than the prose it replaced.

**Let colour carry state, not decoration.** Colour and size register
before any text is read, so spend them on the one distinction that
matters. Pick a convention, state it in the subtitle line, and hold it
for the whole canvas. `data.bg_color` and `data.stroke_color` take CSS
colours and every node type accepts them. A convention that works:
given facts in one colour, assumptions you made in another, the decision
in a third, rejected options greyed. What matters is that it is
consistent and declared, not which hues you choose.

**Make the answer the biggest thing.** One card should be visibly the
conclusion: larger `text_size`, a wider `width`, its own colour. If a
reader zooms out and cannot tell what you concluded, the canvas failed
regardless of how good the evidence under it is.

**Say what you rejected.** An option considered and dropped, with the
reason, is worth a card. It stops the reader re-asking the question you
already answered, and it is the part a reviewer most needs in order to
disagree with you.

**Label the edges that carry reasoning.** An evidence edge says where a
value came from. An edge between steps of an argument should say why it
leads there ("fails at 5 m", "passes with margin"). An unlabelled edge
between two claims is a line, not an argument.

**Mark what you assumed.** Anything you filled in yourself, rather than
read out of a document, is the first thing the human must check. Give
assumptions their own colour and put them where they will be seen, not
in a footnote.

### A decision canvas, worked

Four areas, a title, and the conclusion standing out. Positions are the
top-left corner of each element; children sit inside their area's box.

```json
[
  {"node_type": "text", "label": "", "x": 40, "y": 0,
   "data": {"text": "Pump selection - 5 m lift, continuous, indoor", "text_size": "2xl", "width": 900}},
  {"node_type": "text", "label": "", "x": 40, "y": 60,
   "data": {"text": "Read left to right. Blue = given, amber = assumed, green = decided.", "text_size": "sm", "width": 900}},

  {"node_type": "area", "label": "1. Requirements", "x": 40, "y": 120,
   "data": {"subtitle": "Duty point and site constraints", "width": 320, "height": 480}},
  {"node_type": "fact", "label": "R1 - Static lift 5 m", "x": 70, "y": 180,
   "data": {"text": "Given. Basin to top of waterfall.", "bg_color": "#dbeafe"}},
  {"node_type": "fact", "label": "R4 - Flow 15-30 m3/h", "x": 70, "y": 280,
   "data": {"text": "ASSUMED for a 1 m wide sheet. Confirm.", "bg_color": "#fef3c7"}},

  {"node_type": "area", "label": "2. Screening", "x": 400, "y": 120,
   "data": {"subtitle": "Which sizes can do it", "width": 380, "height": 480}},
  {"node_type": "spec", "label": "Screening at 5 m head", "x": 430, "y": 180,
   "data": {"rows": [
     {"key": "LKH-10", "value": "PASS - 17 m3/h", "source_ref": {"slug": "lkh", "page": 4, "region_id": "r1"}},
     {"key": "LKH-5", "value": "FAIL - shut-off too low", "source_ref": {"slug": "lkh", "page": 4, "region_id": "r1"}}
   ]}},

  {"node_type": "area", "label": "3. Decision", "x": 820, "y": 120,
   "data": {"subtitle": "Selected pump", "width": 380, "height": 480}},
  {"node_type": "fact", "label": "DECISION - LKH-10, 4-pole", "x": 850, "y": 180,
   "data": {"text": "17 m3/h at 5 m. Shut-off 9 m: margin over duty.",
            "bg_color": "#dcfce7", "text_size": "lg", "width": 320}},
  {"node_type": "fact", "label": "Rejected - LKH-5", "x": 850, "y": 330,
   "data": {"text": "Only reaches 5 m at run-out.", "bg_color": "#f1f5f9"}},

  {"node_type": "area", "label": "4. Open before ordering", "x": 1240, "y": 120,
   "data": {"subtitle": "Confirm these, then order", "width": 340, "height": 480}},
  {"node_type": "fact", "label": "1 - Confirm the flow", "x": 1270, "y": 180,
   "data": {"text": "Waterfall width decides LKH-10 vs LKH-20.", "bg_color": "#fef3c7"}}
]
```

Then edges: evidence edges from each `spec` back to the document card,
and labelled edges between the areas' key cards carrying the reasoning
("fails at 5 m", "passes with margin"). Finish with
`canvas_propose_set` so the human rules on the answer as one thing.

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
