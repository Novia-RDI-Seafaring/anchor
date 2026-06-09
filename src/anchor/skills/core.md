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

## Projects: a folder is the unit

A folder containing an `anchor.toml` (created by `anchor init`) is an ANCHOR
project. It declares the data dir, the AI provider/data-zone, and the models.
**Run ANCHOR from inside that folder** and every adapter resolves the project
automatically — the CLI and `anchor serve` walk up from the working directory
to find `anchor.toml`; `anchor-mcp` does the same, or name it explicitly with
`anchor-mcp --project <folder>`. So a single MCP registration
(`anchor install claude-code`, no `--data-dir`) works for *every* project: open
the agent in the project folder and it targets that project — no reinstall.

If you are unsure which project is active, run `anchor` from the folder you mean
(or pass `--project`/`ANCHOR_CONFIG`). Don't pass `--data-dir ~/anchor-data`
unless you specifically want the global default rather than the current project.

### Set up a project (agent-drivable, like `npm init` / `uv init`)

You can scaffold ANCHOR in any folder non-interactively — `anchor init` accepts
every choice as a flag, so no prompt blocks you:

```bash
# local-only (no document egress): no key, no endpoint
anchor init . --yes --provider local

# a named endpoint (Azure shown): the deployment name is the model
anchor init . --yes --provider azure \
  --base-url https://<resource>.openai.azure.com/openai/v1/ \
  --vision-model <deployment> --embed-model text-embedding-3-small
```

`init` self-corrects an Azure URL that is missing `/openai/v1/`. The API key is
never written to `anchor.toml` — set `ANCHOR_OPENAI_API_KEY` in the environment
or a gitignored `.env` in the folder. Then **verify before ingesting**:

```bash
anchor check            # offline: prints the data zone, repairs a bad endpoint
anchor check --probe    # also makes one tiny call to confirm deployment + key
```

`anchor check` exits non-zero when something would break a real ingest, so you
can gate on it. Register the MCP once with `anchor install claude-code`.

## Where things live

Each project's data lives in its own `data_dir` (default `<project>/anchor-data/`
from `anchor init`, or the global `~/anchor-data/` when no project is found).
`ANCHOR_DATA_DIR` or an explicit `--data-dir <path>` override it; the HTTP
adapter uses the path passed to `anchor serve`.

- `bronze/` — raw PDFs
- `silver/<slug>/` — per-page markdown + page PNGs
- `gold/<slug>/` — structured regions with crops
- `canvases/<slug>/` — per-canvas durable state + events log

## Extensions

Each ingestion or simulation domain ships its own skill section
explaining its tools and a typical flow. The composer concatenates the
enabled extensions below this section so you see only what's available
in the current install.
