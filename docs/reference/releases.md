# Releases

ANCHOR is published to PyPI as `anchor-kb`. Users who run:

```bash
uv tool install anchor-kb
```

receive the latest non-yanked PyPI wheel. The PyPI wheel is not updated by a
plain merge to `main`; it is updated only when maintainers tag and publish a new
release.

## Current Release

| Version | Date | Main difference |
| --- | --- | --- |
| `0.2.6` | 2026-06-22 | Environments and projects. An environment is a named configuration profile (provider, models, data zone) and the trust boundary. A project is a folder bound to one environment, with its corpus in a hidden `.anchor_data/`. `anchor env create <name>` is the provider picker; `anchor init` in a folder starts a project there and self-creates a local, zero-egress environment on a fresh machine. One MCP server serves one environment and addresses projects by a per-call name. A pre-existing `~/anchor-data` keeps working until `anchor migrate` folds it in. |
| `0.2.4` | 2026-06-11 | Config robustness for cross-platform onboarding. A `~`-relative path in a config value now expands to `$HOME` instead of creating a literal `./~` folder. On Windows, the config writer no longer emits a TOML marker in a non-UTF-8 locale encoding that the reader then rejected and silently ignored; the reader also recovers an already-corrupted file. Recommended for anyone on Windows. |
| `0.2.3` | 2026-06-10 | Azure + agent-experience hardening. `anchor version` / `--version` report the real installed version (was stuck at `0.2.0`). `anchor ingest` is idempotent (skips when gold exists; `--force` to recompute). New `anchor canvas url` and `anchor check`; HuggingFace/docling noise no longer pollutes `search` / `ingest` output. Fixes a data-egress edge case where a missing key could route document pages to public OpenAI, and `anchor init` self-corrects an Azure endpoint. |
| `0.2.2` | 2026-06-09 | Onboarding release. The init flow configures the AI provider / data zone and models, and one MCP registration serves every project. Azure OpenAI works via its v1 endpoint; docling auto-selects CUDA or CPU; `anchor serve` falls through to a free port. |
| `0.2.1` | 2026-06-08 | Patch release for public testing. It includes the Windows Unicode ingest fix, canvas ingest progress feedback, timing reports, canvas deletion, improved region overlays and updated MCP setup docs. |
| `0.2.0` | 2026-05-25 | First public release of the v2 local canvas, PDF ingestion, MCP server, CLI, HTTP API and bundled web UI. |

## Why `0.2.6` matters

`0.2.6` makes the data boundary explicit and reusable. An **environment** is a
named profile: the AI provider, the models, and the data zone it implies. It is
the trust and egress boundary, so it decides where a corpus's content may go.
Create one with `anchor env create <name>`. A **project** is a folder bound to
an environment. It carries an `anchor.toml` marker and keeps its corpus in a
hidden `.anchor_data/` subfolder, so the working folder stays clean. Run
`anchor init` inside a folder to start a project there. On a fresh machine that
sets up a local, zero-egress environment for you, so the first run needs no
configuration.

Each environment keeps a `projects.toml` registry, so every project is
addressable by name. Run Anchor anywhere inside a project folder and it resolves
that project automatically. Settings layer: built-in defaults, then the
environment `env.toml`, then the project `anchor.toml`, then `ANCHOR_*`
variables and flags. There is no `data_dir` key. Storage is structural.

For agents, one MCP server serves one environment (`anchor-mcp --env <name>`),
and project-scoped tools take an optional `project` argument. Crossing from one
environment to another is never an MCP operation. It is the human,
zone-confirmed `anchor project move`. A pre-existing `~/anchor-data` keeps
working as the default project until you run `anchor migrate`. See
[Environments and projects](../guides/environments-and-projects.md).

## Why `0.2.4` matters

`0.2.4` is the recommended version, especially on Windows. It fixes two ways a
config marker could be quietly ignored. A path value written with a leading `~`
was taken literally and created a `./~` folder instead of expanding to your home
directory; it now expands `~` and `$VAR` from every source. On Windows, the
config writer emitted the TOML marker in the system's legacy encoding (cp1252)
rather than UTF-8, so a single non-ASCII character corrupted the file for the
UTF-8 reader, which then ignored the config. The writer now always uses UTF-8,
and the reader recovers a file that was already written the old way, so
upgrading is enough. No re-init required.

## Why `0.2.3` matters

`0.2.3` upgrade from `0.2.2` if you tested it: that
wheel reported its version as `0.2.0` (`anchor version` read a hardcoded string),
which `0.2.3` fixes by reading the installed package metadata. `0.2.3` also makes
`anchor ingest` honor its documented idempotency — re-running on an
already-ingested document now skips the billed re-extraction instead of silently
recomputing and overwriting; pass `--force` to recompute. It closes a
data-boundary edge case (a missing `ANCHOR_OPENAI_API_KEY` could send document
pages to public OpenAI instead of your configured endpoint), quiets HuggingFace
and docling noise out of command output, and adds `anchor check` (verify your
data zone before ingesting) and `anchor canvas url`.

## Why `0.2.2` matters

`0.2.2` added the init flow, which configures an environment in one step: pick
the AI provider (and therefore the data zone: local, Ollama, OpenAI, Azure, or
any OpenAI-compatible endpoint), and ANCHOR writes a non-secret config. The CLI,
server, and an agent's `anchor-mcp` all resolve it, so a single `anchor install`
works for every project. Azure OpenAI users point ANCHOR at their `/openai/v1/`
endpoint. See [Configuration](configuration.md#azure-openai).

## Why `0.2.1` matters

Use `0.2.1` or newer for Windows testing. Version `0.2.0` can fail during PDF
ingestion when extracted document text contains Unicode characters that Windows
`cp1252` cannot encode. Version `0.2.1` writes document text and JSON artifacts
as UTF-8.

The `0.2.1` wheel also includes the frontend updates needed to show upload and
ingest progress on document cards, so users can see whether a PDF is queued,
being processed, failed, or completed.

## Installing a specific version

Latest release:

```bash
uv tool install anchor-kb
```

Specific version:

```bash
uv tool install anchor-kb==0.2.4
```

Upgrade an existing install:

```bash
uv tool install --force anchor-kb
```

## Source Checkout Versus PyPI

Install from PyPI when you want the latest released wheel.

Install from a local checkout only when testing changes that have been merged
to `main` but have not yet been released to PyPI. In that case, build the web
frontend first so the local wheel includes the UI:

```bash
pnpm --dir web install
pnpm --dir web build
uv tool install --force --reinstall --refresh .
```

Full release notes are kept in
[`CHANGELOG.md`](https://github.com/Novia-RDI-Seafaring/anchor/blob/main/CHANGELOG.md).
