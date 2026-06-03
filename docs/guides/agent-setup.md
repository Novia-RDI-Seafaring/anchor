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

Data defaults to `~/anchor-data`. Set `ANCHOR_DATA_DIR` to change that default,
or pass `--data-dir` explicitly. Keep `anchor serve`, `anchor ingest`, and agent
configuration on the same data directory:

```bash
anchor ingest /path/to/datasheet.pdf --data-dir ~/anchor-data
anchor serve --data-dir ~/anchor-data
```

`anchor demo` creates a `demo` workspace and placeholder nodes. It ingests an
optional local sample PDF when one is present, but the public package does not
ship a vendor PDF. In normal use, ingest a PDF you are allowed to process.

## 2. Agent harness setup

ANCHOR exposes MCP tools through the `anchor-mcp` stdio executable. For Claude
Code, register the local server with:

```bash
claude mcp add --transport stdio --scope user anchor -- \
  anchor-mcp --data-dir ~/anchor-data --base-url http://localhost:8002
claude mcp list
```

ANCHOR also provides a Cursor helper:

```bash
anchor install cursor --data-dir ~/anchor-data
```

Restart the harness and verify that `anchor` appears in its MCP server list.
The set of tools depends on available optional extensions, such as the FMU
runtime.

See [Agent configuration](agent-configuration.md) for verified Codex, OpenCode,
Cursor, Claude Code, and generic stdio examples.

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

Without an LLM key, PDF ingestion still creates the local bronze and silver
layers. Gold-region extraction and page polishing require a vision-capable
OpenAI-compatible endpoint.

For OpenAI:

```dotenv
ANCHOR_OPENAI_API_KEY=<your-api-key>
ANCHOR_POLISH_MODEL=gpt-5.4
ANCHOR_REGION_MODEL=gpt-5.4
```

For an OpenAI-compatible endpoint, set `ANCHOR_OPENAI_BASE_URL` as well. For
example, Azure OpenAI v1 uses deployment names as model identifiers:

```dotenv
ANCHOR_OPENAI_API_KEY=<your-azure-key>
ANCHOR_OPENAI_BASE_URL=https://<resource-name>.openai.azure.com/openai/v1/
ANCHOR_POLISH_MODEL=<vision-capable-deployment-name>
ANCHOR_REGION_MODEL=<vision-capable-deployment-name>
```

An Ollama or other local OpenAI-compatible server can use the same wiring:

```dotenv
ANCHOR_OPENAI_API_KEY=local
ANCHOR_OPENAI_BASE_URL=http://localhost:11434/v1
ANCHOR_POLISH_MODEL=<vision-model-name>
ANCHOR_REGION_MODEL=<vision-model-name>
```

Use a model that accepts image input and evaluate extraction quality on your
own documents before relying on extracted engineering values.

Embeddings use the local sentence-transformer model
`BAAI/bge-small-en-v1.5` by default. The Python dependency ships with ANCHOR;
the model weights must already be cached or downloaded before fully offline
use.

## 5. Offline boundary

| Step | Local without a hosted API? | Notes |
|---|---|---|
| Store source PDF and render pages | Yes | Files stay under the selected `--data-dir`. |
| Silver extraction | Yes | Docling and local rendering. |
| Gold extraction and page polish | Conditional | Requires a configured vision endpoint; this may be local. |
| Region embeddings and search | Yes, after model availability | Local sentence-transformer default. |
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
