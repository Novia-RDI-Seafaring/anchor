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
| `0.2.8` | 2026-06-23 | Ingest fix. A fresh install resolved a newer RapidOCR that, with no ONNX runtime present, fell back to a torch OCR engine whose default model does not exist, so ingest died with `Unsupported configuration: torch.PP-OCRv6.det.small`. ANCHOR now depends on `onnxruntime` and pins docling's OCR to that backend, so PDF ingestion works on a clean install again. Recommended for anyone on 0.2.5–0.2.7 who hit an OCR error. |
| `0.2.7` | 2026-06-22 | Safer onboarding. `anchor init` no longer invents an environment silently. The environment is the trust boundary, so the first time you init a project, it asks you to pick a provider (your data zone) right in the terminal, accepts `--provider` to provision inline (scriptable), or points you at `anchor env create` when run unattended. Egress is always an explicit choice. Behavior change for scripts that relied on the old silent `local` default. |
| `0.2.6` | 2026-06-22 | Environments and projects. An environment is a named configuration profile (provider, models, data zone) and the trust boundary. A project is a folder bound to one environment, with its corpus in a hidden `.anchor_data/`. `anchor env create <name>` is the provider picker; `anchor init` in a folder starts a project there and self-creates a local, zero-egress environment on a fresh machine. One MCP server serves one environment and addresses projects by a per-call name. A pre-existing `~/anchor-data` keeps working until `anchor migrate` folds it in. |
| `0.2.5` | 2026-06-17 | Grounding and harness-ingest release. Preserves table-cell provenance when Docling supplies cell coordinates, restores row source buttons on populated spec tables, adds the harness-driven gold-ingest path, improves live canvas event sync, warms the local embedding model before the first search, fixes Claude Code MCP registration, and includes the frontend `protobufjs` audit override. Recommended for anyone using `anchor init`, row-level provenance, local embedding search, or agent-driven PDF ingest. |
| `0.2.4` | 2026-06-11 | Config robustness for cross-platform onboarding. A `data_dir` with a leading `~` now expands to `$HOME` instead of creating a literal `./~` folder. On Windows, `anchor init` no longer writes `anchor.toml` in a non-UTF-8 locale encoding that the reader then rejected and silently ignored; the reader also recovers an already-corrupted file. Recommended for anyone on Windows or using a `~`-relative `data_dir`. |
| `0.2.3` | 2026-06-10 | Azure + agent-experience hardening. `anchor version` / `--version` report the real installed version (was stuck at `0.2.0`). `anchor ingest` is idempotent (skips when gold exists; `--force` to recompute). New `anchor canvas url` and `anchor check`; HuggingFace/docling noise no longer pollutes `search` / `ingest` output. Fixes a data-egress edge case where a missing key could route document pages to public OpenAI, and `anchor init` self-corrects an Azure endpoint. |
| `0.2.2` | 2026-06-09 | Onboarding release. The init flow configures the AI provider / data zone and models, and one MCP registration serves every project. Azure OpenAI works via its v1 endpoint; docling auto-selects CUDA or CPU; `anchor serve` falls through to a free port. |
| `0.2.1` | 2026-06-08 | Patch release for public testing. It includes the Windows Unicode ingest fix, canvas ingest progress feedback, timing reports, canvas deletion, improved region overlays and updated MCP setup docs. |
| `0.2.0` | 2026-05-25 | First public release of the v2 local canvas, PDF ingestion, MCP server, CLI, HTTP API and bundled web UI. |

## Why `0.2.8` matters

`0.2.8` fixes PDF ingestion on a clean install. ANCHOR uses docling for layout
and OCR, with RapidOCR underneath. docling's default OCR options let RapidOCR
auto-pick its engine. A fresh `uv tool install` now resolves RapidOCR 3.x, and
because no ONNX runtime was installed (torch is present for the layout model),
RapidOCR fell back to its torch engine, whose default PP-OCRv6 model is not
shipped — so the first ingest crashed with `Unsupported configuration:
torch.PP-OCRv6.det.small`. Earlier installs avoided this only because they
happened to resolve an older RapidOCR that bundled the ONNX runtime.

The fix declares `onnxruntime` as a dependency and pins docling's OCR to the
onnxruntime backend, so ingestion is deterministic across fresh installs.
Upgrading is enough; no config change needed.

## Why `0.2.7` matters

`0.2.7` makes the data-zone choice explicit at the moment it matters. In `0.2.6`,
running `anchor init` on a fresh setup quietly created a `local` environment for
you. That was safe (nothing left your machine), but it made the most important
decision (where may my documents go?) without asking, and it meant the silent
default produced no LLM extraction, which surprised people.

Now `anchor init` never invents a trust boundary. If no environment exists yet:

- on a terminal, it prompts the provider picker (`local`, `ollama`, `openai`,
  `azure`, `custom`, `harness`) and creates that environment before binding;
- with `--provider` (and optional `--base-url` / `--vision-model` /
  `--embed-model`), it provisions the environment inline, no prompt, so scripts
  and CI stay one command;
- unattended with neither, it stops with a clear message pointing at
  `anchor env create <name>` or `--provider`.

Migration: a script that relied on a bare `anchor init` standing up `local`
should now pass `anchor init --provider local --yes`, or run
`anchor env create local` once up front. Interactive users just answer one
question. See
[Environments and projects](../guides/environments-and-projects.md).

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

## Why `0.2.5` matters

`0.2.5` is the recommended version for current testers. It includes the
project setup fixes from `0.2.4` and adds the recent provenance and harness
ingest work. If Docling exposes table-cell coordinates, ANCHOR keeps them
through ingest so row-level source buttons can highlight the selected value,
not just the page or table. The release also restores row source buttons on
agent-populated spec tables, adds the harness-driven ingest path for projects
where the agent performs vision extraction, fixes live canvas event updates,
warms the local embedding model before the first search, and registers Claude
Code MCP config in the file Claude Code reads.

## Why `0.2.4` matters

`0.2.4` was the Windows configuration fix release. It fixes two ways a
project's `anchor.toml` could be quietly ignored. A `data_dir` written with a
leading `~` (such as `~/anchor-data`) was taken literally and created a `./~`
folder inside the project instead of expanding to your home directory; it now
expands `~` and `$VAR` from every source. On Windows, `anchor init` wrote
`anchor.toml` in the system's legacy encoding (cp1252) rather than UTF-8, so a
single non-ASCII character corrupted the file for the UTF-8 reader, which then
fell back to the global data dir without using your project config. The writer
now always uses UTF-8, and the reader recovers a file that was already written
the old way, so upgrading is enough. No re-`init` required.

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
uv tool install anchor-kb==0.2.6
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
