# The canvas

The canvas holds the objects you and your agent work on: document cards,
specification tables, notes, shapes, and engineering objects. It belongs to a
project and uses that project's document corpus.

## Open and navigate

Start `anchor serve` for the desired environment and project, open the printed
URL, and choose a canvas. A canvas URL ends with `/c/<slug>`. One server serves
one project; the same canvas slug can exist in another project.

Use the left rail to place cards and shapes, add producer files, or enter the
mark-up tool. The files explorer and source dock sit beside the canvas and can
be toggled with `[` when you are not typing. Select a node for its context
toolbar and properties, drag to move it, and use handles where supported for
resizing or connections. Shift-click or a selection box selects several objects.

## Common objects

| Node type | Purpose |
| --- | --- |
| `document` | Card for a PDF in the project corpus |
| `spec` | Related parameters or specifications, with one source reference per row |
| `markdown` | Structured prose, lists, tables, and code |
| `fact`, `concept`, `entity` | General knowledge cards or shapes |
| `area` | Container for related canvas objects |
| `canvas` | Tile linking to another canvas |
| `cad:model` | CAD model view and supported parameter operations |
| `fmu` | FMU model with variables and simulation controls when its runtime is available |

Other shapes and producer objects are registered by the browser and bundled
extensions. Renderers live under `web/src/canvas/primitives/` and
`web/src/canvas/shapes/`; `web/src/canvas/registry.ts` maps node types to them.
Use `anchor canvas node-types` or MCP `canvas_node_types` for the live data-field
contract rather than inventing a field the renderer does not use.

## Tables and source evidence

Keep related extracted values in one spec table. Each row has a `key`, `value`,
and optional `source_ref`. A PDF source can name the document slug, one-based
page, region/item/cell selectors, or an explicit bounding box. Boxes use PDF
points, a top-left origin, and `[left, top, right, bottom]`.

Click a row's source anchor to open the PDF dock. It highlights a precise
locator when one resolves, or opens the cited page otherwise. Selecting source
text can attach a more precise box. A source link makes the claim inspectable;
it does not confer Verified status by itself.

Rows distinguish Verified, Unverified, Stale, and No evidence. Editing a claim
can preserve the link while making its binding stale. Use **Check** to request
revalidation against stored evidence. See [Claim and evidence](claim-evidence.md)
and [Source resolution](spec-source-resolution.md).

## Headings, folding, and details

Choose **Heading** from the shape palette to place a section label. It creates
a `concept` with `data.role: "heading"`: a large label and optional subtitle,
without the card border or body. Select an existing concept and choose
**Appearance > Heading** in its properties to give it the same presentation.

A node with children has a collapse button above it. Folding hides descendants
and every edge touching a hidden node. The folded root stays visible, including
its own evidence link, and its `+4` badge counts the descendants currently hidden.
Expand to restore their saved positions. A shared child stays visible if another
visible, expanded parent reaches it. Cycles are visited once, and a cyclic
component keeps an expand affordance.

Folding follows structural edges and area containment. **Child direction** in
properties uses the organizer's outgoing, incoming, or any direction convention;
the default is outgoing. Edge labels such as `contains` and `part_of` do not
change that direction. Evidence edges never make the source document a child
of a fact. A document card additionally treats incoming evidence dependents as
children, so it can fold its sourced claims.

Fact, note, Markdown, and spec cards default to **Compact**: the label and first
line or row count. Double-click a compact card, or select any node and choose
**Details**, to read the complete content, rows, source references and crops,
evidence links, stored review record, and requests that target it. Source actions
open the document viewer at the resolved page. Region/item references without a
page are resolved before opening; an unavailable source keeps its reference
visible. Document cards retain double-click to open the PDF, and sub-canvas
tiles retain double-click to navigate. Their **Details** action is separate.

Choose **Display > Full** to keep one important card or table expanded on the
canvas. Full tables retain their inline row editing and source anchors. The
detail view also offers **Edit properties** for the existing editing panel.
Read-only canvases allow detail reading and source opening without editing.

These settings are ordinary persisted node data. HTTP node patches, MCP
`canvas_add_node` / `canvas_update_node`, and CLI `anchor canvas add-node` /
`anchor canvas update-node` all use the same fields:

```json
{
  "collapsed": true,
  "collapse_direction": "outgoing",
  "role": "heading"
}
```

Use `data.display_mode: "compact"` or `"full"` on a card. Every viewer reads
the same persisted fold. `canvas_get_state` and CLI canvas state still return
all nodes, edges, source data, and positions; folding only filters rendering.

## Requests and review

Use **mark up** (`i`) to add text and drawings about visible objects. Click
**send to agent** to create a persistent project-level intent. A connected
external agent must retrieve and handle it; an empty placeholder does not submit
an ask. The remark stays on the board with its request thread.

The agent can ask a question or stage a suggested edit. Inspect the preview and
approve, decline, or send feedback. Applied small changes may offer keep/revert
controls. These are scoped to the thread change, not a general undo history.
Canvas review mode and proposal sets support review of agent-added elements
separately. See the [tutorial](../getting-started/tutorial.md).

## PDF upload

Drop a PDF on the canvas or use **+ > PDF datasheet**. A card shows its processing
status. With `local` or an endpoint-backed provider, the server runs the built-in
pipeline. With `harness`, it saves the PDF and queues a `drop_to_ingest` intent;
the card stays **awaiting agent** until the harness completes the session.

CLI ingestion writes the corpus without adding a canvas card. Drag a document
from the files explorer onto the canvas to place it. See
[Documents and canvases](../guides/documents-and-canvases.md).

## Edges and organization

Floating edges connect nodes. Anchored edges name explicit handles, allowing
row-level wiring and evidence connections. Area nodes can contain child nodes;
sub-canvas tiles link to another workspace. Layout operations include alignment,
distribution, and subtree organization. CLI/MCP add operations can auto-place
nodes when coordinates are omitted; explicit coordinates preserve a chosen layout.

FMU nodes remain separate from extracted knowledge. Inspect a model and wire
table rows to appropriate parameters deliberately. Simulation needs the optional
runtime; explicitly enabled demo output is synthetic.

## Persistence and live updates

Each canvas has metadata, state, and an append-only event log under
`.anchor_data/canvases/<slug>/`. Documents remain in the project's separate
corpus folders. Deleting a canvas does not delete those documents. Copy the whole
project for a backup that includes its source evidence and intent threads.

The browser sends writes through HTTP and receives snapshots and patches over
SSE. The HTTP process also tails canvas events persisted by CLI and MCP writers.
Local optimistic edits are reconciled against server state. If views disagree,
check project selection and re-read or reload the persisted state.

There is no fixed latency guarantee. Write locks and event buses are process-local;
avoid simultaneous mutations to the same canvas from separate processes.
