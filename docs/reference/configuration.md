# Configuration

ANCHOR resolves configuration from, in priority order: explicit command-line
flags, process-level `ANCHOR_*` variables, the selected environment's private
`.env`, the project `anchor.toml` marker, the environment `env.toml`, then
built-in defaults. Provider, endpoint, and local-only policy belong to the
environment trust boundary. A project cannot redirect or weaken them.

The API key is intentionally separate from the non-secret profile. Keep it in
`ANCHOR_OPENAI_API_KEY` or the selected environment's gitignored `.env`, never
in `env.toml` or `anchor.toml`. See
[Choose a provider and enable gold](../guides/provider-setup.md) for complete
recipes and the silver-only recovery workflow.

## Environments: `anchor env create`

The way to configure ANCHOR is `anchor env create`, which creates an
**environment** (a named profile that is the data zone) and its `default`
project:

```bash
anchor env create local         # create an environment named "local"
anchor env create work          # a named environment
```

`anchor env create` asks where document content may go (the **AI provider**,
which is also a **data zone**) and writes a non-secret `env.toml` under
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
each project keeps its corpus in a hidden `.anchor_data/` folder, so there is no
data directory to set. A managed project lives under
`~/.anchor/envs/<name>/projects/<project>/`; a project you start with `anchor
init` lives in your own folder. Either way the environment's `projects.toml`
maps the project name to its folder.

To start a project in a working folder, run `anchor init` there. It drops an
`anchor.toml` marker plus a `.anchor_data/`, binds the folder to an environment,
and registers it by name. Run Anchor anywhere inside that folder afterwards and
it resolves to the project with no flags.

Every adapter resolves the same way, selecting the environment and project by
name: `--env` / `--project`, `ANCHOR_ENV` / `ANCHOR_PROJECT`, or the `anchor
use` session selection, else the default environment and its `default` project.

!!! warning "Secrets stay out of the profile"
    The API key is never written to `env.toml`. Put it in
    `ANCHOR_OPENAI_API_KEY` (environment or a gitignored `.env` next to the
    profile), so a committed config never carries credentials. The supported
    file is `~/.anchor/envs/<name>/.env`, not a project or repository `.env`.
    This file is loaded only after the environment has a valid `env.toml`.

### Why a key does not enable gold by itself

`ANCHOR_OPENAI_API_KEY` authenticates a provider that the environment already
allows. It does not select that provider:

- No `env.toml` or no provider: model egress is disabled and gold is skipped.
- `local`: no endpoint client is built, regardless of key presence.
- `harness`: no endpoint client is built; the harness performs the vision work.
- `ollama`: no user key is required.
- `openai`, `azure`, and `custom`: the key authenticates the configured
  destination.

The environment `.env` loader imports only `ANCHOR_` variables. A bare
`OPENAI_API_KEY` in that file is ignored. A process-level `OPENAI_API_KEY` is a
fallback only for the public `openai` provider when no custom base URL is set.

### `env.toml` keys

| Key | Default | Description |
| --- | --- | --- |
| `provider` | — | The chosen provider; records the data zone. |
| `embed_model` | `BAAI/bge-small-en-v1.5` | Embedding model. A `text-embedding-*` id routes embeddings to the configured endpoint. |
| `openai_base_url` | (unset) | OpenAI-compatible endpoint for polish / region extraction. |
| `polish_model` / `region_model` | `gpt-5.4` | Vision model or deployment names. |
| `docling_device` | `auto` | Bronze-stage accelerator (see below). |

A project usually has no settings of its own and inherits the environment's. A
project may override non-security values by adding them to its own `anchor.toml`
marker (alongside the `env` and `name` keys). Attempts to override `provider` or
`openai_base_url`, weaken `local_only`, or select remote embeddings in a
no-egress environment fail before runtime startup. A malformed config is
ignored with a warning. It never crashes the CLI.

## Command-line settings

| Setting | Default | Description |
| --- | --- | --- |
| `--data-dir DIR` | the selected project's `.anchor_data/` | Storage-root override for a single command. Omit it to use the selected environment + project. |
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

- **`local`**: bronze and silver run on your machine, with no model client.
  Gold regions and their semantic embeddings are not created.
- **`ollama`**: bronze, silver, gold, and gold-region embeddings run against
  your local or LAN Ollama service. No user API key is needed.
- **`openai`**: page images and extracted text are sent to OpenAI for polish
  and region extraction.
- **`azure` / `custom`**: the same content is sent only to the endpoint you
  configure (your tenant / region, or a self-hosted gateway).
- **`harness`**: Anchor constructs no remote model client, but the connected
  agent receives page content during harness-driven ingest. Its model provider
  and retention policy are outside Anchor and must be approved separately.

Embeddings stay **local** (`bge-small`) by default, so text never leaves the
host even when the vision model is remote. Choosing a `text-embedding-*` model
sends embedding text to the configured endpoint.

Custom and Azure endpoints use only the explicit `ANCHOR_OPENAI_API_KEY` scoped
to the selected environment. They never inherit an ambient public
`OPENAI_API_KEY`. Environment `.env` values are read without being copied into
process-global state, so one resolved environment cannot leave its credential
active in another.

## Accelerator (docling)

`docling_device` / `ANCHOR_DOCLING_DEVICE` selects the bronze extraction
backend. `auto` (the default) uses CUDA when present, otherwise CPU. It does not
use MPS: docling's layout model requires float64, which Apple's MPS backend
cannot provide, so MPS fails on every document on Apple Silicon. Set `cuda` or
`mps` explicitly to force a backend; an explicitly-pinned GPU still falls back
to CPU on an accelerator error.

## Azure OpenAI

Azure OpenAI works through its **v1 (OpenAI-compatible)** surface — point ANCHOR
at it like any OpenAI-compatible endpoint. In `anchor env create`, choose
`azure` (or `custom`) and paste your `/openai/v1/` URL when prompted; the
resulting `env.toml`:

```toml
provider        = "azure"
openai_base_url = "https://<resource-name>.openai.azure.com/openai/v1/"
polish_model    = "<vision-capable-deployment-name>"
region_model    = "<vision-capable-deployment-name>"
```

Use the **deployment name** (not the base model name) as `polish_model` /
`region_model`. For Azure, do not rely on a personal `OPENAI_API_KEY`; set
`ANCHOR_OPENAI_API_KEY` to the Azure resource key in the selected environment's
gitignored `.env`:

```bash
echo 'ANCHOR_OPENAI_API_KEY=<your-azure-key>' >> ~/.anchor/envs/<name>/.env
```

PowerShell:

```powershell
$envFile = Join-Path $HOME ".anchor\envs\<name>\.env"
Add-Content -LiteralPath $envFile -Value "ANCHOR_OPENAI_API_KEY=<your-azure-key>"
```

Gold extraction through `anchor ingest` needs this keyed vision setup. If the
key is missing, bronze and silver are still written locally, but no
`OpenAIRegionExtractor` is wired and `has_gold` stays false. If the endpoint,
key, or deployment name is wrong, the Azure call fails during ingest.

Check the setup before ingesting sensitive documents:

```bash
anchor check --probe
```

Then verify an ingest:

```bash
anchor ingest path/to/file.pdf --force
anchor list
anchor gold-map <slug>
```

`anchor list` should show `"has_gold": true` and a non-zero region count.
Content stays inside your Azure tenant / region. Validate with a one-page PDF
before relying on extracted values; if your resource does not expose the v1
surface, front it with an OpenAI-compatible proxy (for example LiteLLM) and use
that URL with the `custom` provider.

## Example: OpenAI-compatible extraction

```bash
anchor env create approved-endpoint --provider custom \
  --base-url https://models.example.org/v1 \
  --vision-model <vision-model-name> --yes
echo 'ANCHOR_OPENAI_API_KEY=<your-key>' \
  >> ~/.anchor/envs/approved-endpoint/.env
anchor check --env approved-endpoint --probe
```

`anchor env create` writes the provider, endpoint, and model to `env.toml`. The
private `.env` holds only the endpoint credential. Without an approved vision
provider, local document storage, bronze and silver extraction, page rendering,
and canvas operations still work; gold regions and their semantic embeddings
are not created.
