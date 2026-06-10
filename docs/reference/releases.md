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
| `0.2.3` | 2026-06-10 | Azure + agent-experience hardening. `anchor version` / `--version` report the real installed version (was stuck at `0.2.0`). `anchor ingest` is idempotent (skips when gold exists; `--force` to recompute). New `anchor canvas url` and `anchor check`; HuggingFace/docling noise no longer pollutes `search` / `ingest` output. Fixes a data-egress edge case where a missing key could route document pages to public OpenAI, and `anchor init` self-corrects an Azure endpoint. |
| `0.2.2` | 2026-06-09 | Onboarding release. `anchor init` configures a project folder (AI provider / data zone, models, data dir) and writes `anchor.toml`; one MCP registration serves every project. Azure OpenAI works via its v1 endpoint; docling auto-selects CUDA or CPU; `anchor serve` falls through to a free port. |
| `0.2.1` | 2026-06-08 | Patch release for public testing. It includes the Windows Unicode ingest fix, canvas ingest progress feedback, timing reports, canvas deletion, improved region overlays and updated MCP setup docs. |
| `0.2.0` | 2026-05-25 | First public release of the v2 local canvas, PDF ingestion, MCP server, CLI, HTTP API and bundled web UI. |

## Why `0.2.3` matters

`0.2.3` is the recommended version. Upgrade from `0.2.2` if you tested it: that
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

`0.2.2` is the recommended version for new users. It adds `anchor init`, which
configures a project folder in one step — pick the AI provider (and therefore
the data zone: local, Ollama, OpenAI, Azure, or any OpenAI-compatible endpoint),
and ANCHOR writes `anchor.toml`. The CLI, server, and an agent's `anchor-mcp`
all resolve that project, so a single `anchor install` works for every project.
Azure OpenAI users point ANCHOR at their `/openai/v1/` endpoint — see
[Configuration](configuration.md#azure-openai).

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
uv tool install anchor-kb==0.2.1
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
