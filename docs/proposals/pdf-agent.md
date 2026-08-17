# Proposal: pdf_agent, a source-grounded PDF ingestion and retrieval package

## Status

Draft for later implementation planning.

## Goal

`pdf_agent` turns unstructured PDFs into searchable, source-grounded documents,
then lets an agent retrieve relevant evidence with a precise anchor to the
original PDF.

## Approach

The general idea: convert each unstructured PDF into a structured, layered
representation, Bronze, Silver, and Gold, then ingest and retrieve against
that structured representation. Concretely, `pdf_agent` has two jobs:

1. Ingest a PDF into a searchable document representation whose text, tables,
   images, and reading order remain tied to exact locations in the original
   PDF.
2. Retrieve relevant evidence from those documents, returning usable context
   together with page- and bbox-level anchors back to the original PDF.

Silver is the complete, extractor-independent, source-grounded document layout
that makes exact anchoring possible. Gold is the semantic representation used
to find relevant evidence, and embeddings and a lexical (BM25) index are
regenerable indices over Gold.

The layers have distinct jobs:

- Bronze preserves the submitted PDF unchanged.
- Silver records the physical document: text, bboxes, kinds, pages, and reading
  order.
- Gold groups one or more Silver regions into one searchable semantic unit with
  a title, a two- to three-sentence retrieval description, and optional tags
  and entities.
- Search ranks Gold units by fusing embedding similarity over the Gold
  description with BM25 lexical match over the unit's raw Silver text, then
  loads their referenced Silver regions as the actual agent or user context.

Each final Silver region belongs to exactly one Gold unit. A Gold unit may
represent one region, connected paragraphs, a figure or table with its caption,
or another coherent context. Silver supplies the source text, geometry, and
table cells.

Documents are independent layout and Gold namespaces. Regions use deterministic
document-local IDs such as `p3-r12`. Cross-document references contain the
document slug and region ID; the ID encodes its page and the layout manifest
maps that page to its layout file.

## Artifact layout

`pdf_agent` owns one configured artifact root. Every command uses that root;
that root contains the package's Bronze, Silver, and Gold artifacts.

```text
pdf-agent --data-dir <root> <command>
pdf-agent-mcp --data-dir <root>
```

The following layout lives below that root:

```text
bronze/
  <filename>.pdf                       # immutable submitted source evidence
silver/
  <slug>/
    detected/                           # pre-final detection and harness-curation artifacts
      <n>.png                           # clean rendered page for display and bbox clipping
      <n>.json                           # complete canonical per-page layout, normalized from extractor-native output
      <n>.suppression.json               # deterministic containment decisions for page n
      <n>.masked.json                    # retained harness work-item input when debug artifacts are kept
      <n>.overlay.png                   # retained work-item overlay when debug artifacts are kept
      <n>.corrections.json               # accepted harness overrides to Silver regions for page n
      <n>.gold_draft.json                # accepted draft Gold units for page n
    layout.json                         # document manifest: order, ID index, page files
    layout/                             # final page-scoped Silver layout
      <n>.json                          # final curated Silver regions for page n
      <n>.overlay.png                  # retained final overlay when debug artifacts are kept
gold/
  <slug>/
    manifest.json                       # document fingerprint, page-file index, and status
    units/                              # page-scoped Gold semantic units
      <n>.json                          # semantic units referencing page n's retained region IDs
    embeddings.json                     # regenerable vectors for all document Gold units
documents.json                          # project catalog of document status and metadata
manifest.json                           # OIP producer manifest (see OIP export)
artefacts/
  <slug>/
    document.json                       # OIP document metadata, compiled
    regions.json                        # OIP regions, one per Gold unit, compiled
    content/
      <region-id>.md                    # reconstructed text for one exported region
      <region-id>.json                  # that region's table cells, when applicable
      <region-id>.png                   # crop of the region's union bbox
```

The page-scoped files are intentional: they are the practical unit for human
inspection and debugging. The clean page image supports display and clipping a
region bbox into evidence. `layout.json` is the compact document-level manifest
for ordered navigation and page-file lookup.

`--keep-debug-artifacts` persists the masked harness work-item input plus its
overlay and the final overlay shown above.

## Pipeline

1. Preserve the source PDF in Bronze.
2. Extract and normalize detected layout regions per page, including full text,
   geometry, and stable detected-region IDs.
3. Compute and persist deterministic containment suppression for each page.
4. Exclude suppressed regions, derive a bounded masked work-item view, render
   an overlay of the retained regions, and open a durable harness-ingestion
   session. The installed package skill directs the image-capable harness agent
   to inspect each page and submit two artifacts, both keyed by retained
   detected-region ID: overrides to Silver regions and draft Gold units.
5. Persist accepted harness corrections separately from the suppression result,
   then combine detected layout, suppression, and corrections to compile and
   persist that page's final Silver layout.
6. Validate the draft Gold units against that final Silver layout and persist
   the page-scoped Gold units with the same retained region IDs.
7. After every required page is accepted, assemble the document-level Silver
   and Gold manifests, embed deterministic retrieval text and assemble each
   unit's lexical (BM25) text derived from the persisted Gold and Silver data,
   and mark the document complete.

The per-page dependency is:

```text
normalized layout -> deterministic suppression -> retained work item -> harness page review
                                                                      |-> corrections -> compile final Silver
                                                                      |-> draft Gold groups -----+
                                                                                                   -> validate retained IDs
                                                                                                      -> persist page Gold

accepted page layouts + units -> ingest_finalize -> document manifests + embeddings + lexical text + complete marker
```

## Specifications

### 1. Bronze source

`bronze/<filename>.pdf` is the original uploaded byte stream. Its metadata must
record at least filename, checksum, ingest time, and the selected extractor.
Bronze is immutable source evidence.

### 2. `detected/<n>.json`

Each `detected/<n>.json` file is the complete canonical page layout before
curation. The extractor adapter maps its page result into the stable schema
below while retaining the full detected text. All later pipeline stages consume
this normalized form.

For one layout version, normalization has these invariants:

- `id` is `p<page>-r<region>`. `page` identifies the page and `region` is the
  detector-inferred, page-local reading-order number. The normalizer assigns
  region numbers in that order. The ID is stable through suppression, harness
  curation, Silver compilation, and Gold grouping.
- The region number in `id` is the default reading order. A harness correction
  writes a separate `reading_order` override while the ID remains stable.
- `bbox` uses Docling's four-number page-coordinate representation, including
  its coordinate origin and ordering.
- `kind` is mapped into the normalized taxonomy defined below.

Each re-extraction produces a layout version. IDs are stable within that
version, and the harness names those IDs in all corrections and Gold groups.

```json
{
  "schema_version": 1,
  "regions": [
    {
      "id": "p3-r12",
      "kind": "paragraph",
      "bbox": [72.0, 610.0, 520.0, 665.0],
      "text": "The pump operates ..."
    }
  ]
}
```

The normalized taxonomy is:

```text
heading, paragraph, list, table, figure, diagram, caption, equation,
header_footer, other
```

### 3. `detected/<n>.suppression.json`

Each page-level `detected/<n>.suppression.json` records only deterministic
containment decisions over that page's detected-region IDs. It is derived from
`detected/<n>.json`, has no harness-authored fields, and can be regenerated
whenever that detected layout changes.

```json
{
  "schema_version": 1,
  "suppressed": [
    {
      "id": "p3-r13",
      "contained_by": "p3-r12",
      "contained_area_ratio": 0.97
    }
  ]
}
```

Deterministic code adds a region to `suppressed` when the intersection of its
bbox with another detected region of equal or larger area covers at least 90%
of the first region's bbox area. It chooses the largest qualifying containing
region; ties use the stable detected-region ID. The record identifies the
containing region and measured ratio so the decision is inspectable.

The package applies suppression before creating `detected/<n>.masked.json` or
its overlay, below. Both work-item artifacts contain only the retained regions
selected for harness curation.

### 4. `detected/<n>.masked.json`, `detected/<n>.overlay.png`, and the harness curation work order

These are the harness's input for one page: everything it reads before it
writes anything back.

`detected/<n>.masked.json` is a deterministic, token-bounded projection of
the retained regions in that page's detected JSON, after suppression has been
applied. It contains each region's ID, current kind, and the first 10
characters of its `text` field. It omits full text, bboxes, and all other
extractor detail.

```json
{
  "regions": [
    {
      "id": "p3-r12",
      "kind": "paragraph",
      "text": "The pump o"
    }
  ]
}
```

`pdf_agent` uses the connected harness's image capability for semantic
curation. The package creates a page work order; its installed skill tells the
harness agent how to read that work order, inspect the page image, and submit
the constrained result. The work order contains:

- an image of the page with retained detected regions overlaid, including each
  detected-region ID and kind;
- `detected/<n>.masked.json` for that page;
- the constrained response schema and task instructions.

The short text prefix lets the harness agent match an overlay label to its JSON record
while keeping the correction input small.

Each overlay label uses the compact form `<detected_region_id> <kind>`, for
example `p3-r12 paragraph`. The region number in the stable ID is the default
page-local reading order. A harness correction names the same ID and supplies
only a `reading_order` override when that order is wrong.

`--keep-debug-artifacts` retains `masked.json` and the work-item overlay so a
human can inspect the exact harness-curation input.

One skill-directed harness page review of this work order produces two
artifacts, described next: overrides to Silver regions
(`detected/<n>.corrections.json`) and draft Gold units
(`detected/<n>.gold_draft.json`), both keyed to the stable detected-region IDs
retained through compilation.

### 5. `detected/<n>.corrections.json`

Each page-level `detected/<n>.corrections.json` records the accepted
harness-authored overrides to retained Silver regions: kind and reading-order
corrections only. It captures visual judgment about a region's own kind or
position, not semantic grouping — Gold units are a separate artifact, below.

```json
{
  "schema_version": 1,
  "overrides": [
    {"id": "p3-r12", "kind": "diagram"},
    {"id": "p3-r14", "reading_order": 48}
  ]
}
```

The harness supplies kind and reading-order overrides. A `reading_order` override
may be any number, including fractional, not only one already in use on that
page: a value below the page's current minimum moves a region to the front, a
value above the current maximum moves it to the back, and a value between two
neighbors, fractional if they are adjacent integers, moves it between them.
Repositioning one region therefore updates only that region's override.

The package writes this file only once the submitted overrides pass
validation; see "Validating and persisting a page submission," below.

### 6. `detected/<n>.gold_draft.json`

Each page-level `detected/<n>.gold_draft.json` records the harness-authored
draft Gold units for that page's retained Silver regions: a title,
description, and optional tags and entities, each grouped by
`detected_region_ids`. The description contains two to three sentences that
name the content, quantities, and entities needed to find the unit through
embedding search. It is draft data — it becomes authoritative only once it
passes the partition check described below and is persisted as
`gold/<slug>/units/<n>.json`.

```json
{
  "schema_version": 1,
  "gold_units": [
    {
      "detected_region_ids": ["p3-r12", "p3-r14"],
      "title": "Cleaning-in-place operating requirements",
      "description": "Cleaning-in-place temperature, duration, and chemical-concentration requirements for the LKH pump range. Includes operating limits and procedure values used to configure a CIP cycle.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

The package writes this file only once the submitted units pass the first
validation stage below; the partition check that promotes them to
`gold/<slug>/units/<n>.json` is separate and may still fail.

### 7. Validating and persisting a page submission

A page submission carries both artifacts above — overrides and draft Gold
units — through two independent validation stages before anything is
persisted as final Silver or Gold.

The first stage validates each artifact against its own closed schema: every
required field present with the required type, no unknown fields, and titles,
descriptions, tags, entities, and override values satisfying their field
constraints. A description must contain two to three descriptive sentences
that identify the unit's subject matter, quantities, and entities for embedding
retrieval. Every override's `id` and every Gold unit's `detected_region_id`
must identify a retained region on this page. Duplicate or conflicting
overrides are rejected. A rejected submission leaves the previously accepted
`corrections.json` and `gold_draft.json` unchanged. Validation returns a
structured, actionable error for each failed field or region reference,
including its JSON path, error code, and the repair required; the skill uses
this response to correct and resubmit the same page.

Once the first stage passes, the server persists `detected/<n>.corrections.json`
and `detected/<n>.gold_draft.json`, then combines the detected layout,
suppression, and corrections to compile that page's final Silver layout.

The second stage checks the draft Gold units against that compiled page. A
Gold unit may contain one or many retained Silver regions, but every retained
Silver region must appear in exactly one Gold unit's `detected_region_ids`.
Unknown or suppressed IDs, missing Silver regions, and Silver regions repeated
within or across Gold units are all validation errors. The submitted Gold
units must therefore form an exact, non-overlapping partition of the retained
Silver regions.

When that partition check fails, the server returns informative errors. Each
error identifies the failed JSON path, a machine-readable code, and the repair
needed; aggregate missing and duplicated region lists make the correction set
explicit:

```json
{
  "accepted": false,
  "errors": [
    {
      "path": "gold_units[1].detected_region_ids[0]",
      "code": "duplicate_region_id",
      "message": "p3-r14 is already assigned to gold_units[0]"
    }
  ],
  "missing_region_ids": ["p3-r15"],
  "duplicated_region_ids": []
}
```

Overrides already accepted in `corrections.json` stand; only
`detected/<n>.gold_draft.json` is re-requested. The server re-issues the same
work order for that page so the harness can resubmit corrected Gold units.
After a small bounded number of failed attempts (for example, three), the page
records a terminal error naming the unresolved regions, visible through
`get_ingest_status`.

Only once the partition is valid does the server write
`gold/<slug>/units/<n>.json` from the accepted `gold_draft.json`.

### 8. `layout.json` and `layout/<n>.json`

`layout.json` is a compact document-level manifest. Its `order` array is the
single canonical document-wide reading order of retained detected-region IDs;
an ID's position in that array is its order. The page component of each ID
selects an entry in `pages`, which maps that page to its final layout file.
`layout/<n>.json` contains that page's final curated regions, in the same
relative reading order. This keeps inspection page-scoped while the manifest
supports direct context queries across page boundaries.

When `--keep-debug-artifacts` is set, render `layout/<n>.overlay.png` from the
clean page image and the final regions. It uses the retained detected IDs and
final labels, so it can be compared directly with the work-item overlay during
debugging.

```json
{
  "schema_version": 1,
  "layout_fingerprint": "sha256:...",
  "pages": {"3": "layout/3.json"},
  "order": ["p3-r12", "p3-r14", "p3-r15"]
}
```

Each page layout file has this shape; the page is implied by its path and by
every region's id, so it is not repeated as a field:

```json
{
  "regions": [
    {
      "id": "p3-r12",
      "kind": "paragraph",
      "bbox": [72.0, 610.0, 520.0, 665.0],
      "text": "The pump operates ..."
    }
  ]
}
```

Final Silver retains the detected-region IDs. Neighboring context is resolved
by locating an ID in `layout.json`'s `order` array and taking adjacent entries,
including across page boundaries.

The compiler gives each retained region an effective order: its harness
`reading_order` override when one was supplied, otherwise the region number in
its ID. It sorts retained regions by page, then by effective order within the
page, breaking ties by the stable detected-region ID. Suppressed regions are
dropped before sorting, and `order` is a positional array: a region's rank is
its index in that array. Sorting page-first keeps each page's curation result
within that page.

The compiler atomically replaces a page's layout file the moment that page is
accepted, with suppressed regions omitted. Once every page is accepted,
`ingest_finalize` atomically writes the document-level manifest from the
accepted pages' final order.

### 9. `manifest.json` and `units/<n>.json`

Gold groups final Silver regions into page-scoped semantic units. After
compiling Silver, `pdf_agent` validates the draft `detected_region_ids`, checks
the complete non-overlapping partition, and persists them as `region_ids` in
the page's unit file.

`gold/<slug>/manifest.json` itself — the document-level index of page unit
files and the `layout_fingerprint` used for staleness checks — is assembled
once, at `ingest_finalize`, from all accepted pages' persisted unit files.

```json
{
  "schema_version": 1,
  "layout_fingerprint": "sha256:...",
  "pages": {
    "3": {
      "units": "units/3.json"
    }
  }
}
```

Each page unit file has this shape; as with `layout/<n>.json`, the page is
implied by its path and by each unit's region ids:

```json
{
  "units": [
    {
      "id": "g-p3-u2",
      "region_ids": ["p3-r12", "p3-r14", "p3-r15"],
      "title": "Cleaning-in-place operating requirements",
      "description": "Connected paragraphs specifying cleaning-in-place temperature, duration, and chemical-concentration requirements. The unit supports retrieval of LKH pump operating limits and CIP procedure values.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

`title` and `description` are required. A description contains two to three
descriptive sentences suitable for embedding search: it names the content,
quantities, and entities represented by the unit. `tags` and `entities` are
optional. `region_ids` are ordered. Across all units they form an exact
partition of the final Silver regions, and all IDs in one unit file must
resolve to that file's page. Gold stores semantic metadata and region
references; Silver supplies the text, bboxes, page numbers, reading order, and
cells.

When `layout.json` changes, search and Gold reads return a stale-layout warning
when `manifest.json` no longer matches the current layout fingerprint. Rebuilds
are explicit.

### 10. `embeddings.json`

Embeddings and the lexical retrieval text stored alongside them are both
disposable and reproducible. `text` is the deterministic embedding input,
constructed from a Gold unit's title, description, and present tags and
entities. `lexical_text` is a separate deterministic field: the unit's member
regions' raw Silver text, assembled in reading order — the same assembly the
OIP export uses for `content.text`. Embedding search matches the harness's
curated description; BM25 matches the document's own wording, so each field
carries the text suited to its retrieval method. This document-level file
contains both for every Gold unit in `units/<n>.json`.

```json
{
  "embed_model": "BAAI/bge-small-en-v1.5",
  "layout_fingerprint": "sha256:...",
  "vectors": [
    {
      "gold_id": "g-p3-u2",
      "region_ids": ["p3-r12", "p3-r14", "p3-r15"],
      "text": "Cleaning-in-place operating requirements ...",
      "lexical_text": "CIP: 85 C for 20 minutes at 1.5% NaOH ...",
      "vector": [0.0]
    }
  ]
}
```

`lexical_text` needs no model or version metadata to stay reproducible: it is
literal Silver text, not a model call, so it is rebuilt directly from
`region_ids` whenever this file is regenerated. `pdf_agent` does not persist a
BM25 term index; the search service builds or caches one from `lexical_text`
at query time, the same way it already scans or caches vectors across
documents (see "Multiple documents and global search," below).

### 11. Grounded retrieval

Search is the candidate-finding step of retrieval: it ranks Gold units by
fusing two independent signals — embedding similarity over each unit's `text`,
and BM25 lexical match over each unit's `lexical_text` — then identifies the
fused-ranked Gold units and their retained region IDs. Reciprocal rank fusion,
or another rank-based combination, avoids reconciling BM25 and
cosine-similarity scores, which live on incomparable scales. Retrieval then
resolves those IDs to authoritative Silver text, cells, images, and
coordinates through the `layout.json` manifest and its page files. Each
retrieval result supplies relevant evidence and the information needed to anchor
it precisely in the original PDF.

The search interface must support direct context expansion through the manifest
`order` array, including preceding and following regions on different pages. It
must also surface stale-layout warnings and give users enough evidence to
inspect a retrieval result.

### 12. Multiple documents and global search

Per-document Silver and Gold artifacts are the durable source of truth.
`documents.json` catalogs document discovery and status.

```json
{
  "documents": [
    {
      "slug": "alfa-laval-lkh",
      "title": "Alfa Laval LKH",
      "page_count": 24,
      "layout_fingerprint": "sha256:...",
      "gold_status": "ready",
      "embedding_model": "BAAI/bge-small-en-v1.5",
      "stale": false
    }
  ]
}
```

A cross-document search hit identifies the document, Gold unit, region IDs,
score, and layout status:

```json
{
  "slug": "alfa-laval-lkh",
  "gold_id": "g-p3-u2",
  "region_ids": ["p3-r12", "p3-r14", "p3-r15"],
  "score": 0.93,
  "stale": false
}
```

The search service embeds the question once, ranks compatible Gold vectors and
`lexical_text` across documents with the same fused ranking used within one
document, then resolves each hit through that document's layout manifest and
page files. Neighbor expansion is always document-local; a multi-document
answer combines independently resolved contexts.

Per-document `embeddings.json` files remain the durable, regenerable vector
and lexical-text source; global search scans or caches those files directly,
computing its BM25 term statistics over whatever set of documents that scan
covers so scores stay comparable across them. The initial implementation
always scans the whole collection, but the scan is already per-document, so
restricting it to a caller-supplied `slugs` subset later is a filter on which
files get scanned, not a change to the artifacts, the ranking method, or how
BM25 statistics are computed — the same "compute over whatever the scan
covers" rule already produces correct, comparable scores for a subset. If
scanning stops scaling, a derived, rebuildable cross-document index (vectors,
lexical text, plus `{slug, gold_id}` references) can be added later without
changing this contract; it is not part of the initial design.

## Portable source references

`pdf_agent` returns package-owned document and retrieval DTOs. A result carries
a portable source reference, for example:

```json
{
  "document": "alfa-laval-lkh",
  "region_ids": ["p3-r12", "p3-r14"],
  "locator": {"page": 3, "bbox": [72.0, 610.0, 520.0, 665.0]}
}
```

The reference identifies durable evidence for caller-controlled display and
storage. A caller may keep it beside an extracted claim, open the cited page,
or use it to retrieve a crop through the package interface.

## OIP export

The internal artifact layout above (`detected/`, `layout/`, `units/`) is
shaped for `pdf_agent`'s own multi-stage curation pipeline: page-scoped,
inspectable, and free to change as that pipeline evolves. `pdf_agent` writes a
thin [OIP](https://github.com/Novia-RDI-Seafaring/OIP)-shaped view at the
artifact root, compiled from `layout.json` and the Gold unit files. This OIP
view is the standard contract through which OIP-aware consumers discover and
read the package's output. It is the mechanical step from "bundled extension"
to "external package" on the producer ladder.

The root-level `manifest.json` is the OIP producer manifest, distinct from
`gold/<slug>/manifest.json` above:

```json
{
  "oip_version": "0.1",
  "producer": {"name": "pdf-agent", "display_name": "pdf-agent", "version": "0.1.0"},
  "produces": {
    "source_kinds": ["application/pdf"],
    "region_kinds": ["heading", "paragraph", "list", "table", "figure",
                      "diagram", "caption", "equation", "header_footer", "other"],
    "source_ref_kinds": ["pdf-page-bbox"]
  },
  "invocation": {"kind": "mcp-stdio", "command": "pdf-agent-mcp", "args": [],
                  "tools_namespace": "pdf"}
}
```

Each exported region compiles one Gold unit to the OIP shape:

```json
{
  "id": "alfa-laval-lkh:r0042",
  "kind": "paragraph",
  "source_ref": {"kind": "pdf-page-bbox", "page": 3,
                  "bbox": [72.0, 610.0, 520.0, 665.0]},
  "content": {"text": "content/alfa-laval-lkh:r0042.md"}
}
```

`id` is a fresh, sequential OIP id, independent of `pdf_agent`'s own
`p3-r12` / `g-p3-u2` ids. `kind` is the normalized kind of the unit's first
member region in reading order. `source_ref.bbox` is the union of its member
regions' bboxes. `content.text` points at the unit's member regions' text,
assembled in relative reading order; a unit with a table member also gets a
`content.json` with that table's cells, and a `content.png` crop of the union
bbox.

This export is a compiled, regenerated projection at the package boundary. It
carries data and invariants established by `layout.json` and the Gold unit
files, and is regenerated whenever either changes. The internal artifacts
remain the authoritative pipeline data while the OIP view provides the stable
consumer contract.

## Agent interface

This is the package's agent-facing interface. The HTTP, CLI, and MCP adapters
call the same package services and return JSON for agent-facing commands. A
host that aggregates tool servers may prefix names for collision safety, but
the inputs and outputs remain package contracts.

### 1. Ingest and monitor

Semantic curation and Gold creation always use the connected harness. The
package exposes a durable session protocol:

```text
ingest_begin(pdf_path, slug?, dpi?, force?)
ingest_get_page(session_id, page, format=path|base64)
ingest_submit_page(session_id, page, regions, polished_md?, protocol_version?)
ingest_status(session_id?|slug?)
ingest_finalize(session_id, allow_missing_pages?, declared_model?)
ingest_abort(session_id)
```

`ingest_begin` preserves the source and prepares Silver layout artifacts and
page work items. The harness skill supplies the per-page polished markdown and
grounded region grouping. Each accepted page writes its final Silver layout and
Gold units. `ingest_finalize` validates completion, assembles the document-level
manifests, creates embeddings, and marks Gold complete. A convenience
`ingest_pdf` command may start this same session and await the harness
submissions that create page results.

`list_documents`, `list_active_ingests`, and `get_ingest_status` expose
document state, session progress, and terminal errors directly to the agent.

### 2. Inspect a document and its evidence

These operations let an agent browse the stored PDF substrate and expand a
search hit into its source evidence:

```text
get_document_index(slug)                 # Silver outline, tables, figures
get_gold_regions(slug, page?)            # Gold regions and their source refs
get_gold_map(slug)                       # document metadata plus all Gold data
get_page_text(slug, page)                # polished or raw page markdown
get_page_image(slug, page, format=path|base64)
get_crop(slug, rel_path, format=path|base64)
get_pdf(slug, format=path|base64)
locate_text(slug, page, query, within_bbox?)
```

`locate_text` returns page-space quads and is the value-level companion to a
region bbox. An agent uses it when a number or short phrase must be highlighted
inside a larger cited region.

### 3. Retrieve grounded evidence

```text
embed_document(slug, overwrite?)
get_embeddings_meta(slug)
search_documents(query, k=10, slugs?)
```

`embed_document` backfills or rebuilds `embeddings.json` without re-running
ingest — both the embedding vectors and each unit's `lexical_text`.
`search_documents` is the public retrieval operation. Internally it fuses
embedding and BM25 ranking over Gold units and resolves the retained Silver
evidence. Its results therefore carry a source anchor, not only a ranked
score. `slugs` is optional and, when omitted, searches the whole collection;
the initial implementation is not required to expose it, but the parameter
reserves the extension point so a caller-restricted subset costs nothing
structural to add later — see "Multiple documents and global search," below:

```json
{
  "slug": "alfa-laval-lkh",
  "page": 3,
  "region_id": "p3-r12",
  "text": "...",
  "score": 0.93
}
```

Every hit is resolvable through the inspection operations above. An agent can
preserve the returned source reference beside any downstream claim or artifact.

### 4. Produce grounded structured outputs

```text
extract_pointed(slug, select, shape)
compose_synopsis(slug, entity, output=json|pdf|md)
derive_region(slug, parent_region_id, region)
```

`extract_pointed` fills a caller-defined JSON shape only from selected Gold
regions and returns leaf-level provenance plus explicitly unfilled fields.
`compose_synopsis` produces an entity-scoped structured or rendered summary.
`derive_region` persists an additional package-owned region that inherits its
parent's source reference.

### 5. Required CLI, MCP, and HTTP surface

The `pdf-agent` CLI, MCP server, and HTTP API must together cover: ingest,
list, search, index, regions, page text, text location, gold map, page image,
crop, raw PDF, embed, structured extract, synopsis, and harness ingest
sessions. The CLI may group or rename commands for clarity as long as every
operation above is reachable with equivalent JSON inputs and outputs.

The HTTP, CLI, MCP, and programmatic interfaces are the complete package
boundary for this proposal.

## Harness ingestion logic

Harness ingestion is a skill-driven collaboration between `pdf_agent` and an
image-capable agent host. The package prepares durable work items, the host
installs the package skill as agent guidance, and the agent follows the session
protocol using its image-reading capability. Model selection, credentials, and
model-provider data handling remain within the harness boundary.

The protocol has the following responsibilities:

| Stage | `pdf_agent` | Harness agent, guided by the installed skill |
| --- | --- | --- |
| Begin | Stores Bronze, runs layout extraction, writes preliminary Silver artifacts, renders page images, and opens a journaled session. | Calls `ingest_begin`, retains the returned `session_id`, protocol version, and page status. |
| Work item | Returns one page's image, suppression-filtered masked region data, a retained-region overlay, raw or reconstructed text, candidate IDs, and the response instructions. | Calls `ingest_get_page` for each pending page. |
| Visual curation | Supplies the page image, retained layout data, and constrained response schema. | Uses the harness's native image-reading facility to inspect the page image alongside the work-item data, then identifies corrections and Gold groups. |
| Submit | Validates the closed response schema, known IDs, geometry, exact partition, and revision/version state. Persists accepted overrides and draft Gold units as separate page artifacts, then persists that page's final Silver layout and Gold units once the partition is valid. | Calls `ingest_submit_page` with polished markdown, overrides, and Gold units. Repairs any named validation error and resubmits the page. |
| Publish | Assembles the document-level layout manifest and Gold manifest from the accepted pages, then computes and persists embeddings; marks Gold complete only after all required writes succeed. | Checks session status, then calls `ingest_finalize` when every page is accepted. |

`ingest_get_page` is the image hand-off. On a same-machine harness it may
return a local PNG path; for a harness running elsewhere it may return base64
image bytes. The skill directs the agent to use its host-specific image tool to
place that image in the model context before writing a result. Harness
ingestion therefore requires a host that can load the handed-off image into its
model context.

The page result is intentionally constrained. The agent names stable
detected-region IDs, supplies any allowed kind or reading-order overrides, and
creates Gold units with the required `title` and retrieval-oriented
`description` fields plus optional tags and entities. The package resolves IDs to geometry, validates region
membership, and checks that the submitted Gold units form an exact,
non-overlapping partition of the retained Silver regions. The harness supplies
visual and semantic judgment while `pdf_agent` remains the source of truth for
evidence, validation, and persistence.

Sessions are durable and page submissions are replaceable. After an interrupted
agent run, the next agent starts with `ingest_status(session_id or slug)`, then
gets only the remaining pages. A rejected page remains uncommitted until a
corrected submission is accepted. `ingest_finalize` refuses to assemble and
mark complete a partial document unless the caller explicitly declares the
missing pages; that declaration is recorded in the resulting document metadata.

## Suggested project structure

This implementation shape follows the artifact layout and agent interface
above. `ingest` owns the work that creates and refreshes Bronze, Silver, Gold,
and embeddings. `retrieve` owns the query path: `search` finds relevant Gold
units and `resolve` turns them into anchored Silver evidence and context.
`export` compiles the OIP-shaped view at the package boundary; it reads
`layout.json` and Gold unit files and writes nothing the internal pipeline
reads back, so it can change independently of `ingest` and `retrieve`.
`api.py` is the stable public boundary over those jobs.

```text
pdf-agent/
  pyproject.toml
  src/
    pdf_agent/
      api.py                          # stable public services, DTOs, errors
      core/
        ingest/                       # build the searchable anchored document
          normalize.py                # map extractor output to canonical page layout
          suppression.py              # deterministic retained-region decisions
          corrections.py              # accepted harness overrides to Silver regions
          gold_draft.py               # accepted draft Gold-unit artifacts
          session.py                  # durable harness work orders and publication
          validation.py               # validate submitted corrections and Gold groups
        retrieve/
          search.py                   # rank Gold units via fused embedding and BM25 match
          resolve.py                  # load anchored Silver evidence and context
        export/
          oip.py                      # compile manifest.json + artefacts/<slug>/
      infra/
        filesystem/                   # Bronze, Silver, Gold, session, index storage
        docling/                      # layout extraction
        pymupdf/                      # render, crop, text location
        embeddings/                   # local or configured embedding provider
        bm25/                         # in-memory lexical index builder
      adapters/
        http/
        cli/
        mcp/
      skills/
        pdf_agent/
          skill.md                    # harness-driven ingest, inspect, retrieve, cite workflow
  tests/
```

The harness session service is the only path that supplies semantic curation
output. It feeds the same ingest validation and artifact-writing path used for
every document, while the skill supplies the host-facing loop that obtains page
vision from the harness.
