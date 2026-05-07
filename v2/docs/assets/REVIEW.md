# Architecture diagrams — iteration notes

Seven versions produced this round (v11–v17). Each iteration looked at
the previous result and identified one thing that wasn't maximally clear,
then refined.

| Version | What changed                              | Outcome                              |
| ------- | ----------------------------------------- | ------------------------------------ |
| **v11** | Cleanup pass on v10: drop spurious `read` label, polish footnote, no invented annotations | Clean baseline, but extensions visually look like external services |
| **v12** | Big outer **ANCHOR RUNTIME hexagon** containing both extensions and the inner core/infra/adapters concentric hexagons | Major win — runtime boundary visually unambiguous |
| **v13** | OIP shown as a **dashed contract-surface band** running horizontally across the runtime, not just an arrow label. DOCUMENTS consolidated into one panel. | Major win — OIP becomes a *zone you cross*, not invisible text |
| **v14** | Radial layout (concentric hexagons centred), extensions as satellites, **`peers` label** between UI and AGENTS as architectural thesis | Mixed — peers label landed, but PDF source picked up Adobe-red colour breaking monochrome, layout muddled |
| **v15** | Synthesis attempt of v12+v13+v14 | Regression — gemini took prompt-language descriptions verbatim as labels ("two small rectangles connected by a line, simulation model" appeared as text) |
| **v16** | Cleaner synthesis with terse descriptors | Strong — strict monochrome, small `peers` label visible, all elements compose cleanly |
| **v17** | One more pass: bigger pictograms in extension cards, prominent `PEERS — humans + agents, equal siblings` label | **Strongest of the batch.** Bonus delight: gemini chose **anchor pictograms** inside each extension card — ties the project name to the visual language |

## Recommendation

**v17** is the version to use for the poster. It carries every architectural
claim:

- One **ANCHOR RUNTIME** hexagon as the runtime boundary
- **EXTENSIONS** row inside the runtime — bundled producers, anchor-glyphed
- **OIP — contract surface** dashed line as a visible zone
- **DOCUMENTS + CANVASES** as consolidated substrates
- **Concentric ADAPTERS / INFRA / CORE** with **BUS** pub/sub
- **PEERS — humans + agents, equal siblings** between UI and AGENTS
- **Future** (CAD, P&ID, VOICE, XR) consistently dashed
- **OIP** acronym defined in bottom-left footnote
- Pure monochrome — inverts cleanly to white-on-black for print

**Fallbacks:**
- **v13** if v17's anchor pictograms feel too on-the-nose. Cleanest "horizontal banded" version.
- **v16** if you want v17 with a more subtle peers label.
- **v10** if you want the older wide-column layout where the runtime boundary
  is implied rather than drawn.

## Source files

The Mermaid structural ground truth (`source/architecture.mmd`) and
visual rules (`source/style.md`) accumulated changes across the
iterations. Both reflect the latest layout (ANCHOR RUNTIME hexagon,
OIP contract surface band, peers grouping). Use them as the spec for a
designer redrawing the diagram in vector form for the print poster.
