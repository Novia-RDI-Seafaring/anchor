# Anchor v2 — poster content

Content brief for a single A1 landscape poster aimed at **academia and
industry simultaneously**. Designed in the Mike-Morrison
"better-poster" style: one large takeaway in the centre, three short
columns around it, no paragraphs of body text. Use this file as the
content source when laying out the LaTeX scaffold (`better-poster`
skill) or a printed one-pager — every zone below is explicitly named so
the layout team can place the prose into the right tile.

The artwork already on disk that the poster should pull from:
`v2/docs/assets/architecture-diagram-v17.png` (the canonical hexagonal
diagram) and `v2/docs/assets/sysml-ir-round-trip.png` (the dual-path
parser + agent → IR figure).

---

## Title strip (top)

> **ANCHOR — engineering documents become a knowledge base your agents can drive, without leaving your laptop.**
>
> *Novia RDI Seafaring · open source · runs offline · MCP-first*

Tag line beneath: *PDF datasheets · CAD models · FMU simulations · SysML
v2 — one canvas, one source of truth, every value pointing back to its
source.*

---

## Centre takeaway (one giant sentence, fills the middle of the poster)

> **Drop a datasheet. Ask a question. Get a number that points back to its source page — and that an LLM, a script, or a colleague can build on without ever opening the PDF again.**

Sub-line, slightly smaller:

> *Every value on the canvas carries `source_ref { page, bbox }` back to the original PDF region. Provenance isn't a feature — it's the contract.*

---

## Left column — THE PROBLEM (audience: industry)

**Header**: *Engineers spend a real share of their week opening PDFs and transcribing values into spreadsheets.*

Three bullets, one short sentence each:

- A small brewery sizing an Alfa Laval LKH-5 pump needs **max inlet pressure, flow envelope, NPSH, EPDM-compatibility, CIP duty** — all in one PDF, all in different sections, none of them machine-readable.
- A maritime designer pulling specs for a cooling-water loop opens **3 datasheets, 1 P&ID drawing, 2 FMU runtimes** — and copies numbers between them by hand.
- A digital-twin team integrating a simulation needs **the same parameter** from the leaflet, the SysML model, the FMU input contract, and the SCADA tag list — kept consistent over the system's lifecycle.

**Tag**: *"Where does this number come from?" is the question every engineer asks. Anchor makes it answerable in one click.*

A small bottom-left vignette: a screenshot of a typical datasheet (Alfa Laval LKH page 2 — *Technical Data* section) with the gold-extracted bboxes overlaid in cyan.

---

## Centre column — HOW IT WORKS (audience: both)

**Header**: *Hexagonal monolith. Three peer adapters. One source of truth.*

Use the existing diagram `v2/docs/assets/architecture-diagram-v17.png`
as the centrepiece of this column. Around it, three concise notes:

**Producers (left of the diagram)** — pluggable via OIP, the Open Ingestion Protocol:

- `anchor-pdfs` — datasheets, leaflets, manuals
- `anchor-cad` — STL / STEP / glTF / OpenSCAD
- `anchor-fmus` — FMI-2 simulation runtimes
- `anchor-sysml` — SysML v2 textual models
- *Future*: `anchor-pids` (P&ID schematics), third-party producers via MCP stdio

**Core (centre of the diagram)** — pure domain code, no I/O:

- `WorkspaceService` · `DomainEvent` · `Reducer`
- 6 `import-linter` contracts enforce CORE has no HTTP, no MCP, no
  Playwright, no Pymupdf
- Bus is in-memory pub/sub; events serialise per workspace

**Adapters (right of the diagram)** — three peers, equal status:

| | HTTP | MCP | CLI |
| --- | :-: | :-: | :-: |
| Web UI consumes | ✅ | | |
| Agents (Claude, Cursor) consume | | ✅ | |
| Shell + scripts consume | | | ✅ |
| Same `WorkspaceService.add_node()` call ↓ | ✅ | ✅ | ✅ |

**Tag**: *Whatever a user can do via the canvas, an agent can do via MCP, a script can do via curl, a shell can do via `anchor`. Adapter parity is verified by CI.*

---

## Right column — WHAT IT MEANS (audience: split bullets per audience)

### For industry

- **Runs on your laptop or air-gapped sim PC.** No managed tenant. Your datasheets and simulation models never leave your network.
- **No vendor lock-in.** MCP-first means any LLM (Claude, GPT, open-source) can drive Anchor; HTTP means any client can; CLI means any shell pipeline can.
- **Provenance baked in.** Every spec value carries `source_ref { page, bbox }` back to the PDF. The brewer who picks an LKH-5 can show their supplier exactly which line of the datasheet justifies it.
- **Composes with what you already have.** FMUs from Modelon / Dymola / OpenModelica plug in. STEP files from your CAD seat. PDFs from any vendor's leaflet.

### For academia

- **Agent-first hexagonal architecture** — pure CORE, three peer adapters, import-linter enforcement. A concrete answer to "what does *clean architecture* look like when LLM agents are first-class clients?"
- **OIP — Open Ingestion Protocol** — vendor-neutral spec for producers; manifest + on-disk artefacts + MCP-stdio invocation. Lets a SysML producer, a chart-tracer, a P&ID extractor compose into the same canvas with no centralised registry.
- **Provenance as a typed contract.** Every emitted value carries a `source_ref` discriminated union (page+bbox for PDFs, element_id for SysML, parameter_name for FMUs). Round-trip-tested.
- **Reproducible by design** — each canvas is a portable folder (`canvases/<slug>/{meta.json, state.json, events.jsonl}`); event log lets you replay any session deterministically.

A bottom-right vignette: the Alfa Laval LKH datasheet on the left, a SysML BDD rendering of `LKH5 :> Pump` on the right, an evidence edge between them. *Same model, two views, one truth.*

---

## Footer strip (bottom)

A three-section footer running across the bottom of the poster.

### Five-step booth demo

1. Drag the **Alfa Laval LKH leaflet** onto a fresh canvas → bronze/silver/gold pipeline runs, regions extracted with bboxes.
2. Drag the **Flow chart region** (page 4) out of the document node → a spec card appears, anchored to the source by an evidence edge.
3. Ask the agent: *"What's the max inlet pressure for the LKH-5?"* → it answers `600 kPa (6 bar)` and shows you the row on page 2.
4. Wire that value into an **FMU input** → simulation runs from the canvas.
5. Hover the evidence edge → the datasheet jumps to page 2 and highlights the exact row. **Every value, one click from its source.**

### Try it yourself

```
uv tool install anchor-kb
anchor serve
open http://127.0.0.1:8002
```

QR code → github.com/Novia-RDI-Seafaring/anchor

### Credits

- **Authors**: Christoffer Björkskog, Lamin Jatta, Novia RDI Seafaring
- **Built on**: KerML / SysML v2 (OMG), MCP (Anthropic), OIP (open spec), ReactFlow, PyMuPDF, Docling, Playwright, FMPy
- **Status**: open-source, MIT. *Talk to us at the booth or open an issue.*

---

## Notes for whoever lays this out

### Why this works for **two audiences at once**

Industry skims posters left-to-right: **problem → mechanism → adoption hint.** Academia reads centre-out: **takeaway → method → claim.** Both end up reading the same three columns; the angled cuts in the right column (industry above, academia below) let one zone serve both groups without diluting either.

### The takeaway sentence is the poster

If the layout has to drop anything, drop the right column before the centre takeaway. A reader walking past who only registers one phrase should walk away with *"every number on the canvas points back to its source page."* That's the irreducible Anchor pitch.

### What NOT to put on the poster

Things that are tempting but make the poster denser, not stronger:

- The full adapter-parity scorecard table. (Goes on the website, not the poster — one row is enough.)
- A list of every MCP tool. (Replaced by *"agents + scripts + UI share one canvas"*.)
- A long phasing roadmap. (Replaced by *"OIP composes — your producer can plug in."*)
- Code snippets longer than 4 lines. (Posters are read at 1 m, not 30 cm.)

### Suggested visual ratios

```
+------------------------------------------------------------+
|  TITLE STRIP — 8% height                                   |
+------------------------------------------------------------+
|                                                            |
|  ┌──────────┐    ╔══════════════════════╗    ┌──────────┐  |
|  │ LEFT     │    ║   TAKEAWAY (60% w)   ║    │  RIGHT   │  |
|  │ PROBLEM  │    ║                      ║    │  WHAT IT │  |
|  │ (20% w)  │    ║   (one large quote)  ║    │  MEANS   │  |
|  │          │    ║                      ║    │  (20% w) │  |
|  │          │    ║   below: HOW IT WORKS║    │          │  |
|  │          │    ║   diagram + 3 notes  ║    │          │  |
|  └──────────┘    ╚══════════════════════╝    └──────────┘  |
|                                                            |
+------------------------------------------------------------+
|  FOOTER — demo · try it · credits   (12% height)           |
+------------------------------------------------------------+
```

### Tone

- **Plain English** in the industry column. *"You keep your data"* not *"data sovereignty preserved through local-first execution"*.
- **Precise technical language** in the academic column. *"Hexagonal architecture with import-linter-enforced layering"* not *"clean separation of concerns"*.
- **No marketing words.** Avoid: *"revolutionary", "AI-powered", "next-generation"*. Use: *"vendor-neutral", "round-trip-tested", "every value source-grounded"*.

### Print specs

- A1 landscape (594 × 841 mm). Use the existing `posters/anchor/` LaTeX scaffold if it's still there, or scaffold a fresh one with the `better-poster` skill.
- Body type: a humanist sans-serif (Source Sans Pro / Inter / IBM Plex Sans). The blueprint-style figures in `v2/docs/assets/` are line-art; pair them with a sans-serif of similar weight.
- Keep the architecture figure at ≥ 35 cm wide so a reader at 1 m can follow every arrow.
