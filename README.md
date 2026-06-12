# ANCHOR

**A**gent-**N**ative **C**anvas to **H**elp **O**rganize **R**esources<br>
*Source-Grounded Knowledge Canvas for Traceable Engineering Document Extraction*

[![PyPI version](https://img.shields.io/pypi/v/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![Python versions](https://img.shields.io/pypi/pyversions/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

ANCHOR is a tool that lets you and your agent work with engineering documents.

Drop a PDF onto a canvas. The agent reads it and pulls the values you need into a spec table. Every value links back to the page and bounding box it came from, so you can click and see the source.

Drop FMU simulation models onto the same canvas and wire the extracted values into their parameters.

It runs on your laptop. Data lives under `~/anchor-data`. Agents talk to it over MCP, so it works with Claude Code, Cursor, or any MCP client. There's an HTTP API and a CLI too.

First five minutes: [`docs/getting-started/tutorial.md`](./docs/getting-started/tutorial.md).

---

## Install

Two paths, depending on whether you want to *use* ANCHOR or *hack on it*.

### Use it (from PyPI)

```bash
uv tool install anchor-kb
```

`anchor` and `anchor-mcp` are now on your PATH globally. The wheel
includes the prebuilt frontend, so no Node toolchain is required to
just run it.

If you want LLM-backed gold region extraction on your first PDF upload,
create a `.env` file before starting ANCHOR; see
[Enable gold region extraction](#enable-gold-region-extraction). Installation
itself does not require an API key.

```bash
anchor serve              # -> http://127.0.0.1:8002
```

Requires Python >= 3.12. CI tests Linux and runs CLI smoke checks on
macOS and Windows; verify browser and PDF workflows on your target platform.

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

Source development requires Node.js 20+ and pnpm 10. If `pnpm` is not installed
globally, use the Corepack form instead: `corepack pnpm@10 --dir web install`
and `corepack pnpm@10 --dir web dev`.

For normal use, run `anchor init` in a project folder and leave
`ANCHOR_DATA_DIR` unset. Commands then share the project's `anchor.toml`.
Configuration precedence is: explicit flags, `ANCHOR_*` environment variables,
`.env`, project `anchor.toml`, then built-in defaults.

Releases are tag-driven: pushing a `v*` tag triggers the
[release workflow](./.github/workflows/release.yml), which publishes
to PyPI via OIDC trusted publishing (no token sits in the repo). See
[`PUBLISHING.md`](./PUBLISHING.md) for the full release process.

---

## Quick start

To produce gold regions, configure a `.env` file before running `anchor demo`
or `anchor ingest`; see [Enable gold region extraction](#enable-gold-region-extraction).
Without it, ANCHOR still produces the silver document extraction.

```bash
# 0. One-shot: seed a `demo` workspace with six placeholder spec slots
#    and start the server. If you already have the optional local demo PDF,
#    ANCHOR ingests it too; otherwise ingest your own PDF in step 3.
anchor demo

# Or step by step:

# 1. Configure a project folder and create your first canvas
mkdir my-anchor-project
cd my-anchor-project
anchor init
anchor canvas create my-first-canvas

# 2. Start the server (serves the canvas UI, HTTP API, and browser SSE updates)
anchor serve

# 3. (in another terminal) Ingest a PDF
anchor ingest /path/to/datasheet.pdf

# 4. Open http://localhost:8002/c/my-first-canvas in your browser
```

See [`docs/getting-started/tutorial.md`](./docs/getting-started/tutorial.md) for a walked-through `anchor demo` -> "agent fills the placeholders" tour.

That's the whole loop. Every PDF you ingest becomes a structured set of regions on disk; every canvas you create is a folder you can zip and email.

---

## Using ANCHOR with an AI agent

ANCHOR exposes its tools over **MCP** (Model Context Protocol). For Claude
Code, the quickest path is the plugin marketplace. It needs no prior
install of the `anchor` CLI, only [uv](https://docs.astral.sh/uv/):

```text
/plugin marketplace add Novia-RDI-Seafaring/anchor
/plugin install anchor@anchor
```

The plugin registers the MCP server (via `uvx --from anchor-kb anchor-mcp`)
and the anchor skill in one step. See the
[Claude Code plugin guide](./docs/guides/claude-plugin.md) for details.

Alternatively, with the CLI already installed, register the local stdio
server with:

```bash
anchor install claude-code
```

Pick one of the two paths, not both.

Open Claude Code inside a folder configured with `anchor init`. In any
conversation, run `/mcp` and you should see `anchor` listed with its available
tools. The exact list depends on optional extensions such as FMU support. Then
talk normally:

> "Ingest the PDF at ~/Downloads/lkh-pump.pdf and create a canvas called pump-analysis with a document node for it."
>
> "What does the document say about max inlet pressure for the LKH-5 at 50 Hz? Place the answer as a fact card on the pump-analysis canvas, with an evidence edge back to the source page."

Claude calls the MCP tools directly. Your browser tab on `localhost:8002/c/pump-analysis`, if open, sees nodes appear live via SSE. Multi-client real-time sync between agents and humans is the default.

For Cursor:

```bash
anchor install cursor
```

See the [agent configuration guide](./docs/guides/agent-configuration.md) for
Codex, OpenCode, Cursor, Claude Code, and generic stdio examples.

---

## Where data lives

Every canvas is a folder. Every document is a folder. Both shareable as zips, both diffable in git.

```
~/anchor-data/
|- bronze/                 # raw PDFs (your originals)
|  `- datasheet.pdf
|- silver/<doc-slug>/      # docling extraction + per-page markdown + page PNGs
|  |- index.json           # outline, tables, figures
|  |- pages.meta.json
|  `- pages/{1.md, 1.png, ...}
|- gold/<doc-slug>/        # structured regions with page + bbox provenance
|  `- pages/{1.regions.json, 1/r1-spec-block.png, ...}
`- canvases/<canvas-slug>/
   |- meta.json
   |- state.json           # latest snapshot
   `- events.jsonl         # append-only log; every action ever taken
```

This layout is **the contract**. You can hand-edit JSON files, copy a canvas folder to another machine, or version-control the whole thing.

---

## Configuration

Configure a project with `anchor init`; it writes non-secret settings to
`anchor.toml`. Select the data directory and server bind address with the CLI
flags `--data-dir`, `--host`, and `--port`. The following `ANCHOR_`
environment variables override project settings:

| Variable | Default | Purpose |
|---|---|---|
| `ANCHOR_DATA_DIR` | `~/anchor-data` | Storage root override for CLI and MCP commands. An explicit `--data-dir` takes priority. |
| `ANCHOR_OPENAI_API_KEY` | (unset) | Optional: enables LLM polish + region extraction in the gold layer. Required for Azure and custom endpoints. |
| `ANCHOR_OPENAI_BASE_URL` | (unset) | Override the OpenAI-compatible endpoint. For Azure OpenAI v1 use `https://<resource>.openai.azure.com/openai/v1/`; for Ollama use `http://localhost:11434/v1`. |
| `ANCHOR_POLISH_MODEL` | `gpt-5.4` | Model name for page-MD polishing |
| `ANCHOR_REGION_MODEL` | `gpt-5.4` | Model name for region extraction |
| `ANCHOR_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Local sentence-transformer model used by default for semantic search. Recorded in every `embeddings.json` so cross-model search refuses to mix vectors. |
| `ANCHOR_DPI` | `150` | Render DPI for page images |
| `ANCHOR_CORS_ORIGINS` | (unset) | Comma-separated additional origins permitted by the HTTP server |

If no usable vision key is configured, ingest still produces silver
(deterministic Docling extraction + per-page markdown). Gold extraction
(LLM-driven structured regions) is skipped. The system stays useful without an
API key: silver is the workable substrate; gold is the polish.

### Enable gold region extraction

Gold regions are created during PDF ingestion only. Configure a vision-capable
LLM endpoint before uploading a document or running `anchor ingest`. Documents
already ingested as silver-only are not backfilled automatically; ingest them
again after enabling a provider.

ANCHOR reads `.env` from the project folder where you run `anchor init`, then
start `anchor serve`, `anchor demo`, or `anchor ingest`. For users installed
with `uv tool install anchor-kb`, create that `.env` file in your chosen
project directory before the first upload.

For OpenAI, create `.env` containing:

```dotenv
ANCHOR_OPENAI_API_KEY=<your-openai-api-key>
ANCHOR_POLISH_MODEL=gpt-5.4
ANCHOR_REGION_MODEL=gpt-5.4
```

For Azure OpenAI, ANCHOR currently supports the Azure OpenAI **v1** endpoint
through the standard OpenAI-compatible client using API-key authentication.
The key must be the Azure resource key. A personal `OPENAI_API_KEY` in your
shell is not proof that the Azure project is configured.

```dotenv
ANCHOR_OPENAI_API_KEY=<your-azure-openai-key>
ANCHOR_OPENAI_BASE_URL=https://<resource-name>.openai.azure.com/openai/v1/
ANCHOR_POLISH_MODEL=<vision-capable-deployment-name>
ANCHOR_REGION_MODEL=<vision-capable-deployment-name>
```

The Azure deployment name is used as `model`, not the base model name, and must
support image input and JSON-formatted chat completion output. Azure Entra ID
authentication and the older Azure deployment/API-version endpoint shape are
not configured by ANCHOR environment variables today. See Microsoft's
[Azure OpenAI v1 API documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle?tabs=python)
for endpoint details.

You can let ANCHOR write the non-secret project settings for you:

```bash
anchor init . --provider azure \
  --base-url https://<resource-name>.openai.azure.com/ \
  --vision-model <vision-capable-deployment-name>
echo 'ANCHOR_OPENAI_API_KEY=<your-azure-openai-key>' >> .env
anchor check --probe
```

Run those commands from the project folder, the same folder that contains
`anchor.toml` and `.env`.

From the same directory as `.env`, start ANCHOR and upload the PDF in the UI:

```powershell
anchor serve
```

Alternatively, ingest a file directly from the same directory:

```powershell
anchor ingest "C:\path\to\datasheet.pdf" --force
```

Successful gold extraction creates `~/anchor-data/gold/<doc-slug>/pages/*.regions.json`
and returns a non-zero `region_count` when regions are identified. Verify with:

```bash
anchor list
anchor gold-map <doc-slug>
```

In `anchor list`, the document should show `"has_gold": true`. If it does not,
check `ANCHOR_OPENAI_API_KEY`, the `/openai/v1/` base URL, and that
`ANCHOR_REGION_MODEL` is the Azure deployment name.

For Ollama / local-LLM recipes, see [`docs/guides/agent-setup.md`](./docs/guides/agent-setup.md).

---

## Commands

```
anchor serve     [--data-dir DIR] [--host HOST] [--port PORT]
anchor demo      [--data-dir DIR] [--host HOST] [--port PORT] [--no-serve]
anchor ingest    PDF_PATH [--data-dir DIR] [--skip-polish] [--skip-regions]
anchor list      [--data-dir DIR]
anchor index     SLUG [--data-dir DIR]
anchor regions   SLUG [--page N] [--data-dir DIR]
anchor page-text SLUG PAGE [--data-dir DIR]
anchor embed     [SLUG] [--overwrite] [--data-dir DIR]
anchor search    "<query>" [--k N] [--data-dir DIR]
anchor canvas    list   [--data-dir DIR]
anchor canvas    create SLUG [--title TITLE] [--data-dir DIR]
anchor canvas    placeholders SLUG [--data-dir DIR]
anchor canvas    snapshot SLUG [--data-dir DIR] [--base-url URL]
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

For new Claude Code setups, use the client-native `claude mcp add` command
shown above. The `anchor install claude-code` helper remains in the CLI but is
not the recommended setup path for current Claude Code releases.

`anchor-mcp [--data-dir DIR]` runs the MCP server over stdio (used by Claude Code's MCP harness; you don't normally invoke it yourself).

---

## Architecture (one paragraph)

ANCHOR is a **hexagonal modular monolith**. Pure domain code in `core/` (no I/O, no framework imports - enforced by `lint-imports`). Concrete protocol implementations in `infra/`. Transport adapters in `adapters/` (HTTP, MCP, CLI, SSE). The Python wheel ships the React frontend bundle inside it (`anchor/_web_dist/`) so one process serves both the API and the UI. State changes are events, persisted to `events.jsonl` per canvas, broadcast to subscribers (agents on MCP, browsers on SSE). See the [architecture docs](./docs/concepts/architecture.md).

---

## Extensions and the Open Ingestion Protocol

ANCHOR's canvas is one **OIP consumer**. PDF ingestion is one **OIP producer**, bundled with this build. The protocol, specified at [github.com/Novia-RDI-Seafaring/OIP](https://github.com/Novia-RDI-Seafaring/OIP), is governance-neutral: any tool that produces ingested knowledge in OIP shape can plug in, and any OIP-aware consumer can read its output. A transcription tool, a code-region extractor, a web crawler, or your own ingestion logic does not need to import ANCHOR. It only needs to ship an OIP manifest at a known location.

The CLI surfaces this:

```bash
anchor extensions list                        # what producers can this ANCHOR see?
anchor extensions discover                    # where does it look for manifests?
anchor extensions add <path-to-manifest.json> # register a new producer (system-wide)
anchor extensions schema                      # print a starter manifest to edit
anchor extensions info anchor-pdfs            # full manifest for one producer
```

Discovery, in priority order:
1. **Per-data-dir**: `<data-dir>/.oip/producers.d/*.json` (highest priority; bound to a specific workspace tree)
2. **System-wide**: `~/.config/oip/producers.d/*.json` (any installer can drop a manifest here; visible to every OIP consumer on the machine)
3. **Bundled**: compiled into this ANCHOR wheel (`anchor-pdfs`, `anchor-fmus`,
   and `anchor-cad`; SysML tools are also exposed by the bundled MCP server)

For implementation status: today, an OIP-registered producer is *visible* in `extensions list` but ANCHOR doesn't yet *spawn* external producer MCP servers and proxy their tools. That's the next engineering lift. See the [OIP repo](https://github.com/Novia-RDI-Seafaring/OIP) for the spec and `EXTENSIONS.md` for ANCHOR's host-side roadmap.

---

## Tests

```bash
uv sync --extra dev                       # one-time: install pytest/ruff/import-linter
uv run pytest                             # ~340 backend tests
uv run lint-imports                       # 6 dependency-rule contracts
pnpm --dir web test                       # ~180 web tests (Vitest)
pnpm --dir web exec tsc --noEmit          # web typecheck
```

The test seam is function-based pytest with in-memory implementations of every port. Real I/O tests use `tmp_path`. The frontend tests cover canvas primitives, the SSE event store, and the inline-edit hooks.

---

## Status & roadmap

**v0.2 (current):** canvas primitive + PDF ingestion in one package, real-time SSE sync, MCP integration, skill installer for Claude Code/Cursor, backend and web test suites, hexagonal contracts enforced.

**Near-term:** complete remaining node renderer and asset workflows, then stabilise the extension registration surface.

**Mid-term:** split the canvas primitive (`anchor-canvas`) and PDF extension (`anchor-canvas-pdfs`) into separately-publishable packages, and stabilise the extension contract for third-party authors.

**Longer term:** other ingestion extensions (audio/video transcription, code, web), shared org docs / personal canvases topology, optional Postgres event store for very large workspaces.

---

## Security model: read before exposing

ANCHOR's HTTP server is **unauthenticated by design**. It edits local
engineering data (workspaces, documents, FMU files) and is meant to run
on your own machine.

- Default bind is `127.0.0.1` (loopback). Nothing else on the LAN can
  reach it unless you pass `--host 0.0.0.0`.
- CORS is restricted to the dev Vite origin (`localhost:5173`); set
  `ANCHOR_CORS_ORIGINS=https://your-host` for explicit overrides.
- Workspace slugs and upload filenames are policy-checked and
  containment-asserted before they hit disk. The v2 codebase does not
  trust client-supplied paths.

If you want to share an ANCHOR instance on a network, **add your own
reverse proxy with auth in front of it** (Tailscale, OAuth proxy,
basic-auth nginx, ...). Don't expose the unauthenticated port directly.

## Limitations (v0.2)

These extensions are intentionally rough; we ship them so you can see
the shape and contribute, not as finished features:

- **`anchor_cad`**: parametric-CAD producer (jscad/openSCAD) ships as a
  proof of concept; full feature parity with STEP/STL viewing is on the
  roadmap. SVG export still has a known font-handling bug.
- **`anchor_sysml`**: SysML import (BSD-3-Clause fixtures from the OMG
  reference) and export to SVG/markdown are experimental; we'll swap
  the hand-rolled IR for the official Pydantic model when that lands.
- **`anchor_fmus`**: FMU simulation requires `fmpy` (install via
  `uv tool install 'anchor-kb[fmus]'`). Without it the extension fails
  closed; set `ANCHOR_FMU_DEMO=1` to use the synthetic-output runtime
  (every result is stamped `synthetic=true` so the UI can warn you).

## License

MIT, see [LICENSE](LICENSE).

## Citation

If you use ANCHOR, please cite the software repository:

```bibtex
@misc{ANCHOR,
  author       = {Lamin Jatta and Christoffer Bj{\"o}rkskog},
  title        = {ANCHOR: Agent-Native Canvas to Help Organize Resources for Traceable Engineering Document Extraction},
  year         = {2026},
  howpublished = {\url{https://github.com/Novia-RDI-Seafaring/anchor}},
}
```

GitHub-compatible citation metadata is provided in
[`CITATION.cff`](./CITATION.cff).

## Acknowledgments

This work was done in the Business Finland funded project
[Virtual Sea Trial](https://virtualseatrial.fi/).

## Contributing

Open changes as short-lived branches targeting `main`; see
[`CONTRIBUTING.md`](./CONTRIBUTING.md). Run `uv run --extra dev pytest` and
`uv run --extra dev lint-imports` before pushing backend changes. See
[`EXTENSIONS.md`](./EXTENSIONS.md) for the proposed third-party extension
contract and its current implementation status.
