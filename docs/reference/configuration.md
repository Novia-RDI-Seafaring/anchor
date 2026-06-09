# Configuration

ANCHOR resolves configuration from, in priority order: explicit command-line
flags, `ANCHOR_*` environment variables, a `.env` file, a project `anchor.toml`,
then built-in defaults.

## Projects: `anchor init`

The recommended way to configure ANCHOR is `anchor init`, run inside the folder
you want to work in:

```bash
cd ~/my-project
anchor init
```

A folder with an `anchor.toml` is an ANCHOR *project*. `anchor init` asks where
document content may go — the **AI provider**, which is also a **data zone** —
and writes a non-secret `anchor.toml`:

| Provider | Data zone |
| --- | --- |
| `local` | on-host; nothing leaves the network (no gold regions) |
| `ollama` | your machine / LAN; no internet egress (offline gold regions) |
| `openai` | public cloud |
| `azure` | your Azure tenant / region |
| `custom` | any OpenAI-compatible endpoint; you label the zone |

It also picks the embedding model (local `bge-small`, or a remote
`text-embedding-3-*` when an endpoint is configured) and the data directory
(defaults to `<project>/anchor-data`).

Every adapter — the `anchor` CLI, `anchor serve`, and an agent-launched
`anchor-mcp` — resolves `anchor.toml` by walking up from its working directory.
So you configure once and run ANCHOR from inside the project folder. Name a
project explicitly with `anchor-mcp --project <folder>` or by setting
`ANCHOR_CONFIG` to the file's path.

!!! warning "Secrets stay out of `anchor.toml`"
    The API key is never written to `anchor.toml`. Put it in
    `ANCHOR_OPENAI_API_KEY` (environment or a gitignored `.env`), so a committed
    config never carries credentials.

### `anchor.toml` keys

| Key | Default | Description |
| --- | --- | --- |
| `provider` | — | The chosen provider; records the data zone. |
| `data_dir` | `<project>/anchor-data` | Storage root for this project. |
| `embed_model` | `BAAI/bge-small-en-v1.5` | Embedding model. A `text-embedding-*` id routes embeddings to the configured endpoint. |
| `openai_base_url` | — | OpenAI-compatible endpoint for polish / region extraction. |
| `polish_model` / `region_model` | `gpt-5.4` | Vision model or deployment names. |
| `docling_device` | `auto` | Bronze-stage accelerator (see below). |

A malformed `anchor.toml` is ignored with a warning — it never crashes the CLI.

## Command-line settings

| Setting | Default | Description |
| --- | --- | --- |
| `--data-dir DIR` | resolved from config, else `~/anchor-data` | Storage root. Omit it to use the project resolved from the working directory. |
| `--host HOST` | `127.0.0.1` | HTTP bind address for `anchor serve`. |
| `--port PORT` | `8002` | Preferred HTTP port. If it is in use, `anchor serve` binds the next free port and prints the chosen URL. |

Use loopback unless you provide authentication and TLS through your own
deployment layer.

## Supported environment variables

| Variable | Purpose |
| --- | --- |
| `ANCHOR_CONFIG` | Absolute path to an `anchor.toml` to use; overrides walk-up discovery. |
| `ANCHOR_DATA_DIR` | Default storage root. An explicit `--data-dir` or a project `anchor.toml` takes priority. |
| `ANCHOR_OPENAI_API_KEY` | Credential for an OpenAI-compatible endpoint used by LLM-backed extraction. |
| `ANCHOR_OPENAI_BASE_URL` | OpenAI-compatible endpoint base URL, including local services. |
| `ANCHOR_POLISH_MODEL` | Vision-capable model used for markdown polishing. |
| `ANCHOR_REGION_MODEL` | Vision-capable model used for region extraction. |
| `ANCHOR_EMBED_MODEL` | Embedding model id (local sentence-transformer, or `text-embedding-*` for remote). |
| `ANCHOR_DOCLING_DEVICE` | Bronze-stage accelerator: `auto`, `cpu`, `cuda`, `mps`. |
| `ANCHOR_DPI` | PDF rendering DPI for silver pages and region crops. |
| `ANCHOR_CORS_ORIGINS` | Additional browser origins allowed by the HTTP server. |
| `ANCHOR_FMU_DEMO` | Enables synthetic FMU demo behavior when explicitly set. |

## Data zones and egress

The provider you pick determines where document content may go:

- **`local` / `ollama`** — bronze, silver, and embeddings run on your machine;
  no document content leaves the network. `ollama` adds offline gold regions via
  a local vision model.
- **`openai`** — page images and extracted text are sent to OpenAI for polish
  and region extraction.
- **`azure` / `custom`** — the same content is sent only to the endpoint you
  configure (your tenant / region, or a self-hosted gateway).

Embeddings stay **local** (`bge-small`) by default, so text never leaves the
host even when the vision model is remote. Choosing a `text-embedding-*` model
sends embedding text to the configured endpoint.

## Accelerator (docling)

`docling_device` / `ANCHOR_DOCLING_DEVICE` selects the bronze extraction
backend. `auto` (the default) uses CUDA when present, otherwise CPU. It does not
use MPS: docling's layout model requires float64, which Apple's MPS backend
cannot provide, so MPS fails on every document on Apple Silicon. Set `cuda` or
`mps` explicitly to force a backend; an explicitly-pinned GPU still falls back
to CPU on an accelerator error.

## Example: OpenAI-compatible extraction

```bash
export ANCHOR_OPENAI_API_KEY=<your-key>
export ANCHOR_OPENAI_BASE_URL=https://api.openai.com/v1
```

`anchor init` writes the matching `anchor.toml` for you. Without an API key,
local document storage, page rendering, search, and canvas operations still
work; gold-region extraction is the only step that needs the vision endpoint.
