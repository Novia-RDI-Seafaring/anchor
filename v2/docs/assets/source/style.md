# Anchor architecture diagram — visual style spec

This file is the **style** counterpart to `architecture.mmd` (which holds the
**structure**). Use both in tandem when generating, redrawing, or
print-preparing the architecture illustration. Edit them independently — they
should never drift.

Generation prompts should reference both files explicitly:
> "Use `architecture.mmd` as the structural ground truth (nodes, arrows,
> arrangement) and `style.md` as the visual ground truth (palette,
> typography, line weight, iconography, future-state treatment)."

---

## Aspect ratio

- 16:9 landscape
- Editorial / poster quality, generous whitespace

---

## Colour mode (v7+)

**Monochrome only.** The diagram is rendered as a charcoal-on-white line
drawing so a pure colour-inversion at print time produces the desired
white-on-black poster output.

| Role | Hex | Used for |
|------|-----|----------|
| Charcoal | `#1F2937` | All lines, arrows, fills, primary text |
| Background | `#FFFFFF` (pure white) | Canvas |
| (Optional) Mid grey | `#9CA3AF` | Decorative ellipsis only — use sparingly |

**Forbidden:**
- No colour fills (no sage green, no terracotta, no dusty blue, no amber).
- No gradients, no glows, no tinted shadows, no soft drop shadows.
- No anti-aliased halos that could read oddly under colour-inversion.

**Emphasis** comes from line weight and fill density, NOT colour:
- Heavier stroke or solid black fill on a label = primary emphasis.
- Outline-only with thinner descriptor = secondary.
- Dashed outline = future state.

> Older versions (v1–v6) used a 6-colour palette. v7 onward is strictly
> monochrome. Do not reintroduce colour without an explicit revision.

---

## Line weight

- Single uniform stroke weight, ~1.5px equivalent at 2K render
- All borders, arrows, and icon strokes use the same weight
- Arrowheads: small, filled triangles in charcoal

---

## Typography (v7+)

Strict two-family discipline — only these, nothing decorative:

| Use | Family | Weight | Case |
|-----|--------|--------|------|
| Title, section headings, panel labels, producer/consumer names | Geometric sans-serif (Montserrat-style) | Bold | UPPERCASE, tracking-wide |
| Descriptors / sub-labels (italic) | Humanist sans-serif (Open Sans-style) | Regular | Mixed case, italic |

Reference list of headings to set in **Montserrat-style bold uppercase
tracking-wide**: `ANCHOR ARCHITECTURE`, `SOURCE FILES`, `PRODUCERS`,
`DURABLE`, `CORE`, `INFRA`, `ADAPTERS`, `CONSUMERS`, plus primary node
labels `PDF`, `FMU`, `CAD`, `DOCUMENTS`, `CANVASES`, `BUS`, `MONITOR`,
`UI`, `AGENTS`, `VOICE`, `XR`.

Reference list of descriptors to set in **Open Sans-style italic regular**:
`datasheet, leaflet`, `simulation model`, `STEP, future`, `OIP producer`,
`future producer`, `per producer`, `data/<producer>/...`, `per workspace`,
`in-memory pub/sub`, `HTTP · MCP · CLI · SSE`, `FsStores · MemoryBus`,
`WorkspaceService · DomainEvent · Reducer`, `headless monitor, today`,
`visual canvas, today`, `external agents, Claude Cursor`, `voice interface,
future`, `XR Omniverse, future`.

**Section labels** (`SOURCE FILES`, `PRODUCERS`, `DURABLE`, `CENTRAL
HEXAGONAL STACK`, `CONSUMERS`, plus the title `ANCHOR ARCHITECTURE`) MUST
be set in **full uppercase, tracking-wide** geometric sans-serif. The title
takes no surrounding quotation marks of any kind — no straight quotes
(`'…'`), no curly quotes (`'…'`), no guillemets. Just the bare words.

When prompting an image model, phrase it as:
> *"geometric sans-serif (Montserrat-style) for uppercase section labels,
> humanist sans-serif (Open Sans-style) italic for descriptive text"*.

Even if the model approximates the fonts, the visual language should read
consistently — geometric/structural for headings, humanist/warm for
descriptors.

Plain inline text — **NO brackets, NO markdown, NO square brackets** around
descriptors. Descriptor sits directly under (or beside) the primary label,
same column.

---

## Iconography (v7+)

In v7 every primary node — including SOURCE FILES, DOCUMENTS, CANVASES, and
all CONSUMERS — is rendered as a charcoal **line pictogram on white**. There
are no surrounding rectangle "cards" with coloured fills; the icon plus
label IS the card.

| Node | Pictogram |
|------|-----------|
| **PDF** (source) | Stylized document outline with a folded top-right corner, two short horizontal text lines inside |
| **FMU** (source) | Tiny block-diagram icon — two small rectangles connected by an arrow (signals a simulation model) |
| **CAD** (source, future) | Wireframe cube with **dashed** outline |
| **P&ID** (source, future) | Process schematic glyph — two small instrument circles connected by a short pipe segment, with a tiny valve bowtie or pump circle on the line. **Dashed** outline |
| **anchor_pdfs / anchor_fmus / anchor_cad / anchor_pids** (producers) | Small hexagonal/tag-shaped badge, charcoal outline, white fill. `anchor_cad` and `anchor_pids` use a dashed outline. Optional `…` ellipsis below the column |
| **DOCUMENTS** | Stack-of-pages glyph (3 overlapping page rectangles with text lines) |
| **CANVASES** | Graph-of-nodes glyph (3 small circles connected by lines, inside a small frame) |
| **BUS** (inside hexagon) | Small rounded-rectangle pill with a tiny pair of stacked sine waves |
| **MONITOR** (consumer) | Bar chart with trend line inside a frame. Solid outline (today) |
| **UI** (consumer) | Browser / panel window with a small node-graph inside. Solid (today) |
| **AGENTS** (consumer) | Chat speech bubble. Solid (today) |
| **VOICE** (consumer, future) | Stand microphone (classic shape). **Dashed** outline |
| **XR** (consumer, future) | VR head-mounted display goggles — NOT headphones, NOT earbuds. **Dashed** outline |

All pictograms share the same uniform 1.5px-equivalent line weight and
charcoal colour. No fills (white interior). The PRODUCERS row may keep
small badge outlines if pictograms feel forced.

---

## Future-state styling (v7+)

With colour gone, the future/today distinction is carried purely by stroke
style:

- **Today** (MONITOR, UI, AGENTS, anchor_pdfs, anchor_fmus): SOLID charcoal
  outline.
- **Future** (VOICE, XR, anchor_cad, CAD source, anchor_pids, P&ID source):
  **DASHED** charcoal outline, same line weight, dash pattern ~6px on /
  4px off. Text stays full opacity for legibility.

Do **not** combine dashing with desaturation or grey tones — there is no
colour to desaturate, dashed-vs-solid is the entire signal.

**MONITOR is the minimal common denominator.** A headless monitor is just a
process subscribed to the SSE stream — five lines of `EventSource` Python or
`curl` is enough. Every other consumer is `MONITOR + extra capability`:

- UI = MONITOR + visual rendering + user input
- AGENTS = MONITOR + LLM reasoning + tool calls back
- VOICE = MONITOR + audio I/O + speech-to-text
- XR = MONITOR + 3D rendering + spatial input

So MONITOR sits in the **today / solid** group with UI and AGENTS. Only
VOICE and XR remain dashed/future.

> **Note on captions (v10+):** the colloquial caption *"MONITOR is the
> minimal common denominator — every other consumer is MONITOR + extra
> capability."* is **NOT** drawn on the diagram. The framing is technically
> imprecise (voice/UI also send commands, not just receive), and the
> bottom-right corner is intentionally left empty for breathing room. The
> OIP legend stays in the bottom-left.

---

## No depth tricks

- No drop shadows
- No soft shadows under blocks
- No gradients
- No 3D perspective
- No isometric / axonometric projection
- No inner glows or highlights
- No anti-aliased halos that could look weird after colour-inversion

Pure flat line work on white. The diagram is a 2D top-down schematic, not
an illustration with depth.

---

## Connection rules

These are architectural invariants — the visual must respect them:

1. **Consumers connect to ADAPTERS, not to BUS or CORE.**
   - Each consumer has ONE **double-headed** arrow to the outer ADAPTERS
     hexagon ring (commands flow in, events flow out — implied by direction,
     not labelled twice).
   - **Single-word labels only**: pick `HTTP`, `MCP`, `SSE`, or no label at
     all. Never write multi-token strings like "commands HTTP/MCP" or
     "events SSE/MCP notif" on consumer arrows. Let layout carry the
     semantics.
2. **BUS lives ONLY inside the hexagon.** It sits between CORE and ADAPTERS,
   visualised as a small rounded-rectangle pill inside the hexagonal stack
   (between the INFRA ring and the CORE centre). Give it **comfortable
   padding** from CORE — never jam BUS against the CORE label.
3. **CORE → BUS** (label `publish`), **BUS → ADAPTERS** (label
   `subscribe`) — small internal arrows show the publish/subscribe pump
   inside the hexagon.
4. **Producer pipeline:** `SOURCE FILE → PRODUCER → DOCUMENTS`, with the
   arrow from `PRODUCER → DOCUMENTS` labelled `OIP`. **Producers are not
   inside the hexagon.** They sit between input source files (left edge of
   the diagram) and the `DOCUMENTS` substrate, written *into* DOCS via the
   OIP contract. Anchor core then reads from DOCS.
5. **DOCUMENTS → CORE**: a single solid arrow with **NO label**. Do not
   invent a `read` label here — the structure source has none.
6. **CANVASES ↔ CORE / ADAPTERS**: bidirectional.
   - `events.jsonl` label sits on the CANVASES → CORE segment.
   - `snapshot.json` label sits on the CORE → CANVASES segment.
   - **Both labels must have breathing room** — spaced along the arrow,
     never overlapping the CANVASES pictogram.
7. **CAD producer** stays on the same edge of the hexagon as PDF and FMU,
   but rendered with the future-state treatment (dashed outline). It must
   not float outside the column — align it with the others.

---

## OIP placement

OIP is the contract every producer must satisfy when writing into the
`DOCUMENTS` substrate. As of v5 it lives on the producer→DOCS edge:

- **Canonical:** edge labels on each `PRODUCER → DOCUMENTS` arrow read
  simply `OIP`. The label sits on the arrow itself.
- The producers are positioned between the source files (left edge) and
  the `DOCUMENTS` substrate, so the OIP label visually reinforces that the
  protocol is the boundary on the *producer-to-storage* hop, not on the
  consumer side.

Do not also draw a separate `OIP 0.1` pill or an italic floating `OIP`
above DOCS — one canonical placement is enough.

---

## Legends / footnotes

- **OIP acronym definition (v9+):** in the bottom-left empty corner near the
  producer column's `…` ellipsis, set a small two-line footnote — line 1
  `OIP — Open Ingestion Protocol` (acronym geometric-bold, expansion
  humanist italic), line 2 `vendor-neutral spec at
  github.com/Novia-RDI-Seafaring/OIP` (humanist italic). Subtle text-near-
  the-edge, NOT a boxed callout, same charcoal-on-cream as the rest of the
  diagram, comparable in weight to the MONITOR caption on the right.

---

## Layout (left to right)

1. **Far-left column — source files** (line pictograms on white, charcoal):
   - `PDF` (folded-corner document) + italic `datasheet, leaflet`
   - `FMU` (two-block diagram with arrow) + italic `simulation model`
   - `CAD` (wireframe cube, dashed) + italic `STEP, future`
   - `P&ID` (process schematic — instrument circles + pipe + valve, dashed)
     + italic `schematic, future`

2. **Producers column** (small hexagonal/tag badges, charcoal outline,
   white fill — between source files and DOCS):
   - `anchor_pdfs OIP producer` (solid)
   - `anchor_fmus OIP producer` (solid)
   - `anchor_cad future` (dashed)
   - `anchor_pids future producer` (dashed)
   - Optional `…` ellipsis under the column to imply "more producers
     possible" (e.g. `anchor_sysml`, `anchor_step`)
   - Each producer receives an arrow from its source pictogram on the left
     and emits an arrow into `DOCUMENTS` on the right, labelled `OIP` on
     the producer→DOCS edge.

3. **Middle-left column — durable substrate** (line pictograms, no
   coloured rectangles):
   - `DURABLE on disk` header containing a stack-of-pages `DOCUMENTS`
     glyph and a graph-of-nodes `CANVASES` glyph. There is **no SESSION
     slab** on the left — BUS is shown only inside the hexagon.

4. **Centre — hexagonal stack** (concentric, flat charcoal outlines on
   white, no shadows):
   - Outer hexagon `ADAPTERS` (italic `HTTP · MCP · CLI · SSE`)
   - Middle hexagon `INFRA` (italic `FsStores · MemoryBus`)
   - Inner hexagon `CORE` (italic `WorkspaceService · DomainEvent ·
     Reducer`)
   - Small `BUS in-memory pub/sub` rounded-rectangle pill sitting inside
     the INFRA ring next to CORE — **with breathing room from CORE**, not
     jammed against it. Internal `publish` / `subscribe` arrows. This is
     the only place BUS appears.

5. **Right column — consumers** (line pictograms, no coloured rectangles),
   each connected to ADAPTERS via a single double-headed arrow. Order
   top-to-bottom reflects the "MONITOR + extra capability" ladder:
   - `MONITOR headless monitor, today` (solid) — label `SSE`
   - `UI visual canvas, today` (solid) — label `HTTP · SSE`
   - `AGENTS external agents, Claude Cursor` (solid) — label `MCP`
   - `VOICE voice interface, future` (dashed) — label `MCP`
   - `XR XR Omniverse, future` (dashed) — label `MCP`

   Single-line caption near the consumer column (italic humanist sans):
   *"MONITOR is the minimal common denominator — every other consumer is
   MONITOR + extra capability."*

---

## Print prep — colour-inversion check

Before sending to print:

1. Verify the rendered PNG is genuinely monochrome (no faint coloured
   anti-aliasing halos around strokes).
2. Apply a pure colour inversion (e.g. ImageMagick `-negate` or a
   Photoshop Invert adjustment).
3. Inspect the inverted output:
   - Background should now be solid black, lines and text crisp white.
   - Dashed outlines should remain clearly dashed.
   - No grey-on-grey passages where solid black was expected to invert to
     solid white.
4. Reject any version with gradients, soft shadows, or tinted fills —
   they invert to muddy mid-greys.

---

## What changes between revisions

When iterating, change **one axis at a time**:

- Structure changes → edit `architecture.mmd`
- Style changes → edit `style.md`
- Generator prompt = `architecture.mmd` + `style.md`, recombined fresh

Never let the prompt drift away from these two files.
