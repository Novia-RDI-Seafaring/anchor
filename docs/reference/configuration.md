# Configuration

ANCHOR resolves configuration from, in priority order: explicit command-line
flags, `ANCHOR_*` environment variables, a `.env` file, the project
`project.toml`, the environment `env.toml`, then built-in defaults.

## Environments: `anchor init`

The recommended way to configure ANCHOR is `anchor init`, which creates an
**environment** (a named profile that is the data zone) and its `default`
project:

```bash
anchor init local           # create an environment named "local"
anchor init work            # a named environment
```

`anchor init` asks where document content may go (the **AI provider**, which is
also a **data zone**) and writes a non-secret `env.toml` under
`~/.anchor/envs/<name>/`:

| Provider | Data zone |
| --- | --- |
| `local` | on-host; nothing leaves the network (no gold regions) |
| `ollama` | your machine / LAN; no internet egress (offline gold regions) |
| `openai` | public cloud |
| `azure` | your Azure tenant / region |
| `custom` | any OpenAI-compatible endpoint; you label the zone |

It also picks the embedding model (local `bge-small`, or a remote
`text-embedding-3-*` when an endpoint is configured). Storage is structural:
projects live under `~/.anchor/envs/<name>/projects/<project>/`, so there is no
data directory to set.

Every adapter resolves the same way, selecting the environment and project by
name: `--env` / `--project`, `ANCHOR_ENV` / `ANCHOR_PROJECT`, or the `anchor
use` session selection, else the default environment and its `default` project.

!!! warning "Secrets stay out of the profile"
    The API key is never written to `env.toml`. Put it in
    `ANCHOR_OPENAI_API_KEY` (environment or a gitignored `.env` next to the
    profile), so a committed config never carries credentials.

### `env.toml` keys

| Key | Default | Description |
| --- | --- | --- |
| `provider` | — | The chosen provider; records the data zone. |
| `embed_model` | `BAAI/bge-small-en-v1.5` | Embedding model. A `text-embedding-*` id routes embeddings to the configured endpoint. |
| `openai_base_url` | — | OpenAI-compatible endpoint for polish / region extraction. |
| `polish_model` / `region_model` | `gpt-5.4` | Vision model or deployment names. |
| `docling_device` | `auto` | Bronze-stage accelerator (see below). |

A project may override any of these in its own `project.toml`. A malformed
config is ignored with a warning — it never crashes the CLI.

## Command-line settings

| Setting | Default | Description |
| --- | --- | --- |
| `--data-dir DIR` | the selected project's directory | Storage-root override for a single command. Omit it to use the selected environment + project. |
| `--env NAME` / `--project NAME` | the default env / `default` | Select the environment and project for the command. |
| `--host HOST` | `127.0.0.1` | HTTP bind address for `anchor serve`. |
| `--port PORT` | `8002` | Preferred HTTP port. If it is in use, `anchor serve` binds the next free port and prints the chosen URL. |

Use loopback unless you provide authentication and TLS through your own
deployment layer.

## Supported environment variables

| Variable | Purpose |
| --- | --- |
| `ANCHOR_ENV` | Environment NAME to use; overrides the default environment. |
| `ANCHOR_PROJECT` | Project NAME to use; overrides the `default` project. |
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

## Azure OpenAI

Azure OpenAI works through its **v1 (OpenAI-compatible)** surface — point ANCHOR
at it like any OpenAI-compatible endpoint. In `anchor init`, choose `azure` (or
`custom`) and paste your `/openai/v1/` URL when prompted; the resulting
`env.toml`:

```toml
provider        = "azure"
openai_base_url = "https://<resource-name>.openai.azure.com/openai/v1/"
polish_model    = "<vision-capable-deployment-name>"
region_model    = "<vision-capable-deployment-name>"
```

```bash
export ANCHOR_OPENAI_API_KEY=<your-azure-key>   # never written to env.toml
```

Use the **deployment name** (not the base model name) as `polish_model` /
`region_model`. Content stays inside your Azure tenant / region — the "my zone"
posture. Validate with a one-page PDF before relying on extracted values; if your
resource does not expose the v1 surface, front it with an OpenAI-compatible proxy
(for example LiteLLM) and use that URL with the `custom` provider.

## Example: OpenAI-compatible extraction

```bash
export ANCHOR_OPENAI_API_KEY=<your-key>
export ANCHOR_OPENAI_BASE_URL=https://api.openai.com/v1
```

`anchor init` writes the matching `env.toml` for you. Without an API key,
local document storage, page rendering, search, and canvas operations still
work; gold-region extraction is the only step that needs the vision endpoint.
