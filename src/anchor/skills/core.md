---
name: anchor
description: |
  Use this skill when the user works with engineering documents — datasheets,
  leaflets, manuals, P&ID drawings — and wants to ingest them into a
  source-grounded knowledge base, query the structured contents, or build a
  workspace canvas where every value points back to its source page + bbox.
  Anchor exposes ingestion + workspace tools over MCP, so call this skill when
  the user says "ingest this PDF", "what does the leaflet say about X", "place
  that spec on the canvas", "wire this value into a simulation", or otherwise
  works with a folder of technical PDFs.
---

# ANCHOR — agent-first engineering knowledge canvas

ANCHOR turns a folder of engineering documents into a structured,
source-grounded knowledge base you can drive over MCP. Every value the
agent quotes points back to a specific page region.

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

## Where things live

Configured at install time. Default `~/anchor-data/`:

- `bronze/` — raw PDFs
- `silver/<slug>/` — per-page markdown + page PNGs
- `gold/<slug>/` — structured regions with crops
- `canvases/<slug>/` — per-canvas durable state + events log

## Extensions

Each ingestion or simulation domain ships its own skill section
explaining its tools and a typical flow. The composer concatenates the
enabled extensions below this section so you see only what's available
in the current install.
