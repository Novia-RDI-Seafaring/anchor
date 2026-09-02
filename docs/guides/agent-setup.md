# Adoption

This guide describes the supported path for running ANCHOR outside the
repository and connecting it to an MCP-capable agent harness.

## 1. Install and run

Install the packaged application:

```bash
uv tool install anchor-kb
anchor serve
```

The wheel includes the web frontend. You need Node.js and pnpm only when
working on `web/` from a source checkout:

```bash
git clone https://github.com/Novia-RDI-Seafaring/anchor
cd anchor
uv sync --extra dev
pnpm --dir web install
uv run anchor serve
# in another terminal:
pnpm --dir web dev
```

Source development requires Node.js 20+ and pnpm 10. If `pnpm` is not
installed globally, use Corepack for the frontend commands instead:

```bash
corepack pnpm@10 --dir web install
corepack pnpm@10 --dir web dev
```

ANCHOR serves the UI and HTTP API at `http://127.0.0.1:8002` by default.
It is unauthenticated, so bind to a network interface only behind an
authentication layer.

The recommended setup is one environment with a project inside it. Run
`anchor env create` to choose the AI provider / data zone; it creates a named
environment and its default project. Then run `anchor init` inside a working
folder to start a project bound to that environment:

```bash
anchor env create local
cd ~/work/pumps
anchor init
anchor ingest /path/to/datasheet.pdf
anchor serve
```

Storage is structural. A project is a folder with an `anchor.toml` marker and a
hidden `.anchor_data/` holding its corpus. A managed project lives under
`~/.anchor/envs/<env>/projects/<project>/`. The environment keeps a
`projects.toml` registry mapping each project name to its folder.

`anchor demo` creates a `demo` workspace and placeholder nodes. It ingests an
optional local sample PDF when one is present, but the public package does not
ship a vendor PDF. In normal use, ingest a PDF you are allowed to process.

## 2. Agent harness setup

ANCHOR exposes MCP tools through the `anchor-mcp` stdio executable. Register it
with the installer, which points at an environment by name:

```bash
anchor install claude-code               # MCP entry + skill (default env)
anchor install claude-desktop --env work
anchor install cursor --env work
```

The entry runs `anchor-mcp --env <name>`. The server serves that one
environment; projects inside it are addressed by a per-call `project` argument
(`list_projects` enumerates them). A second environment is a second named
server.

Cursor has no global skills directory, so the MCP entry alone gives a Cursor
agent the tools and the server's own briefing but not the project conventions.
For a Cursor workspace that is an Anchor project, add `--rules` to also write a
project-scoped `.cursor/rules/anchor.mdc` that points the agent at `AGENTS.md`
plus the CLI/MCP surfaces:

```bash
cd ~/work/pumps
anchor install cursor --rules            # writes ./.cursor/rules/anchor.mdc
```

The rules file is a short pointer, not a copy of `AGENTS.md`. The write is
idempotent and will not overwrite a file you have edited unless you pass
`--force`; use `--project-dir` to target a directory other than the current
one.

Restart the harness and verify that `anchor` appears in its MCP server list.
The set of tools depends on available optional extensions, such as the FMU
runtime.

If reinstalling ANCHOR fails on Windows because `anchor-mcp.exe` is in use,
close the MCP client and follow the reinstall steps in
[Install](../getting-started/installation.md#reinstall-or-upgrade).

See [Agent configuration](agent-configuration.md) for verified Claude Code,
Codex, Gemini CLI, OpenCode, Cursor, and generic stdio examples.

`anchor serve` exposes the browser UI, HTTP API, and browser SSE updates. It
does not expose an authenticated remote-MCP HTTP endpoint. A hosted or remote
MCP integration therefore requires additional transport and authentication
work.

## 3. Viewing and snapshotting canvases

Keep a browser open on:

```text
http://127.0.0.1:8002/c/<workspace-slug>
```

Changes written through HTTP, CLI, or MCP are reflected through the browser's
SSE subscription.

Snapshots render the same browser canvas through headless Chromium and
therefore require a running `anchor serve`:

```bash
anchor canvas snapshot <workspace-slug> --out canvas.png
```

From MCP, use `canvas_snapshot(..., format="inline")` when the harness can
render image content directly. Use `format="path"` for local agents that can
read files from the same machine, or `format="base64"` when raw transfer is
needed.

## 4. LLM endpoints and local operation

An API key is not the first setup step. Create an environment first so
`env.toml` records the provider and data boundary. The key only authenticates
an endpoint that this environment already permits. A key cannot select a
provider or enable egress on its own.

For local gold through Ollama, start a vision-capable model and create an
Ollama environment:

```bash
anchor env create private-gold --provider ollama \
  --base-url http://localhost:11434/v1 \
  --vision-model llava --yes
anchor check --env private-gold --probe
```

Ollama does not need `ANCHOR_OPENAI_API_KEY`. ANCHOR supplies the harmless
local placeholder required by the OpenAI-compatible client library.

For a keyed provider, create the environment, then put the endpoint credential
in the selected environment's private file:

```text
~/.anchor/envs/<environment-name>/.env
```

```dotenv
ANCHOR_OPENAI_API_KEY=<credential-for-that-endpoint>
```

Do not put `OPENAI_API_KEY` in this file. The environment-scoped loader imports
only `ANCHOR_` names. The environment must also have a valid `env.toml`; an
orphan `.env` is not loaded. Provider, endpoint, and model names belong in
`env.toml`, which `anchor env create` writes for you.

Use a model that accepts image input and evaluate extraction quality on your
own documents before relying on extracted engineering values. See
[Choose a provider and enable gold](provider-setup.md) for all provider
recipes, server restart instructions, and silver-only recovery.

Gold-region embeddings use the local sentence-transformer model
`BAAI/bge-small-en-v1.5` by default. The Python dependency ships with ANCHOR;
the model weights must already be cached or downloaded before fully offline
use. A silver-only document has no gold regions to embed, so its region
embedding count is zero.

## 5. Offline boundary

| Step | Local without a hosted API? | Notes |
|---|---|---|
| Store source PDF and render pages | Yes | Files stay under the project's `.anchor_data/`. |
| Silver extraction | Yes | Docling and local rendering. |
| Gold extraction and page polish | Conditional | Requires a configured vision endpoint; this may be local. |
| Gold-region embeddings and search | Yes, after gold and model availability | Local sentence-transformer default. Silver-only documents have no region vectors. |
| Workspace state, HTTP, SSE, MCP-stdio | Yes | Runs on the local machine. |
| Canvas snapshot | Yes | Requires local `anchor serve` and Chromium support. |
| Agent harness model calls | Outside ANCHOR | Governed by the harness you choose. |

## Code pointers

- Harness installer: `src/anchor/adapters/cli/install.py`
- CLI wiring: `src/anchor/adapters/cli/main.py`
- MCP stdio entry: `src/anchor/adapters/mcp/stdio_main.py`
- MCP snapshot promotion: `src/anchor/adapters/mcp/server.py`
- Runtime configuration: `src/anchor/infra/config.py`
- PDF LLM adapters: `src/anchor/extensions/anchor_pdfs/infra/llm/`
