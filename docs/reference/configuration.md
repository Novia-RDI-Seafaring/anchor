# Configuration

Choose an environment before processing a PDF. The environment records the
provider, endpoint, and model policy; the project records its own corpus and
canvases. Start with [Provider setup](../guides/provider-setup.md) for recipes.

## Supported configuration files

| Location | Purpose |
| --- | --- |
| `~/.anchor/envs/<name>/env.toml` | Environment provider, endpoint, model settings, and metadata |
| `~/.anchor/envs/<name>/.env` | Optional environment-scoped endpoint credential |
| `~/.anchor/envs/<name>/projects.toml` | Project-name to folder registry |
| `<project>/anchor.toml` | Project name, environment binding, and permitted overrides |
| `<project>/.anchor_data/` | Project documents, canvases, and intent data |

Create profiles with `anchor env create`. Bind a working folder with
`anchor init --env NAME`, or create a managed project with
`anchor project create NAME --env ENV`. Do not put credentials in TOML profiles.

## Select a project

Inside an initialized working folder, CLI commands resolve the nearest
`anchor.toml` unless explicitly overridden. Outside that folder, selection uses
explicit `--env` / `--project` where supported, `ANCHOR_ENV` / `ANCHOR_PROJECT`,
the saved `anchor use` selection, and then the default environment and project.
An explicit `--data-dir` selects a raw storage directory for commands that
support it. Use command help for the available selectors.

```bash
anchor use study pump-study
anchor check --env study --project pump-study
anchor serve --env study --project pump-study
```

MCP selection is separate: an installed `anchor-mcp --env study` serves that
environment, and the agent chooses a project per call or with `open_project`.
CLI `anchor use` does not change the MCP server. A browser server serves one
project. `anchor serve-info` helps identify running servers.

## Environment-owned model policy

Provider, endpoint, and local-only settings belong to the environment. Project
overrides cannot redirect the endpoint or weaken local-only mode. Process
variables do not silently retarget a named environment's provider/endpoint.
Create another environment when the processing destination changes.

| Provider | Model-assisted gold | Model destination |
| --- | --- | --- |
| `local` | Skipped | No ANCHOR-side remote model client |
| `harness` | Agent ingestion session | Connected agent and its chosen model provider |
| `ollama` | Configured vision model | Configured Ollama endpoint |
| `openai` | Configured vision model | Public OpenAI endpoint |
| `azure` | Configured deployment | Configured Azure OpenAI endpoint |
| `custom` | Configured model | Configured OpenAI-compatible endpoint |

Local storage does not constrain what an external harness can retrieve or send
to its own model. A local-only pipeline may still require downloading local
weights before offline use; run `anchor models prefetch --env NAME` while online.

## Credentials

For `openai`, `azure`, and `custom`, interactive `anchor env create` can prompt
for the key with hidden input and save it to the environment's `.env`. With
`--yes`, there is no credential prompt; provision the key separately.

The environment credential file uses:

```dotenv
ANCHOR_OPENAI_API_KEY=<credential-for-this-environment>
```

The file is loaded only when the environment has a valid `env.toml`. An orphan
key file neither selects a provider nor enables model traffic. The scoped loader
accepts `ANCHOR_` names; a bare `OPENAI_API_KEY` in that file is ignored.
A process-level `OPENAI_API_KEY` is a fallback only for the public `openai`
provider with no custom base URL. Azure and custom endpoints require the explicit
credential for that environment. Ollama needs no user key.

## Model and extraction settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `embed_model` | `BAAI/bge-small-en-v1.5` | Local gold-region embeddings; configured `text-embedding-*` models use an allowed endpoint instead |
| `polish_model` / `region_model` | `gpt-5.4` | Model or deployment names used when an endpoint-backed stage is enabled |
| `openai_base_url` | Unset | Environment-owned OpenAI-compatible endpoint |
| `docling_device` | `auto` | Local extraction accelerator selection |
| `local_only` | Provider-dependent | Offline/no-remote-client policy; `local` environments enable it |

### Azure OpenAI

Defaults are configuration values, not a claim that every provider accepts that
model name. Use a vision-capable model supported by your endpoint. For Azure,
use the deployment name and a base URL ending in `/openai/v1/`.
See [Azure test-drive](../guides/azure-test-drive.md).

Gold-region embeddings are local by default. Configuring remote embeddings sends
embedding text to the permitted endpoint; remote embeddings are rejected for
providers whose policy disallows server model egress. Without gold regions there
are no gold-region vectors to search.

`docling_device` accepts `auto`, `cpu`, `cuda`, and `mps`. The default extraction
path selects CUDA when available, otherwise CPU; accelerator failures may fall
back to CPU. See the current runtime output when diagnosing a device issue.

## Process variables and command flags

These variables are recognized by runtime configuration. Named environment
policy remains authoritative for security settings; they are not a way to
redirect a configured data boundary.

| Variable | Purpose |
| --- | --- |
| `ANCHOR_ENV` / `ANCHOR_PROJECT` | CLI selection by name |
| `ANCHOR_DATA_DIR` | Raw storage-root selection when that resolution path is used |
| `ANCHOR_OPENAI_API_KEY` | Explicit endpoint credential |
| `ANCHOR_OPENAI_BASE_URL` | Endpoint setting for configuration paths that permit it |
| `ANCHOR_POLISH_MODEL` / `ANCHOR_REGION_MODEL` | Model or deployment settings |
| `ANCHOR_EMBED_MODEL` | Embedding model setting |
| `ANCHOR_DOCLING_DEVICE` | Local extraction accelerator |
| `ANCHOR_DPI` | PDF rendering DPI |
| `ANCHOR_CORS_ORIGINS` | Browser-origin configuration for the HTTP server |
| `ANCHOR_FMU_DEMO` | Explicit opt-in to synthetic FMU demo output |

`anchor serve` defaults to host `127.0.0.1` and preferred port `8002`. If the
port is occupied it chooses another free port and prints the actual URL.
The server is unauthenticated; provide an authenticated deployment layer before
network exposure. MCP snapshot configuration needs the actual server URL in
`--base-url` if it differs from the default.

## Check and recover

```bash
anchor check --env study --project pump-study
anchor check --env study --project pump-study --probe
```

`--probe` makes a minimal live endpoint call when the provider allows it. It
checks reachability, not extraction quality. Test a representative nonsensitive
PDF before relying on model output.

Restart the canvas server and reconnect the MCP process after changing provider
settings. Existing silver-only documents are not automatically backfilled. Use
the appropriate harness session or deliberate `anchor ingest PDF --force` with
a configured endpoint. Forced ingestion can repeat paid processing.
