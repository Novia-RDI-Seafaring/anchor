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
