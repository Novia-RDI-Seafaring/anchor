# Chart ingestion

Turn a chart printed in a datasheet (a pump curve, an efficiency map) into a
real `(x, y)` data series on the canvas, anchored to the page it came from.

This pipeline is the first worked example of an **external OIP producer**.
ANCHOR writes no chart-specific code. It discovers a conforming tool, briefs
the agent about it, and renders its output by token. The same path serves
any future producer that follows the standard.

## The pieces

| Repo | Role |
| --- | --- |
| [graph-data-extractor](https://github.com/NoviaIntSysGroup/graph-data-extractor) | The producer. Traces chart lines into data. Ships an OIP manifest, a `trace_series` MCP tool, and a `graph-tracer-trace` CLI. Installs without a GUI. |
| [OIP](https://github.com/Novia-RDI-Seafaring/OIP) | The contract. v0.3 adds region producers (`consumes`), derived regions (`derived_from`), and recognised `renders` tokens (`chart`). |
| anchor (this repo) | The consumer. Discovers the producer, folds its agent skill, and renders a `chart` region with `ChartPrimitive`. |

The tracing engine fuses ridge detection, colour similarity, and patch
embeddings, then connects a few seed waypoints into the full curve. The agent
places those seeds from the image; a human can place them by clicking instead.

## How it fits OIP

graph-data-extractor is an OIP **region producer**. It does not ingest a
source. It `consumes` a `chart` region another producer wrote (a chart image
with a `png` crop) and `produces` a `chart_series` region whose `renders`
hint is `chart`. The derived region keeps the parent chart's `source_ref`, so
the recovered series still points at the same page and bbox.

```
chart region (anchor_pdfs)            chart_series region (graph-tracer)
  kind: chart                           kind: chart_series
  source_ref: pdf-page-bbox  ──────▶    derived_from: <chart region id>
  content.png: crop.png                 source_ref: <copied from parent>
                                        content.data: { axes, series }
```

`content.data` is exactly the OIP `chart` token payload:

```json
{
  "x_label": "Q (m3/h)", "y_label": "H (m)",
  "x_scale": "linear", "y_scale": "linear",
  "series": [{ "label": "LKH-85", "points": [[0, 94], [150, 94], [400, 50]] }]
}
```

## Setup

Install the producer and register it so any OIP consumer can find it:

```bash
# in the graph-data-extractor checkout
uv run graph-tracer-oip-install --data-dir ~/anchor-data
```

This writes a manifest to `~/.config/oip/producers.d/graph-tracer.json`.
ANCHOR discovers it (`anchor extensions list`) and folds its agent skill into
the composed briefing, so a connected agent learns when and how to use it.

For the agent to call the tracer, register its MCP server in the same harness
that runs ANCHOR's:

```bash
claude mcp add graph-tracer -- uv run graph-tracer-mcp
```

The harness is the integration point. It holds both ANCHOR's tools and the
producer's tools, so the agent orchestrates across them. ANCHOR does not spawn
the producer itself.

## The flow (agent-driven)

1. Ingest the datasheet in ANCHOR. The PDF producer extracts regions; a chart
   region has `kind: chart` and a `png` crop.
2. Read the crop. `anchor get_crop` (or `get_page_image`) returns the image
   path. Inspect it.
3. Place calibration and seeds. Read two tick values per axis and their pixel
   positions; drop a few waypoints along each line. All in pixels.
4. Trace. Call `graphtracer.trace_series(image_path, request)`. It returns
   `{ axes, series }`.
5. Place it. Call `anchor canvas_add_node(node_type="chart", data={ chart:
   <result>, source_ref: <parent chart region's source_ref> })`. The node
   renders as a chart, with a chip that opens the source PDF at the page and
   bbox.

The node type registry is open, so `chart` needs no registration; the canvas
renders it through the `chart` token. Provenance is preserved end to end: the
chart on the canvas points back at the page region it was traced from.

## The human-click path

The same `chart` token and the same `ChartPrimitive` serve a human-driven
trace. Instead of the agent placing pixels, the user clicks the calibration
ticks and waypoints on the chart region in the canvas, and the same
`trace_series` request is sent. This path needs a canvas point-collection
mode (planned); the data contract and renderer are already shared.

## What is built, what is next

Built and verified:

- Producer: headless `trace_series` / `graph-tracer-trace`, OIP manifest +
  installer, Qt-free core install.
- Contract: OIP 0.3 `consumes` / `derived_from` / `chart` token (RFC 0001).
- Consumer: discovery + skill composition (no per-producer code), and the
  `chart` render token (`ChartPrimitive`) with source provenance.

Next:

- Durable gold persistence: store the `chart_series` region in the document's
  gold layer so it is searchable, not only a canvas node.
- Canvas point-collection for the human-click path.
- A generic "run a region producer on this region" helper, keyed on the
  manifest `consumes` / `produces`, reused by every future region producer.
