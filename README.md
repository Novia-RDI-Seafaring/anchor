# Anchor · agent-first knowledge canvas

[![PyPI version](https://img.shields.io/pypi/v/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![Python versions](https://img.shields.io/pypi/pyversions/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

> A canvas your AI agent can actually drive. Drop a PDF datasheet onto a workspace, ask the agent for the operating limits, get a grounded spec table where every value points back to its source page+bbox. Wire those values into a simulation. **No managed cloud, no vendor lock-in, your data stays on your laptop.**

Anchor is two things: a **generic canvas primitive** (workspace, nodes, edges, real-time multi-client sync over MCP/HTTP/SSE) and a **PDF-ingestion extension** (medallion bronze→silver→gold pipeline producing structured, page-and-bbox-anchored regions). Today PDFs are the canonical use case; the canvas itself is domain-agnostic and other extensions (transcription, code, web pages) will land alongside.

**New here?** Walk through [`docs/TUTORIAL.md`](./docs/TUTORIAL.md) — five minutes from `uv tool install` to "agent fills my engineering specs while I watch".

---

## Install

Two paths, depending on whether you want to *use* Anchor or *hack on it*.

### Use it (from PyPI)

```bash
uv tool install anchor-kb
```

`anchor` and `anchor-mcp` are now on your PATH globally. The wheel
includes the prebuilt frontend, so no Node toolchain is required to
just run it.

If you want LLM-backed gold region extraction on your first PDF upload,
create a `.env` file before starting Anchor; see
[Enable gold region extraction](#enable-gold-region-extraction). Installation
itself does not require an API key.

```bash
anchor serve              # → http://127.0.0.1:8002
```

Requires Python ≥ 3.12. macOS and Linux supported today; Windows on
the roadmap.

If you prefer plain pip:

```bash
pipx install anchor-kb
# or, in a virtualenv:
pip install anchor-kb
```

Optional extras:

| Extra | Install | Adds |
|---|---|---|
| `fmus` | `uv tool install 'anchor-kb[fmus]'` | FMU simulation runtime (`fmpy`). Without it, FMU tools fail closed unless you opt into the synthetic demo with `ANCHOR_FMU_DEMO=1`. |

### Hack on it (from source)

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
uv sync --extra dev          # adds pytest, ruff, import-linter
pnpm --dir web install
```

Start the backend in one terminal:

```bash
uv run anchor serve
```

Start the frontend development server in a second terminal:

```bash
pnpm --dir web dev
```

Open `http://localhost:5173` for the development UI. The backend remains on
`http://127.0.0.1:8002`.

Source development requires Node.js 20+ and pnpm 10. If `pnpm` is not
installed globally, run the frontend commands through Corepack instead:

```bash
corepack pnpm@10 --dir web install
# Run this in the second terminal after starting the backend.
corepack pnpm@10 --dir web dev
```

Default `--data-dir` is `~/anchor-data`; override per-command or via
`ANCHOR_DATA_DIR`.

Releases are tag-driven: pushing a `v*` tag triggers the
[release workflow](./.github/workflows/release.yml), which publishes
to PyPI via OIDC trusted publishing (no token sits in the repo). See
[`PUBLISHING.md`](./PUBLISHING.md) for the full release process.

---

## Quick start

To produce gold regions, configure a `.env` file before running `anchor demo`
or `anchor ingest`; see [Enable gold region extraction](#enable-gold-region-extraction).
Without it, Anchor still produces the silver document extraction.

```bash
# 0. One-shot: ingest the bundled LKH-5 sample, seed a `demo` workspace
#    with six placeholder spec slots, and start the server.
anchor demo

# Or step by step:

# 1. Pick a folder for your data; create your first canvas
anchor canvas create my-first-canvas --data-dir ~/anchor-data

# 2. Start the server (serves the canvas + the API + MCP-SSE on one port)
anchor serve --data-dir ~/anchor-data

# 3. (in another terminal) Ingest a PDF
anchor ingest /path/to/datasheet.pdf --data-dir ~/anchor-data

# 4. Open http://localhost:8002/c/my-first-canvas in your browser
```

See [`docs/TUTORIAL.md`](./docs/TUTORIAL.md) for a walked-through `anchor demo` → "agent fills the placeholders" tour.

That's the whole loop. Every PDF you ingest becomes a structured set of regions on disk; every canvas you create is a folder you can zip and email.

---

## Using Anchor with an AI agent (Claude Code, Cursor, your own)

Anchor exposes its tools over **MCP** (Model Context Protocol). One command registers it with Claude Code:

```bash
anchor install claude-code --data-dir ~/anchor-data
```

This writes:
- `~/.claude/mcp.json` — the MCP server entry pointing at your `anchor-mcp` binary
- `~/.claude/skills/anchor/SKILL.md` — a skill description so Claude knows when to invoke Anchor

**Restart Claude Code** (Cmd+Q, reopen). In any conversation, run `/mcp` and you should see `anchor` listed with 14 tools (5 ingest + 9 canvas). Then talk normally:

> "Ingest the PDF at ~/Downloads/lkh-pump.pdf and create a canvas called pump-analysis with a document node for it."
>
> "What does the document say about max inlet pressure for the LKH-5 at 50 Hz? Place the answer as a fact card on the pump-analysis canvas, with an evidence edge back to the source page."

Claude calls the MCP tools directly. Your browser tab on `localhost:8002/c/pump-analysis`, if open, sees nodes appear live via SSE. Multi-client real-time sync between agents and humans is the default.

For Cursor or any other MCP-speaking harness:

```bash
anchor install cursor --data-dir ~/anchor-data
# or print the install plan without writing anything:
anchor install print
```

---

## Where data lives

Every canvas is a folder. Every document is a folder. Both shareable as zips, both diffable in git.

```
~/anchor-data/
├─ bronze/                 # raw PDFs (your originals)
│   └─ datasheet.pdf
├─ silver/<doc-slug>/      # docling extraction + per-page markdown + page PNGs
│   ├─ index.json          # outline, tables, figures
│   ├─ pages.meta.json
│   └─ pages/{1.md, 1.png, …}
├─ gold/<doc-slug>/        # structured regions with page + bbox provenance
│   └─ pages/{1.regions.json, 1/r1-spec-block.png, …}
└─ canvases/<canvas-slug>/
    ├─ meta.json
    ├─ state.json          # latest snapshot
    └─ events.jsonl        # append-only log; every action ever taken
```

This layout is **the contract**. You can hand-edit JSON files, copy a canvas folder to another machine, or version-control the whole thing.

---

## Configuration

Anchor reads its config from environment variables prefixed `ANCHOR_`:

| Variable | Default | Purpose |
|---|---|---|
| `ANCHOR_DATA_DIR` | `~/anchor-data` | Where canvases + documents live |
| `ANCHOR_HTTP_PORT` | `8002` | Backend HTTP/SSE port |
| `ANCHOR_HTTP_HOST` | `0.0.0.0` | Backend listen host |
| `ANCHOR_OPENAI_API_KEY` | (unset) | Optional — enables LLM polish + region extraction in the gold layer |
| `ANCHOR_OPENAI_BASE_URL` | (unset) | Override the OpenAI-compatible endpoint. For Azure OpenAI v1 use `https://<resource>.openai.azure.com/openai/v1/`; for Ollama use `http://localhost:11434/v1`. |
| `ANCHOR_POLISH_MODEL` | `gpt-5.4` | Model name for page-MD polishing |
| `ANCHOR_REGION_MODEL` | `gpt-5.4` | Model name for region extraction |
| `ANCHOR_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Local sentence-transformer model used for semantic search. Recorded in every `embeddings.json` so cross-model search refuses to mix vectors. |
| `ANCHOR_DPI` | `150` | Render DPI for page images |
| `ANCHOR_LOG_LEVEL` | `INFO` | Logging |

If you don't set `ANCHOR_OPENAI_API_KEY`, ingest still produces silver (deterministic Docling extraction + per-page markdown). Gold extraction (LLM-driven structured regions) is skipped. The system stays useful without an API key — silver is the workable substrate; gold is the polish.

### Enable gold region extraction

Gold regions are created during PDF ingestion only. Configure a vision-capable
LLM endpoint before uploading a document or running `anchor ingest`. Documents
already ingested as silver-only are not backfilled automatically; ingest them
again after enabling a provider.

Anchor reads `.env` from the directory where you start `anchor serve`,
`anchor demo`, or `anchor ingest`. For users installed with
`uv tool install anchor-kb`, create that `.env` file in your chosen launch
directory before the first upload.

For OpenAI, create `.env` containing:

```dotenv
ANCHOR_OPENAI_API_KEY=<your-openai-api-key>
ANCHOR_POLISH_MODEL=gpt-5.4
ANCHOR_REGION_MODEL=gpt-5.4
```

For Azure OpenAI, Anchor currently supports the Azure OpenAI **v1** endpoint
through the standard OpenAI-compatible client using API-key authentication:

```dotenv
ANCHOR_OPENAI_API_KEY=<your-azure-openai-key>
ANCHOR_OPENAI_BASE_URL=https://<resource-name>.openai.azure.com/openai/v1/
ANCHOR_POLISH_MODEL=<vision-capable-deployment-name>
ANCHOR_REGION_MODEL=<vision-capable-deployment-name>
```

The Azure deployment name is used as `model` and must support image input and
JSON-formatted chat completion output. Azure Entra ID authentication and the
older Azure deployment/API-version endpoint shape are not configured by Anchor
environment variables today. See Microsoft's
[Azure OpenAI v1 API documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle?tabs=python)
for endpoint details.

From the same directory as `.env`, start Anchor and upload the PDF in the UI:

```powershell
anchor serve
```

Alternatively, ingest a file directly from the same directory:

```powershell
anchor ingest "C:\path\to\datasheet.pdf" --data-dir "$HOME\anchor-data"
```

Successful gold extraction creates `~/anchor-data/gold/<doc-slug>/pages/*.regions.json`
and returns a non-zero `region_count` when regions are identified.

For Ollama / local-LLM recipes, see [`docs/ADOPTION.md`](./docs/ADOPTION.md).

---

## Commands

```
anchor serve     [--data-dir DIR] [--host HOST] [--port PORT]
anchor ingest    PDF_PATH [--data-dir DIR] [--skip-polish] [--skip-regions]
anchor list      [--data-dir DIR]
anchor index     SLUG [--data-dir DIR]
anchor regions   SLUG [--page N] [--data-dir DIR]
anchor page-text SLUG PAGE [--data-dir DIR]
anchor embed     [SLUG] [--overwrite] [--data-dir DIR]
anchor search    "<query>" [--k N] [--data-dir DIR]
anchor canvas    list   [--data-dir DIR]
anchor canvas    create SLUG [--title TITLE] [--data-dir DIR]
anchor install     claude-code [--data-dir DIR] [--dry-run]
anchor install     cursor [--data-dir DIR] [--dry-run]
anchor install     print [--data-dir DIR]
anchor extensions  list  [--data-dir DIR] [--verbose]
anchor extensions  info  NAME [--data-dir DIR]
anchor extensions  add   MANIFEST_PATH [--scope system|project] [--data-dir DIR] [--force]
anchor extensions  remove NAME [--scope system|project] [--data-dir DIR]
anchor extensions  discover [--data-dir DIR]
anchor extensions  schema
anchor version
```

`anchor-mcp [--data-dir DIR]` runs the MCP server over stdio (used by Claude Code's MCP harness; you don't normally invoke it yourself).

---

## Architecture (one paragraph)

Anchor is a **hexagonal modular monolith**. Pure domain code in `core/` (no I/O, no framework imports — enforced by `lint-imports`). Concrete protocol implementations in `infra/`. Transport adapters in `adapters/` (HTTP, MCP, CLI, SSE). The Python wheel ships the React frontend bundle inside it (`anchor/_web_dist/`) so one process serves both the API and the UI. State changes are events, persisted to `events.jsonl` per canvas, broadcast to every subscriber (agents on MCP, browsers on SSE) within ~50 ms. The full architecture diagram is at `paperx/figures/anchor_v2_architecture.png`.

---

## Extensions and the Open Ingestion Protocol

Anchor's canvas is one **OIP consumer**. PDF ingestion is one **OIP producer**, bundled with this build. The protocol — specified at [github.com/Novia-RDI-Seafaring/OIP](https://github.com/Novia-RDI-Seafaring/OIP) — is governance-neutral: any tool that produces ingested knowledge in OIP shape can plug in, and any OIP-aware consumer can read its output. A transcription tool, a code-region extractor, a web crawler, your own ingestion logic — none of them need to import Anchor; they just ship an OIP manifest at a known location and Anchor picks them up.

The CLI surfaces this:

```bash
anchor extensions list                        # what producers can this Anchor see?
anchor extensions discover                    # where does it look for manifests?
anchor extensions add <path-to-manifest.json> # register a new producer (system-wide)
anchor extensions schema                      # print a starter manifest to edit
anchor extensions info anchor-pdfs            # full manifest for one producer
```

Discovery, in priority order:
1. **Per-data-dir** — `<data-dir>/.oip/producers.d/*.json` (highest priority; bound to a specific workspace tree)
2. **System-wide** — `~/.config/oip/producers.d/*.json` (any installer can drop a manifest here; visible to every OIP consumer on the machine)
3. **Bundled** — compiled into this Anchor wheel (currently just `anchor-pdfs`)

For implementation status: today, an OIP-registered producer is *visible* in `extensions list` but Anchor doesn't yet *spawn* external producer MCP servers and proxy their tools. That's the next engineering lift — see the [OIP repo](https://github.com/Novia-RDI-Seafaring/OIP) for the spec and `EXTENSIONS.md` for Anchor's host-side roadmap.

---

## Tests

```bash
uv sync --extra dev                       # one-time: install pytest/ruff/import-linter
uv run pytest                             # ~315 backend tests
uv run lint-imports                       # 6 dependency-rule contracts
pnpm --dir web test                       # ~180 web tests (Vitest)
pnpm --dir web exec tsc --noEmit          # web typecheck
```

The test seam is function-based pytest (matches the legacy `backend/tests/` style) with in-memory implementations of every port. Real I/O tests use `tmp_path`. The frontend tests cover canvas primitives, the SSE event store, and the inline-edit hooks.

---

## Status & roadmap

**v0.2 (current):** canvas primitive + PDF ingestion in one package, real-time SSE sync, MCP integration, skill installer for Claude Code/Cursor, ~315 Python + ~180 web tests, hexagonal contracts enforced.

**Near-term:** real `pnpm build` integration in the wheel build, port the remaining 14 v1 node renderers (image, FMU, plot, model, …), assets system (SVG/PNG upload + serve), screenshot mechanism (browser-as-screenshotter via the EventBus), viewport/visibility math, lock state on nodes.

**Mid-term:** split the canvas primitive (`anchor-canvas`) and PDF extension (`anchor-canvas-pdfs`) into separately-publishable packages, formal extension contract for third-party authors, per-project `anchor.toml` for declarative extension sets, PyPI publication.

**Longer term:** other ingestion extensions (audio/video transcription, code, web), shared org docs / personal canvases topology, optional Postgres event store for very large workspaces.

---

## Security model — read before exposing

Anchor's HTTP server is **unauthenticated by design**. It edits local
engineering data (workspaces, documents, FMU files) and is meant to run
on your own machine.

- Default bind is `127.0.0.1` (loopback). Nothing else on the LAN can
  reach it unless you pass `--host 0.0.0.0`.
- CORS is restricted to the dev Vite origin (`localhost:5173`); set
  `ANCHOR_CORS_ORIGINS=https://your-host` for explicit overrides.
- Workspace slugs and upload filenames are policy-checked and
  containment-asserted before they hit disk — the v2 codebase does not
  trust client-supplied paths.

If you want to share an Anchor instance on a network, **add your own
reverse proxy with auth in front of it** (Tailscale, OAuth proxy,
basic-auth nginx, ...). Don't expose the unauthenticated port directly.

## Limitations (v0.2)

These extensions are intentionally rough; we ship them so you can see
the shape and contribute, not as finished features:

- **`anchor_cad`** — parametric-CAD producer (jscad/openSCAD) ships as a
  proof of concept; full feature parity with STEP/STL viewing is on the
  roadmap. SVG export still has a known font-handling bug.
- **`anchor_sysml`** — SysML import (BSD-3-Clause fixtures from the OMG
  reference) and export to SVG/markdown are experimental; we'll swap
  the hand-rolled IR for the official Pydantic model when that lands.
- **`anchor_fmus`** — FMU simulation requires `fmpy` (install via
  `uv tool install 'anchor-kb[fmus]'`). Without it the extension fails
  closed; set `ANCHOR_FMU_DEMO=1` to use the synthetic-output runtime
  (every result is stamped `synthetic=true` so the UI can warn you).

## License

MIT — see [LICENSE](LICENSE).

## Contributing

PRs welcome on the `feat/architecture` branch. Run `uv run pytest && uv run lint-imports` before pushing. The `extensions/` folder convention for new extensions lands once the canvas/extension split is finalised — see `EXTENSIONS.md` for the proposed contract.
