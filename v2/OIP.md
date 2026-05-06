# OIP — Open Ingestion Protocol

**Version:** 0.1 (draft) · **Status:** proposed · **Maintainer:** Anchor project, intended as a vendor-neutral standard

## What this is

**OIP** is a small, governance-neutral specification for **ingestion tools that produce structured, source-grounded knowledge**. Any tool that conforms to OIP can be consumed by any OIP-aware application, the same way any LSP-compliant language server works in any LSP-aware editor.

OIP is *not* an Anchor-specific format. Anchor is the first reference consumer, and Anchor's PDF medallion pipeline is the first reference producer; both can be replaced. The point of OIP is interop: a transcription tool, a code-region extractor, a web crawler, a mailbox indexer — none of them need to import each other or import Anchor. They just need to conform to OIP.

## Why this exists

Engineering knowledge lives in too many shapes — datasheets, audio recordings, source code, web pages, P&IDs, emails. Today every "ingest this and make it queryable" tool reinvents:
- where to put the structured output
- how to address regions back to their source
- how to expose ingest/list/get operations
- how to declare what kinds of artefacts it produces

OIP nails these down so producers and consumers can mix freely.

## Conforming roles

- **Producer** — a tool that ingests source material (files, URLs, audio streams, etc.) and writes OIP-compliant artefacts to disk.
- **Consumer** — a tool that reads OIP-compliant artefacts and offers them to users / agents (a UI, an MCP server, a search index).

A single tool can be both. Anchor's PDF extension is a producer (it writes gold/silver) and Anchor's canvas is a consumer (it renders gold regions).

## The artefact tree on disk

A producer writes to a base directory whose path is configurable. Inside it, the layout is fixed:

```
<oip-data-dir>/
├── manifest.json           # producer metadata (this file IS the OIP advertisement)
├── sources/<slug>/         # the original input, immutable
│   └── <filename>          # .pdf, .mp3, .zip, .html, etc.
└── artefacts/<slug>/
    ├── document.json       # canonical metadata for the ingested doc
    ├── regions.json        # all addressable regions in this document
    ├── content/            # cropped/extracted content per region
    │   ├── <region-id>.png
    │   ├── <region-id>.svg
    │   ├── <region-id>.md
    │   └── <region-id>.txt
    └── _producer/          # producer-specific extras (out of OIP scope)
```

Producers are free to add additional files inside `_producer/` or in parallel siblings; consumers must ignore anything they don't recognise.

Anchor's existing `bronze/silver/gold/` is one specific producer's substrate; the OIP-conformant view of it is the gold layer projected through `manifest.json` + `document.json` + `regions.json`.

## `manifest.json`

Every producer MUST write this file at the root of its data dir. It declares who the producer is, what it produces, and how to invoke it.

```json
{
  "oip_version": "0.1",
  "producer": {
    "name": "anchor-pdfs",
    "display_name": "Anchor PDFs",
    "version": "0.2.0",
    "homepage": "https://github.com/Novia-RDI-Seafaring/anchor-kb-ui-RAG"
  },
  "data_dir": "/abs/path/to/this/data/dir",
  "produces": {
    "source_kinds": ["application/pdf"],
    "region_kinds": ["table", "spec_block", "chart", "diagram", "figure", "text"],
    "source_ref_kinds": ["pdf-page-bbox"]
  },
  "invocation": {
    "kind": "mcp-stdio",
    "command": "anchor-mcp",
    "args": ["--data-dir", "/abs/path/to/this/data/dir"],
    "tools_namespace": "pdf"
  },
  "ui_hints": {
    "node_types": [
      { "name": "pdf:document", "renders": "document" },
      { "name": "pdf:spec_table", "renders": "regions where kind=spec_block" }
    ],
    "edge_styles": {
      "pdf:evidence": { "stroke": "#FF8E2B", "dasharray": "4 4" }
    },
    "source_ref_handlers": {
      "pdf-page-bbox": "open the PDF at the given page, draw the bbox"
    }
  }
}
```

Required keys: `oip_version`, `producer.name`, `producer.version`, `data_dir`, `produces`, `invocation`. `ui_hints` is optional; OIP-aware UIs (like Anchor) read it; pure-data consumers ignore it.

## `document.json`

Per-document metadata at `<data-dir>/artefacts/<slug>/document.json`:

```json
{
  "slug": "alfa-laval-lkh-centrifugal-pump",
  "title": "Alfa Laval LKH Centrifugal Pump",
  "source_kind": "application/pdf",
  "source_path": "sources/alfa-laval-lkh-centrifugal-pump.pdf",
  "source_url": null,
  "ingested_at": "2026-05-06T12:00:00Z",
  "ingested_by": "anchor-pdfs/0.2.0",
  "size_units": { "page_count": 4 },
  "tags": [],
  "extras": { }
}
```

`size_units` is keyed by what makes sense for the medium (`page_count` for PDFs, `duration_ms` for audio, `loc_count` for code, etc.).

## `regions.json`

A list of addressable regions:

```json
[
  {
    "id": "alfa-laval-lkh-centrifugal-pump:p2:r1-spec-lkh5",
    "kind": "spec_block",
    "title": "Operating data — LKH-5",
    "description": "Inlet pressure, flow, head, temperatures for LKH-5 at 50 Hz",
    "source_ref": {
      "kind": "pdf-page-bbox",
      "page": 2,
      "bbox": [42, 720, 295, 612]
    },
    "content": {
      "markdown": "content/r1-spec-lkh5.md",
      "image": "content/r1-spec-lkh5.png",
      "data": { "Max inlet pressure": "600 kPa", "Max flow": "30 m³/h", "...": "..." }
    },
    "tags": ["operating_limits"],
    "entities": ["mentions:lkh-5"]
  }
]
```

Required keys per region: `id`, `kind`, `source_ref`. `content` contains paths (relative to `<data-dir>/artefacts/<slug>/`) for each available representation; consumers pick what they understand.

`source_ref.kind` is open-ended — registered by the producer in `manifest.json/produces.source_ref_kinds` and accompanied by whatever address fields make sense for that kind. Conventional kinds:

| `kind` | Address fields | Used by |
|---|---|---|
| `pdf-page-bbox` | `page` (int), `bbox` (`[l, t, r, b]` BOTTOMLEFT) | PDF producers |
| `audio-timestamp` | `source_url`, `start_ms`, `end_ms` | Transcription producers |
| `video-timestamp` | `source_url`, `start_ms`, `end_ms`, `track?` | Video producers |
| `code-line-range` | `path`, `start_line`, `end_line`, `language?` | Code producers |
| `web-snapshot` | `url`, `snapshot_sha`, `xpath?` | Web crawlers |

New kinds are fine; producers SHOULD prefix domain-specific kinds (`yourtool-foo-bar`) to avoid collision.

## MCP surface (the `invocation`)

A producer's MCP server SHOULD expose at least:

```
<namespace>.ingest(input)         → { slug, summary }
<namespace>.list_documents()      → [ document.json[]… ]
<namespace>.get_document(slug)    → document.json
<namespace>.get_regions(slug, kind?) → regions.json subset
<namespace>.get_region_content(region_id, format) → text | base64-bytes | url
```

`<namespace>` matches `manifest.json/invocation.tools_namespace` (`pdf` for Anchor PDFs, `transcribe` for a transcription tool, etc.). Every consumer prefixes the namespace when listing tools so multiple producers compose without name collisions.

## Discovery

A consumer finds OIP producers in three ways, in order:

1. **`anchor.toml` per data-dir** — explicit list, highest priority
2. **`~/.config/oip/producers.d/*.json`** — system-wide registrations (any producer can drop a manifest here; multiple consumers see them all)
3. **Walk the data-dir** — if the data-dir contains a `manifest.json` with `oip_version`, that's a producer

A producer's installer SHOULD write its manifest to `~/.config/oip/producers.d/<name>.json`. The user MAY also register manually:

```bash
anchor extensions add /path/to/some-producer/manifest.json   # registers that producer
oip-cli register /path/to/manifest.json                       # equivalent if there's a generic CLI
```

## What OIP doesn't specify

- **Embeddings / search indexes** — out of scope; consumers build their own indices from `content/` and `regions.json`.
- **Authentication** — local-first by default; if a producer wants auth, it ships its own MCP server with auth handling. OIP doesn't mandate it.
- **Rendering** — `ui_hints` is advisory. A pure-data consumer (an indexer, a CLI) ignores it.
- **Transport** — MCP is the SHOULD; HTTP, gRPC, named pipes are NOT-SHALL-NOTed. Future versions may add `invocation.kind = "http"`, etc.
- **Provenance verification** — OIP carries source refs; verifying that `bbox` actually contains what the producer claims is the consumer's job. (Anchor's "every value points to its source page" property is a *consumer behaviour*, not an OIP guarantee.)

## Versioning

`oip_version` follows semver. Backwards-incompatible changes bump the major. Consumers MUST refuse to read a manifest whose major exceeds the consumer's supported major; consumers SHOULD read older minors. Producers SHOULD declare the minimum consumer version they require if they use newer optional fields.

## Reference implementations

- **Producer:** `anchor-pdfs` (this repo). Writes manifest to `<data-dir>/manifest.json` at first run; follows the disk layout above starting v0.3 (today's `bronze/silver/gold/` is the producer-specific layout under `_producer/`).
- **Consumer:** Anchor's canvas. Discovers manifests via `anchor extensions list`, aggregates MCP tools across producers, displays regions with `ui_hints` styling.

## Why this is worth doing

Until something like OIP exists, every "agent + structured docs" tool is its own walled garden. The transcription app you wrote, the PDF parser you forked, the code-region extractor you might build — they don't compose. With OIP they do, and the canvas in front of them is a separate thing that any consumer can replace.

Anchor's bet: get OIP defined and demonstrated; the canvas wins by being the best consumer; producers proliferate independently.

---

*This is a draft. The protocol stabilises at 1.0 once a second producer (transcription) and at least one external consumer have been implemented end-to-end. Comments and divergent implementations welcome — `oip_version` is meant to be community-versioned, not Anchor-versioned.*
