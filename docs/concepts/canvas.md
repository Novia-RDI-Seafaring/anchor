# The canvas

The canvas is the surface humans and agents share. Everything else in
v2 — the workspace aggregate, the event bus, the OIP producers, the
on-disk substrate — exists to make this one screen behave correctly.

## What you see

A blank canvas opens to a grid background, a small toolbar on the
left, and a status line at the bottom. There's no chrome around the
canvas itself — the workspace fills the viewport. Nodes are drawn as
cards or shapes; edges are lines between them. A node is dragged with
the mouse, resized with a corner handle, double-clicked to edit its
label, and connected to another node by dragging from a handle on its
border to a handle on another node's border.

The interaction vocabulary is small and deliberate. There is no
modal-mode, no tool palette to switch into, no context menu hierarchy
to memorise. A node is created by dragging from the left rail onto the
canvas; deleted with `Backspace`; selected with click; multi-selected
with shift-click or rubber-band drag. That is the whole input system.

## The workspace list

The first page is `CanvasListPage`. It shows every workspace as a card
with title, slug, last-modified time, and (eventually) a thumbnail
rendered server-side. Click one to open it; the URL becomes
`/c/<slug>` and React Router mounts `CanvasPage`, which mounts
`CanvasGraph(slug=...)`.

A workspace is the unit of portability. The folder
`data/canvases/<slug>/` is the entire state of one canvas. Copy that
folder to another machine, run `anchor serve --data-dir ./received`,
and the same canvas opens with the same nodes and edges. Documents
referenced from those nodes need to come along too — they live in
their producer's data folder, not in the canvas folder — but the two
substrates are independently transferable.

## Node types

The frontend ships **seven built-in node types** in
`web/src/canvas/nodes/`. They are intentionally generic. Anything more
specific (PDF documents with cover pages, FMU models with simulate
buttons, Recharts plots) is registered by an extension at runtime, not
baked in here.

| Type        | Shape          | Used for                                       |
| ----------- | -------------- | ---------------------------------------------- |
| `concept`   | rounded card   | the default — anything textual                 |
| `entity`    | circle         | a thing-of-substance — a product, a system     |
| `fact`      | small card     | a single assertion or observation              |
| `document`  | tall card with cover | an ingested source (PDF, audio, video, ...) |
| `spec`      | wide table     | a structured table of named values             |
| `area`      | dashed outline | a region that contains other nodes             |
| `note`      | sticky-note    | freeform markdown                              |

Each renderer is a separate `.tsx` file under `nodes/`; each registers
itself into a `registerCardType(name, component)` map at module load
time. A new renderer is one new file plus one `registerCardType` call.
The registry is a `Proxy`, so ReactFlow's `nodeTypes` lookup just
asks the registry without recompilation.

This is what makes extensions composable on the frontend. An OIP
producer's manifest can declare `pdf:document` as a node type with
`renders: "document with cover image and region overlay"`; the Anchor
extension that ships alongside that manifest registers a real React
component under the name `pdf:document`; the canvas core never has to
know about it.

## Edge types

Two:

- **`floating`** — automatic edge routing. The edge connects two nodes
  abstractly; ReactFlow picks the prettiest path. Use for loose
  associations, "X is related to Y."
- **`anchored`** — explicit handle-to-handle. The edge starts on a
  specific handle of node A and ends on a specific handle of node B.
  Used for row-level wiring (a spec-table row → an FMU parameter) and
  for evidence edges (a value on a card → its source region).

An anchored edge that carries a `source_ref` in its `data` field is an
**evidence edge** — it says "this value is grounded in this region of
this document." Today they render as straight lines; a future visual
treatment is to render those edges with an anchor glyph at the source endpoint
and a chain-link pattern along the stroke. The metaphor is already in
the code; the visual just doesn't lean into it yet.

## Live multi-client

The canvas is server-authoritative and optimistic-local. When you drag
a node, the local store updates the position immediately and renders
the next frame; in parallel the browser issues
`PATCH /api/workspaces/{slug}/nodes/{id}` with the new x,y; the server
emits a `NodeMoved` event; SSE delivers it back; the local
`applyEvent` runs idempotently because the event id matches a request
the client already issued. On a 4xx/5xx the optimistic write rolls
back and a toast surfaces.

Two tabs of the same workspace open in two browsers, an agent
connected over MCP, and the CLI all see each other's mutations within
~50ms. There's no separate sync layer — they all subscribe to the
same `EventBus` via SSE or MCP `notifications/resources/updated`.

If the network blips, `EventSource` reconnects automatically; the
client requests a snapshot, compares versions, and resumes streaming.
The reconnection is invisible to the user.

## Drop-to-ingest

Drag a PDF (or any file whose MIME type is claimed by an OIP
producer) onto the canvas. A placeholder `document` node appears at
the drop position with a status diamond on its corner. The browser
POSTs the file to `/api/workspaces/{slug}/upload`; the server routes
it to the producer that claims its source kind (`anchor_pdfs` for
PDFs); the producer streams `IngestProgress` events back over SSE;
the placeholder updates as the pipeline moves through bronze →
silver → gold. When `DocIngested` fires, the placeholder is replaced
with a real document node — cover image rendered, region overlay
ready, evidence edges available.

The same mechanism works for FMU files (the `anchor_fmus` producer
claims `application/x-fmu`) and will work for any future producer
that declares the MIME type in its OIP manifest. The canvas core
doesn't change; the dropped file just lands at a producer that knows
what to do with it.

## Selection, parenting, areas

A selected node has a thin border and a small toolbar above it
(rename, duplicate, delete). Multi-selection works with shift-click
and rubber-band; multi-selected nodes drag together.

`area` nodes are **containers**. Drop a node onto an area and the
node's `parent` field updates to the area's id; the move is
constrained to the area's bounds (or the area grows). Removing a node
from an area is a drag out of its bounds. This is the only nesting
the canvas supports.

There is no z-order management. The canvas is structurally flat
except for parenting; `area` nodes always render below their
children.

## Layouts

`Cmd-Shift-L` runs a one-shot dagre layout over the current selection
(or the whole canvas if nothing is selected). It's deliberately a
one-shot, not a continuous force-directed simulation — the user moves
nodes deliberately and a continuous layout would fight them. There's
also no auto-layout on add. New nodes land where they were dropped or
where the toolbar inserts them.

## Why the canvas is small

`CanvasGraph.tsx` is 131 lines. `CanvasPage.tsx` is 22. `CanvasListPage.tsx`
is 79. The state lives in a Zustand store; server data lives in
TanStack Query; ReactFlow handles the rendering. The canvas component
itself is a wiring layer — it subscribes to SSE, applies events to the
store, hands ReactFlow a `nodes[]` and `edges[]` derived from the
store, and forwards `onNodesChange` / `onConnect` callbacks back to
HTTP mutations.

The old pre-refactor `CanvasGraph.tsx` was 1751 lines. The shrinkage
isn't because we removed features — it's because the features that
*were* in `CanvasGraph` belonged elsewhere. Node-specific rendering
moved into `nodes/`; layout moved into a utility module; the PDF
viewer moved into its own component; sync moved out into the SSE
client. What's left is the wiring.

## What it isn't

- **Not a whiteboard.** There are no freehand strokes, no images on
  the background, no comment threads. Things on the canvas are
  structured nodes with provenance.
- **Not a presentation tool.** No slides, no animations, no zoom
  paths.
- **Not a graph database UI.** The canvas doesn't render the entire
  knowledge graph; it renders one workspace's chosen view of it. A
  document can appear on a hundred canvases or none.
- **Not committed to ReactFlow forever.** The renderer is one
  dependency; the workspace state, events, and sync don't know about
  it. Swapping in a different rendering layer is a contained change.
