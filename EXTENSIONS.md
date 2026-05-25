# Anchor extensions — the contract

Anchor's canvas primitive is domain-agnostic. **Extensions** layer specific
ingestion pipelines, node types, edge styles, and UI components on top of it.
Today the PDF medallion pipeline (Docling + VLM region extraction + spec
tables with page+bbox provenance) lives inside the same wheel as the canvas;
this document describes the contract every extension follows so future
extensions — transcription, code regions, web pages, your own — can ship
either in-tree or as separate `anchor-canvas-*` packages.

---

## What an extension provides

```python
from anchor.canvas import CanvasCore, NodeType, ToolDef, SourceRefKind

class AnchorExtension(Protocol):
    NAME: str               # machine identifier, used as namespace prefix.
                            # e.g. "anchor_pdfs", "anchor_transcribe"
    DISPLAY_NAME: str       # human-friendly label for UI
    VERSION: str            # extension version (semver)
    REQUIRES_CANVAS: str    # canvas-core compat range, e.g. ">=0.2,<0.3"

    def configure(self, canvas: CanvasCore) -> None:
        """Called once at canvas startup. Register everything here."""
        canvas.node_types.register_many([
            NodeType("pdf:document", data_schema=DocumentData),
            NodeType("pdf:spec_table", data_schema=SpecTableData),
            ...
        ])
        canvas.source_ref_kinds.register(
            SourceRefKind("pdf-page-bbox", schema=PdfPageBboxRef,
                          renderer_hint="open_pdf_at_bbox"),
        )
        canvas.mcp_tools.register_namespace("pdf", [
            ToolDef("ingest", schema=...),
            ToolDef("list_documents", schema=...),
            ...
        ])
        canvas.http.mount_router("/api/pdfs", router)
        canvas.events.register([DocBronzed, DocSilvered, DocIngested, ...])
        canvas.services.provide("pdfs.ingest_service", IngestService(...))
```

**Frontend half** (parallel contract for the React app):

```typescript
import { registerExtension } from "@anchor/canvas/extensions";
import { SpecTableNode, DocumentNode } from "./nodes";

registerExtension({
  name: "anchor_pdfs",
  nodeTypes: {
    "pdf:document": DocumentNode,
    "pdf:spec_table": SpecTableNode,
  },
  edgeStyles: {
    "pdf:evidence": { stroke: "#FF8E2B", dasharray: "4 4" },
  },
  sourceRefHandlers: {
    "pdf-page-bbox": openPdfAtBbox,
  },
});
```

---

## Naming convention

- **Node types:** `<extension_name_short>:<type>` (e.g. `pdf:spec_table`,
  `transcribe:segment`, `code:region`). The `:` prefix prevents collisions.
- **MCP tools:** prefixed namespaces (`pdf.ingest`, `pdf.list_documents`,
  `transcribe.ingest_audio`).
- **HTTP routes:** `/api/<extension_short>/...` (`/api/pdfs/...`,
  `/api/transcribe/...`).
- **Source-ref kinds:** `<short>-<address-shape>` (`pdf-page-bbox`,
  `audio-timestamp`, `code-line-range`).
- **On-disk substrates:** `data/<short>/...` (`data/bronze/`, `data/silver/`,
  `data/gold/` for PDFs; would be `data/transcripts/` for transcription).

---

## What the canvas core provides

The canvas core is the **substrate**. Extensions consume:

```
core/
  workspace/      # Workspace aggregate, Node, Edge, reducer, validator
  events/canvas.py  # NodeAdded, NodeMoved, EdgeAdded, …
  ports/          # WorkspaceStore, EventBus, AssetStore
  services/       # WorkspaceService — generic CRUD over canvases

infra/
  stores/fs_workspace_store.py
  bus/memory_bus.py

adapters/
  http/routers/{workspaces, nodes, edges, sse}.py
  mcp/{server, handlers_canvas, stdio_main}.py
  cli/main.py     # the `anchor` binary, with extension subcommands

Built-in node types: concept, entity, fact, area, note
Built-in edge types: floating, anchored
```

Every extension can use these without re-inventing them. Extensions only
add what's specific to their domain.

---

## Three ways to ship an extension

### 1. In-tree (`extensions/` folder, recommended for the curated set)

```
v2/extensions/
└── anchor_pdfs/
    ├── pyproject.toml
    ├── src/anchor_pdfs/
    │   ├── extension.py              # AnchorExtension implementation
    │   ├── core/, infra/, adapters/  # backend code
    │   └── ...
    ├── web/
    │   ├── package.json
    │   └── src/index.ts              # registerExtension(...)
    └── tests/
```

Discovery: the canvas runner walks `extensions/` at startup, imports each
`extension:Extension` class, calls `configure(canvas)`. Frontend imports each
`extensions/*/web/dist/index.js` at canvas mount.

**Status today:** PDF ingestion lives inside `src/anchor/` directly, not yet
extracted into `extensions/anchor_pdfs/`. The split lands as a refactor pass
once the API surface is stable. Use `extensions/` for genuinely new
extensions you'd contribute upstream.

### 2. Out-of-tree pip-installable package

Anyone publishes their own `anchor-canvas-<name>` package to PyPI:

```toml
# my-anchor-ext/pyproject.toml
[project]
name = "anchor-canvas-mermaid"
dependencies = ["anchor-canvas>=0.2"]

[project.entry-points."anchor.extensions"]
mermaid = "anchor_canvas_mermaid.extension:MermaidExtension"
```

Discovery: the canvas runner reads Python entry points
(`importlib.metadata.entry_points(group='anchor.extensions')`) and loads each
registered class.

```bash
uv tool install --with anchor-canvas-mermaid anchor-canvas
anchor serve --data-dir ~/anchor-data    # picks up mermaid automatically
```

### 3. Local / editable (for extension developers)

Set `ANCHOR_EXTENSIONS_PATH` to a colon-separated list of directories
containing extension source code. Canvas runner walks each path, finds the
`extension.py` entry point, loads the extension without packaging.

```bash
export ANCHOR_EXTENSIONS_PATH=~/dev/my-ext:~/dev/another-ext
anchor serve --data-dir ~/anchor-data
```

Useful for iterating on a new extension without `pip install -e .` round-trips.

---

## Per-project extension pinning (planned)

For reproducible extension sets bound to a `--data-dir`:

```toml
# ~/anchor-data/cooling-system/anchor.toml
[anchor]
canvas_version = ">=0.2,<0.3"

[[extensions]]
name = "anchor-canvas-pdfs"
version = ">=0.2"

[[extensions]]
git = "https://github.com/someone/anchor-canvas-mermaid"
ref = "v0.1"

[[extensions]]
path = "/Users/me/dev/my-custom-ext"
```

`anchor serve --data-dir <dir>` reads `<dir>/anchor.toml`, ensures every
listed extension is available (or fails loudly with install instructions),
loads them, starts. Lands in v0.4.

---

## What lives in the canvas core vs. an extension

| Concern | Canvas core | Extension |
|---|---|---|
| Workspace, Node, Edge, reducer | ✓ | |
| Generic node types: concept, entity, fact, area, note | ✓ | |
| Generic edge types: floating, anchored | ✓ | |
| EventBus, SSE, WebSocket | ✓ | |
| Asset upload + serve | ✓ | |
| Screenshot mechanism (browser-as-screenshotter) | ✓ | |
| Viewport math (fit, visibility) | ✓ | |
| Lock state on nodes | ✓ | |
| `data.locked`, `data.visible`, `data.layer`, `data.opacity` | ✓ | |
| Domain-specific node types (pdf:spec_table, transcribe:segment, …) | | ✓ |
| Domain-specific schemas in `Node.data` | | ✓ |
| Domain-specific source-ref kinds | | ✓ |
| Ingestion pipelines (Docling, Whisper, tree-sitter, …) | | ✓ |
| Domain-specific React renderers | | ✓ |
| Domain-specific edge styling (e.g. `pdf:evidence` orange-dashed) | | ✓ |
| MCP tools for domain operations | | ✓ |

**The principle:** if the canvas core needs to know about a domain to
function, it doesn't belong in core. Canvas core only knows registries.

---

## Honest gotchas for extension authors

1. **Frontend bundling is the harder problem.** Extensions need to ship JS
   bundles that load into the canvas's React app. Today (in-tree) we glob
   `extensions/*/web/src/index.ts` at build time. Out-of-tree extensions
   eventually need Module Federation. We'll ship that path when there's
   demand.

2. **`Node.data` is not type-safe across the wire.** Validators in the
   `NodeTypeRegistry` enforce schemas at command time, but anyone reading the
   stored JSON has to revalidate. Keep your schemas backwards-compatible.

3. **Source-ref kinds need to be unique.** If two extensions both register
   `"page-bbox"` you'll get an error at startup. Always namespace
   (`"pdf-page-bbox"`, not `"page-bbox"`).

4. **Don't fight the layer rules.** Your extension's `core/` may not import
   `httpx`/`fastapi`/`openai`/etc. Same hexagonal discipline applies. Run
   `lint-imports` on your extension.

5. **Test against the canvas's in-memory implementations.** The canvas
   core ships `MemoryWorkspaceStore`, `MemoryDocStore`, `MemoryEventBus` —
   use them in your unit tests so you don't need a real filesystem.

---

## Status of the contract

**Stable today:**
- Canvas core's domain model (Workspace, Node, Edge, reducer, events)
- `NodeTypeRegistry` for runtime node-type registration
- HTTP/MCP/CLI/SSE adapter shape

**In flux (will stabilise as we extract the canvas primitive):**
- The `AnchorExtension` Protocol class itself (today: implicit in how PDF
  code is wired; tomorrow: an explicit class)
- Frontend `registerExtension(...)` API
- Source-ref kind registry
- Edge-style registry

**Not yet implemented but documented here:**
- Out-of-tree extension discovery via Python entry points
- `anchor.toml` per-project extension pinning
- `ANCHOR_EXTENSIONS_PATH` for editable-install paths
- `anchor extensions {list, install, remove}` CLI subcommand

If you're writing an extension *today*, your safest bet is to clone v2,
add it under `extensions/`, follow the patterns in the existing PDF code
(see `src/anchor/core/services/ingest_service.py`,
`src/anchor/adapters/mcp/handlers_ingest.py`,
`src/anchor/infra/llm/`). The contract above is the target shape; the
move from "implicit in v2" to "explicit Protocol" is a follow-up
refactor.
