# ANCHOR

**A**gent-**N**ative **C**anvas to **H**elp **O**rganize **R**esources<br>
*Source-Grounded Knowledge Canvas for Traceable Engineering Document Extraction*

[![PyPI version](https://img.shields.io/pypi/v/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![Python versions](https://img.shields.io/pypi/pyversions/anchor-kb.svg)](https://pypi.org/project/anchor-kb/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

ANCHOR is a tool that lets you and your agent work with engineering documents.

Drop a PDF onto a canvas. The agent reads it and pulls the values you need into a spec table. Every value links back to the page and bounding box it came from, so you can click and see the source.

Drop FMU simulation models onto the same canvas and wire the extracted values into their parameters.

It runs on your laptop. A project is a folder: run `anchor init` in it, and its documents and canvases live in a hidden `.anchor_data/` right there. Agents talk to it over MCP, so it works with Claude Code, Cursor, Claude Desktop, or any MCP client. There's an HTTP API and a CLI too.

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

The web UI ships prebuilt in the PyPI wheel. If you want the latest
`main` and PyPI is behind, install from a local checkout. Installing
directly from git source
(`uv tool install "git+https://github.com/Novia-RDI-Seafaring/anchor@main"`)
does not build the frontend and fails at the wheel build hook. Build the
frontend first:

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor && cd anchor
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv tool install --force .
```

See [Install from source](./docs/getting-started/installation.md#install-from-source)
for pnpm-not-on-PATH fallbacks.

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
and `corepack pnpm@10 --dir web dev`. If Corepack is blocked but Node.js and
npm are available, use `npx pnpm@10 --dir web install` and
`npx pnpm@10 --dir web dev`.

For normal use, run `anchor init` in a project folder. It writes an
`anchor.toml` marker and a hidden `.anchor_data/` there, and binds the project
to an environment (the provider and data zone). Commands run inside the folder
then resolve it automatically. Configuration precedence is: explicit flags,
`ANCHOR_*` environment variables, the project `anchor.toml`, the environment
`env.toml`, then built-in defaults. Provider, endpoint, and local-only policy
are environment-owned security settings: projects cannot redirect or weaken
them, and process variables cannot retarget a named environment.

Releases are tag-driven: pushing a `v*` tag triggers the
[release workflow](./.github/workflows/release.yml), which publishes
to PyPI via OIDC trusted publishing (no token sits in the repo). See
[`PUBLISHING.md`](./PUBLISHING.md) for the full release process.

---

## Quick start

Nothing to a source-grounded value in about five minutes, no API key:

```bash
uv tool install anchor-kb
anchor env create home --provider harness --yes   # no Anchor-side model endpoint
anchor install claude-desktop --env home          # or claude-code / cursor
# restart your harness, drag a PDF into the chat, ask it to ingest
anchor serve                                       # http://127.0.0.1:8002
```

On the `harness` provider your agent reads the pages, so you get gold regions
(values with page + bbox provenance) with no Anchor API key. Page content is
visible to the connected harness and may reach its model provider. Use only a
harness whose data policy is approved for the document. Full walkthrough,
provider decision table, and troubleshooting:
**[Quickstart](./docs/getting-started/quickstart.md)**.

Then [`docs/getting-started/tutorial.md`](./docs/getting-started/tutorial.md)
walks the `anchor demo` -> "agent fills the placeholders" tour.

### Drag-drop, CLI ingest, and harness ingest

There are two PDF ingestion modes:

| Mode | How it starts | Who extracts gold regions | When to use it |
|---|---|---|---|
| Built-in ingest | Canvas drag-drop, HTTP upload, MCP `ingest_pdf`, or CLI `anchor ingest` | ANCHOR's configured extractor | Normal uploads, scripted ingest, and projects with a configured vision endpoint |
| Harness-driven ingest | MCP `ingest_begin` -> `ingest_get_page` -> `ingest_submit_page` -> `ingest_finalize` | The connected agent harness, page by page | Provider `harness`, no-key workflows, or difficult PDFs where extraction quality matters more than speed |

Both modes publish to the same project data layout: `bronze/`, `silver/`,
`gold/`, and canvas state under `.anchor_data/`. A document ingested without a
vision endpoint may have silver data but no gold regions. Configure a provider
and re-ingest with `--force`, or use harness-driven ingest.

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

`anchor install claude-code` / `cursor` wire the MCP server for the default
environment. For Claude Desktop, or to serve a specific environment, use
`anchor install claude-desktop --env <name>`; it writes a named entry, echoes
the data zone before wiring, and is collision-safe. See the
[agent setup guide](./docs/guides/agent-setup.md).

See the [agent configuration guide](./docs/guides/agent-configuration.md) for
Codex, OpenCode, Cursor, Claude Code, and generic stdio examples.

---

## Where data lives

A project is a folder. Its corpus and canvases live in a hidden `.anchor_data/`
beside an `anchor.toml` marker. Everything is plain files: `tar` it, mail it,
diff it in git.

```
your-project/
├── anchor.toml             # binds this folder to an environment (provider + data zone)
└── .anchor_data/
    ├── bronze/<original>.pdf   # raw PDFs, flat (original filename)
    ├── silver/<slug>/          # Docling extraction + per-page markdown + page PNGs
    ├── gold/<slug>/            # structured regions with page + bbox provenance
    └── canvases/<slug>/        # meta.json, state.json, events.jsonl (append-only log)
```

This layout is **the contract**. You can hand-edit the JSON, copy a canvas
folder to another machine, or version-control the whole project. The file-level
detail is in [On-disk substrate](./docs/concepts/on-disk-substrate.md).

A project created by an agent (no working folder) is *managed* under its
environment at `~/.anchor/envs/<env>/projects/<name>/`, with the same
`.anchor_data/` inside. A pre-existing `~/anchor-data` from older versions keeps
working until you run `anchor migrate`.

---

## Configuration

Provider, model, and data-zone settings live in an environment's `env.toml`,
created with `anchor env create <name>`. Choose this environment before
uploading a document. The provider is a data-handling decision: it determines
whether page content stays on the computer, goes to a harness, or goes to a
configured model endpoint.

| Provider | Gold regions | Page destination | Key needed |
|---|---|---|---|
| `local` | No | This computer only | No |
| `ollama` | Yes | Your Ollama server, normally this computer or LAN | No |
| `harness` | Yes | The connected agent harness | No ANCHOR key |
| `openai` | Yes | OpenAI | Yes |
| `azure` | Yes | Your configured Azure OpenAI endpoint | Yes |
| `custom` | Yes | Your configured OpenAI-compatible endpoint | Yes |

Create and verify one environment explicitly:

```bash
anchor env create private-gold --provider ollama --vision-model llava --yes
anchor check --env private-gold --probe
```

For all provider recipes and the security implications of each choice, read
[Choose a provider and enable gold](./docs/guides/provider-setup.md) before
processing sensitive documents.

### `env.toml` is not `.env`

For an environment named `private-gold`, the supported files are:

```text
~/.anchor/envs/private-gold/env.toml   provider, endpoint, models, data zone
~/.anchor/envs/private-gold/.env       optional endpoint credential only
```

`env.toml` is non-secret and selects the provider. The environment's `.env` is
gitignored and should contain only secrets such as:

```dotenv
ANCHOR_OPENAI_API_KEY=<credential-for-this-environment>
```

The key does not select a provider and does not authorize egress by itself.
ANCHOR loads the environment `.env` only after that environment has a valid
`env.toml`. If the provider is missing, `local`, or `harness`, the runtime does
not build an endpoint client even when a key is present. Ollama does not need a
user key. Azure and custom endpoints require `ANCHOR_OPENAI_API_KEY`.

Do not put `OPENAI_API_KEY=...` in the environment `.env`; its scoped loader
imports only `ANCHOR_` variables. A process-level `OPENAI_API_KEY` is accepted
only for the public `openai` provider with no custom base URL. Using
`ANCHOR_OPENAI_API_KEY` consistently is clearer and keeps the credential scoped
to the named environment.

For `openai`, `azure`, and `custom`, omit `--yes` during interactive setup.
ANCHOR asks for the key with hidden input and saves it to the selected
environment's `.env`. With `--yes`, no prompt runs and no key is saved; create
the environment `.env` separately. Never put a key directly in a command-line
argument because shell history may retain it.

Run `anchor init --env <name>` to bind a working folder to an existing
environment. It writes a non-secret project `anchor.toml` and a hidden
`.anchor_data/`. A project cannot redirect its environment's provider or
endpoint.

### Enable gold and recover a silver-only document

Gold regions are created during ingestion only. After creating or changing an
environment, restart the server so it resolves the new provider:

```bash
anchor serve --env private-gold --project default
```

If the server is already running, stop it with `Ctrl+C` first. Documents
already ingested as silver-only are not backfilled automatically. Select the
correct environment and reingest the original PDF:

```bash
anchor use private-gold default
anchor ingest "/path/to/document.pdf" --force
anchor list
```

`anchor list` should report `"has_gold": true` and a non-zero
`region_count`. With a paid endpoint, `--force` repeats billable model calls.
See the provider guide for Windows commands and a complete troubleshooting
checklist.

### Local-only / no-egress mode (confidential documents)

For confidential documents that must never leave the host, run the `local`
provider. It runs Docling layout extraction and OCR with no external model
calls: no OpenAI-compatible client is built for any stage, regardless of any
key in your environment, and model loading is pinned offline. Gold region
extraction is skipped. Semantic region embeddings are therefore also absent,
because the current embedding pipeline operates on gold regions. Bronze,
silver, page text, and rendered pages remain available.

```bash
# One-time: warm the local model cache while you still have network.
anchor models prefetch                  # downloads bge-small + docling models

# Create a no-egress environment and bind a project to it.
anchor env create vault --yes --provider local
cd confidential-project && anchor init --env vault

# Verify the posture before feeding sensitive input.
anchor check --env vault                # shows "local-only: ON - no external egress"

# Ingest with no outbound connections.
anchor ingest "C:\path\to\datasheet.pdf"
```

The `local` provider records `local_only = true` in the environment's
`env.toml`, which the runtime honors identically across the CLI, HTTP and MCP
adapters (so an agent-launched `anchor-mcp` gets the same no-egress posture). For
a confidential corpus, use Anchor's built-in local ingest path. Do not hand the
document to a cloud-backed harness or ask it to perform harness-driven ingest,
because the harness itself would then receive the page content. On a fully
locked-down host, also export the HuggingFace offline switches so a
cache miss fails fast instead of attempting a download:

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
```

`anchor models list` reports the exact model set a local-only ingest needs;
`anchor check` echoes it and whether the offline env is active.

---

## Commands

Run most commands from inside a project folder and they resolve it automatically
(via the `anchor.toml` marker). Full reference: [docs/reference/cli.md](./docs/reference/cli.md).

```
# Environments (the provider / data-zone profile = the trust boundary)
anchor env create NAME [--provider local|harness|ollama|openai|azure|custom] [--base-url ...] [--vision-model ...]
anchor env list | show NAME | default NAME | set-description NAME "..."

# Projects (a folder = a corpus + its canvases)
anchor init [NAME] [--env NAME] [--provider ...]  # start a project in this folder
anchor project create NAME [--env NAME]          # a managed project under the env
anchor project list | set-description | move NAME --to ENV
anchor use ENV [PROJECT]                          # session default so you can omit --env
anchor migrate                                    # fold a legacy ~/anchor-data in
anchor check [--env NAME] [--probe] [--fix]       # audit the data zone before ingesting

# Local models (offline / no-egress provisioning)
anchor models list [--env NAME]                   # the local model set an ingest needs
anchor models prefetch [--env NAME] [--embed-model M]  # cache them while you have network

# Documents + search
anchor ingest PDF_PATH [--skip-polish] [--skip-regions] [--force]
anchor list | index SLUG | regions SLUG [--page N] | page-text SLUG PAGE
anchor embed [SLUG] [--overwrite] | search "<query>" [--k N]

# Canvas + server
anchor serve [--env NAME] [--project NAME] [--host HOST] [--port PORT]
anchor demo  [--no-serve]
anchor canvas list | create SLUG [--title TITLE] | placeholders SLUG | snapshot SLUG

# Agents (write a named MCP pointer for an environment)
anchor install claude-desktop --env NAME [--name ENTRY] [--create]
anchor install claude-code [--env NAME] | cursor [--env NAME] | print

# Extensions (OIP producers) + misc
anchor extensions list | info NAME | add MANIFEST | remove NAME | discover | schema
anchor version
```

`anchor-mcp --env NAME` runs the MCP server over stdio for one environment (used
by an agent's MCP harness; you don't normally invoke it yourself). `--data-dir`
is still accepted on the document/canvas commands to point at a raw storage dir,
but the project folder is the usual way in.

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
uv run pytest                             # ~570 backend tests
uv run lint-imports                       # 6 dependency-rule contracts
pnpm --dir web test                       # ~180 web tests (Vitest)
pnpm --dir web exec tsc --noEmit          # web typecheck
```

The test seam is function-based pytest with in-memory implementations of every port. Real I/O tests use `tmp_path`. The frontend tests cover canvas primitives, the SSE event store, and the inline-edit hooks.

---

## Status & roadmap

**v0.2 (current):** canvas primitive + PDF ingestion in one package, real-time SSE sync, MCP integration, folder-based projects under named environments (the data-zone / trust boundary), skill + pointer installers for Claude Code / Cursor / Claude Desktop, backend and web test suites, hexagonal contracts enforced.

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
  author       = {Lamin Jatta and Christoffer Bj{\"o}rkskog and Mikael Manng{\aa}rd and Johan West{\"o}},
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
