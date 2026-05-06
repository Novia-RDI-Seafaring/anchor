# Assets

Diagrams in this folder are intentionally *not* AI-generated raster art.
The four documents in `docs/` use **Mermaid** code blocks — they render
crisply on GitHub, export cleanly to SVG via the Mermaid CLI, and a
designer can re-draw them in vector form for print without guessing at
the original geometry.

Drop hand-drawn or designer-produced illustrations here when they exist.
Suggested filenames so the markdown can be updated to point at them:

- `01-three-substrates.png` — for `01-architecture.md` (top diagram)
- `02-hexagonal-layers.png` — for `01-architecture.md` (layers diagram)
- `03-event-flow.png` — for `02-data-and-events.md`
- `04-extension-shape.png` — for `03-extensions-and-oip.md`

If you need an SVG export of the current Mermaid diagrams as a starting
point:

```bash
npx -p @mermaid-js/mermaid-cli mmdc \
  -i 01-architecture.md -o assets/01-three-substrates.svg
```

(The CLI extracts the first Mermaid block from the input file — run it
once per diagram with the right input section.)
