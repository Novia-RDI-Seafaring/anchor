---
name: anchor
description: |
  Use this skill when the user works with engineering documents — datasheets,
  leaflets, manuals, P&ID drawings — and wants to ingest them into a
  source-grounded knowledge base, query the structured contents, or build a
  workspace canvas where every value points back to its source page + bbox.
  ANCHOR has its OWN extraction pipeline (docling layout + OCR → per-page
  markdown and images → structured regions with bboxes). So when the user says
  "ingest this PDF", "read / OCR this document", "extract the specs", "what does
  the leaflet say about X", "place that spec on the canvas", or "wire this value
  into a simulation", drive it through ANCHOR — do NOT install OCR/PDF libraries
  or write your own parsing code.
---

# ANCHOR — agent-first engineering knowledge canvas

ANCHOR turns a folder of engineering documents into a structured,
source-grounded knowledge base you can drive over MCP. Every value the
agent quotes points back to a specific page region.

## Use the pipeline — do not reinvent it

ANCHOR already does document extraction end to end. When the user wants a PDF
read, OCR'd, ingested, or its contents extracted, run **one command** —
`anchor ingest <pdf>` (CLI) or the `ingest_pdf` MCP tool — and read the result
with the query ops below. The pipeline is:

- **bronze** — docling layout analysis + OCR on the raw PDF
- **silver** — per-page markdown + page PNGs
- **gold** — structured regions (tables, specs, figures) each carrying a
  source `bbox`, the provenance every quoted value depends on

**Do NOT** `pip install` an OCR/PDF library (pytesseract, pdfplumber,
pdf2image, unstructured, …) or write your own parsing. That bypasses the gold
provenance ANCHOR exists to provide and duplicates work the tool already does.
If `anchor ingest` errors, fix the cause (run `anchor check` — endpoint, key,
model) rather than falling back to hand-rolled extraction.

## Install ANCHOR

Install the tool before using this skill:

```bash
uv tool install anchor-kb
# Fallback:
pipx install anchor-kb
```

`anchor install <harness>` registers an installed ANCHOR tool with an AI
harness. It does not install the tool itself.

Bronze and silver extraction run locally. Gold extraction requires
`ANCHOR_OPENAI_API_KEY`; set the other `ANCHOR_OPENAI_*` variables for your
provider as needed.

## When to use

- The user drops a PDF datasheet, leaflet, or manual and wants it readable.
- The user asks "what does this document say about X" or looks up specs.
- The user wants a spec table, document card, or region crop on a canvas.
- The user wires a datasheet value into a simulation (FMU).
- The user mentions a workspace folder or canvas.
- The user asks "where does this number come from?" — provenance is the
  whole point.

## Conventions

- **Always pass a `workspace_slug`.** ANCHOR is multi-canvas; create one
  per question or project (`canvas_create_workspace`) and reuse it.
- **Provenance is the contract.** When you place a spec value or quote a
  number, anchor it to its source via an edge carrying
  `data.kind = "evidence"` and `data.source_ref = {page, bbox}`. The
  system enforces this on `anchored` evidence edges.
- **Slug naming.** Document slugs are filename-derived (lowercase,
  hyphenated). Canvas slugs are user-chosen, e.g. `pump-analysis`.
- **Don't re-ingest.** `list_documents()` first; if the slug exists with
  `has_gold: true`, skip ingest unless the user asks for a fresh pass.

## Live state

The canvas has SSE. If a browser tab is open at the same time, the user
sees your changes appear live. The server is authoritative and serialises
commands per workspace, so you don't need to coordinate with the browser.

## Environments and projects

An **environment** is a named config profile (provider, models, data zone) and
the trust/egress boundary. It holds **projects**, each a corpus (documents) plus
its canvases. Environments live under `~/.anchor/envs/<name>/`; a project is
contained at `~/.anchor/envs/<name>/projects/<project>/` and inherits the
environment's config.

Over MCP, this server serves one environment. Project-scoped tools take an
optional `project` argument; omit it for the default project. Use
`list_projects` to see the options and `create_project` to make one. A
missing/unknown project returns a self-correcting error. You cannot cross to
another environment from here; that is a separate named server.

On the CLI, select with `--env` / `--project`, or set a session default with
`anchor use <env> <project>`. `ANCHOR_ENV` / `ANCHOR_PROJECT` also work.

### Set up an environment (agent-drivable, like `nvm install`)

`anchor init` (or `anchor env create <name>`) creates an environment and its
default project. Every choice is a flag, so no prompt blocks you:

```bash
# local-only (no document egress): no key, no endpoint
anchor init --yes --provider local

# a named endpoint (Azure shown): the deployment name is the model
anchor init work --yes --provider azure \
  --base-url https://<resource>.openai.azure.com/openai/v1/ \
  --vision-model <deployment> --embed-model text-embedding-3-small
```

`init` self-corrects an Azure URL missing `/openai/v1/`. The API key is never
written to the profile. Set `ANCHOR_OPENAI_API_KEY` in the environment or a
gitignored `.env` next to the profile. Then **verify before ingesting**:

```bash
anchor check --env <name>          # offline: data zone, repairs a bad endpoint
anchor check --env <name> --probe  # also one tiny call to confirm deployment + key
```

`anchor check` exits non-zero when something would break a real ingest, so you
can gate on it. Register the MCP with `anchor install claude-desktop --env <name>`.

## Where things live

A project's data lives under its environment:
`~/.anchor/envs/<env>/projects/<project>/`. Storage is structural (no
`data_dir` key). The default environment is in `~/.anchor/default`; a
pre-existing `~/anchor-data/` keeps working until `anchor migrate` folds it in.

- `bronze/` — raw PDFs
- `silver/<slug>/` — per-page markdown + page PNGs
- `gold/<slug>/` — structured regions with crops
- `canvases/<slug>/` — per-canvas durable state + events log

## Extensions

Each ingestion or simulation domain ships its own skill section
explaining its tools and a typical flow. The composer concatenates the
enabled extensions below this section so you see only what's available
in the current install.
