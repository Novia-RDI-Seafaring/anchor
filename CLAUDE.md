# Anchor — agent-first knowledge canvas (v2)

This file is the at-a-glance briefing for any Claude session working on
this repo. Read [`README.md`](./README.md) for the user-facing intro and
[`docs/01-architecture.md`](./docs/01-architecture.md) for the deep
architecture.

## What this app does

A canvas an AI agent can actually drive. Drop a PDF datasheet into a
workspace, ask the agent for the operating limits, get a grounded spec
table where every value points back to its source page + bbox. Wire
those values into a simulation. **No managed cloud, no vendor lock-in,
data stays on the user's laptop.**

The core workflow:

1. Ingest a technical PDF into the bronze → silver → gold pipeline
2. Drop the resulting document node onto a canvas (or use placeholders)
3. Ask the agent (via MCP) to extract specs, operating data, parameter tables
4. Get grounded, source-referenced spec tables on the canvas
5. Wire values into FMU simulation parameters
6. Run simulations directly from the canvas

## Architecture (v2 — hexagonal modular monolith)

```
src/anchor/
  core/          — pure domain. No httpx, no fastapi, no openai, no pymupdf.
  infra/         — port implementations (fs stores, openai clients, pymupdf, ...)
  adapters/      — http / mcp / cli — all three share one WorkspaceService
  extensions/    — anchor_pdfs / anchor_fmus / anchor_cad / anchor_sysml
web/             — React 19 + Vite + Tailwind v4 + ReactFlow
docs/            — architecture, ingestion, extensions, OIP
tests/           — function-based pytest
```

- **Python**: uv (NOT pip). `uv sync --extra dev` to install everything.
- **Frontend**: `pnpm --dir web ...` (NOT `pnpm --filter`; there is no
  workspace file at the root).
- **Database**: none. Per-workspace folders under `~/anchor-data/canvases/`
  with `meta.json` + `state.json` + append-only `events.jsonl`.
- **Real-time sync**: server-authoritative EventBus → SSE fan-out to
  every connected client. No pgvector, no Postgres, no Redis.
- **Default data dir**: `~/anchor-data` (overridable via
  `--data-dir` or `ANCHOR_DATA_DIR`).

## Canvas node types

| Node type | Purpose |
| --- | --- |
| `document` | PDF / document card with cover image |
| `spec` | Parameter / spec table with row-level source refs |
| `fmu` | FMU model node with inputs/outputs/parameters |
| `cad` | Parametric CAD (jscad/scad) viewer |
| `canvas` | Sub-canvas tile linking to another workspace |
| `concept`, `entity`, `fact`, `area`, `funnel`, `image`, `plot`, etc. | General shapes |

Renderers live under `web/src/canvas/primitives/` and shapes under
`web/src/canvas/shapes/`; the registry mapping `node_type` to a
component is `web/src/canvas/registry.ts`.

## Edge types

- `floating` — loose graph edges (automatic routing)
- `anchored` — explicit handle-to-handle connections (row-level wiring,
  evidence edges)

## Adapter parity rule

**Every new operation must reach HTTP, MCP, and CLI in the same PR.**
Agents and shell users get parity with the UI. See the
`feedback_adapter_parity.md` memory entry for the rationale.

## Document ingestion pipeline (Bronze / Silver / Gold)

Three-layer medallion architecture under `~/anchor-data/`:

| Layer | Path | Contents |
| --- | --- | --- |
| **Bronze** | `bronze/<filename>.pdf` | Raw PDF files |
| **Silver** | `silver/<slug>/` | Docling extraction: items, pages, bboxes |
| **Gold** | `gold/<slug>/` | Structured product knowledge JSON, region crops |

Every region carries `page` + `bbox` (BOTTOMLEFT coordinates from
Docling). The agent's `get_product_data(slug)` tool returns the full
gold JSON in one call.

## FMU runtime

- Real runtime: `fmpy` — `uv pip install 'anchor[fmus]'`.
- Demo runtime: `ANCHOR_FMU_DEMO=1`. Every result is stamped
  `synthetic=true` so the UI can show a `[SYNTHETIC]` badge.
- The extension **fails closed** if neither is available — the previous
  behaviour silently mounted the fake runtime, which was unsafe.

## Security model

The HTTP server is **unauthenticated**. Defaults are loopback-only
(`127.0.0.1`); CORS allows just the Vite dev origins. Workspace slugs
and upload filenames go through `validate_workspace_slug` and
`safe_upload_name`; the filesystem stores re-validate as
defence-in-depth. See `src/anchor/core/upload_safety.py` and
`src/anchor/core/ids.py` for the policy.

## Key design rules

- **FMU nodes are separate from the knowledge graph.** The agent should
  not auto-connect knowledge nodes to FMUs. Manual wiring from spec
  rows to FMU parameters is allowed.
- **Row-level provenance.** Each spec-table row carries its own
  `source_ref` (doc_id, filename, page, bbox). Source edges are visible.
- **One table per extraction.** When extracting operating/spec data,
  produce one grounded table — don't split into many small nodes.

## Development

```bash
# Backend + frontend
uv sync --extra dev
pnpm --dir web install

# Run the server
uv run anchor serve          # http://127.0.0.1:8002
# Or with Vite HMR:
pnpm --dir web dev           # http://localhost:5173, proxies API to 8002

# CLI
uv run anchor demo           # seeds a `demo` workspace with the bundled LKH-5 PDF
uv run anchor canvas list
uv run anchor canvas state <slug>
uv run anchor canvas add-node <slug> spec --label "..." --data '{"rows": [...]}'

# Tests
uv run --extra dev pytest
uv run --extra dev lint-imports
pnpm --dir web test
pnpm --dir web exec tsc --noEmit
```

## Legacy code

The pre-v2 codebase (Next.js + CopilotKit frontend, FastAPI + asyncpg +
pgvector backend, standalone `anchor-canvas` / `anchor-ingest` packages,
paper / poster drafts) lives on the `archive/pre-v2` branch (tag
`pre-v2-cutoff`). Don't revive it on `main` — open it on its own branch
if you need to crib code or context.

## Git

- Do not add "Co-Authored-By" trailers to commits.
- PRs go to `main`; feature branches `feat/<topic>`, fixups `fix/<topic>`.
