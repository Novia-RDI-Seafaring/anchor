# Proposal: curated Silver layout pipeline

## Status

Draft for later implementation planning.

## TODO before implementation

- Resolve the debugging and inspection capabilities for every pipeline stage:
  detected regions, deterministic pruning, overlays, semantic-pass output,
  final Silver layout, Gold search units, and stale-layout warnings.
- Define and validate the extractor and semantic-pass input contracts. The
  semantic pass needs a deterministic masked view of each detected page:
  region ID, kind, detected order, and a bounded text prefix. Specify the
  masking rule, validate its correspondence with the overlay, and clearly
  report an extraction that cannot provide the required region data.
- Define the search interface and its role beyond extraction. Specify how it
  ranks Gold search units, presents the selected Silver regions and their
  evidence, expands preceding and following context across pages, reports
  stale Gold data, and supports inspection and repair of retrieval results.

## Goal

Make Silver the complete, extractor-independent, source-grounded document
layout. Gold is a semantic search layer over Silver, and embeddings are a
regenerable index over Gold.

The layers have distinct jobs:

- Bronze preserves the submitted PDF unchanged.
- Silver records the physical document: text, bboxes, kinds, pages, and reading
  order.
- Gold groups one or more Silver regions into one searchable semantic unit with
  a title, description, and optional tags and entities.
- Search ranks Gold units, then loads their referenced Silver regions as the
  actual agent or user context.

Each final Silver region belongs to exactly one Gold unit. A Gold unit may
represent one region, connected paragraphs, a figure or table with its caption,
or another coherent context. Gold never replaces Silver as the source of text,
geometry, or table cells.

Documents are independent layout and Gold namespaces. A final Silver ID such as
`s000047` is unique only within its document. A reference that crosses a
document boundary uses the document slug and a document-local ID; the layout
manifest resolves Silver IDs to pages when their content is loaded.

## Artifact layout

```text
bronze/
  <filename>.pdf                       # immutable submitted source evidence
silver/
  <slug>/
    detected/                           # pre-final detection and semantic-pass artifacts
      <n>.png                           # clean rendered page for display and bbox clipping
      <n>.json                           # normalized full extractor output for page n
      <n>.masked.json                    # retained VLM input when debug artifacts are kept
      <n>.overlay.png                   # retained detected overlay when debug artifacts are kept
      <n>.edits.json                    # deterministic suppression and VLM curation overrides
    layout.json                         # document manifest: order, ID index, page files
    layout/                             # final page-scoped Silver layout
      <n>.json                          # final curated Silver regions for page n
      <n>.overlay.png                  # retained final overlay when debug artifacts are kept
gold/
  <slug>/
    manifest.json                       # document fingerprint, page-file index, and status
    units/                              # page-scoped Gold semantic units
      <n>.json                          # semantic units resolved to page n's final Silver IDs
    embeddings.json                     # regenerable vectors for all document Gold units
documents.json                          # project catalog of document status and metadata
search-index/
  <model>/...                           # optional derived cross-document vector index
```

The page-scoped files are intentional: they are the practical unit for human
inspection and debugging. The clean page image supports display and clipping a
region bbox into evidence. `layout.json` is the compact document-level manifest
for ordered navigation and page-file lookup.

`--keep-debug-artifacts` retains the masked VLM input and detected and final
overlays shown above. Without it, those derived files are used during ingest
when needed but are not persisted. All other listed artifacts are retained.

## Pipeline

1. Preserve the source PDF in Bronze.
2. Extract and normalize detected layout regions per page, including full text,
   geometry, and stable detected-region IDs. Derive a bounded masked view for
   the semantic pass.
3. Apply deterministic containment suppression, render an overlay of the
   remaining detected regions, and run one mandatory harness or external-VLM
   curation pass. It returns kind and reading-order overrides plus draft Gold
   units, all by detected-region ID. It never proposes bboxes.
4. Apply the VLM overrides and compile final Silver layout pages plus a
   document-level ordered manifest.
5. Resolve the draft Gold units against final Silver, validate their exact
   partition, and persist page-scoped Gold units. This is not a second VLM
   call.
6. Embed deterministic retrieval text derived from persisted Gold data and
   persist the vectors.

The one-call dependency is:

```text
pruned detected regions -> one VLM call -> overrides ------------> compile final Silver
                                        \-> draft Gold groups ----+
                                                                     -> resolve to final IDs
                                                                        -> persist Gold
```

## Specifications

### 1. Bronze source

`bronze/<filename>.pdf` is the original uploaded byte stream. Its metadata must
record at least filename, checksum, ingest time, and the selected extractor.
Bronze is immutable source evidence.

### 2. `detected/<n>.json` and `detected/<n>.masked.json`

Each `detected/<n>.json` file is the normalized extractor result for one page
before curation and retains the full extractor text. Every detected region has
a stable ID for the duration of the ingest and curation pass. The VLM and
harness name only these IDs.

```json
{
  "schema_version": 1,
  "regions": [
    {
      "id": "d-p3-r12",
      "page": 3,
      "detected_order": 47,
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

`detected/<n>.masked.json` is a deterministic, token-bounded projection of
that page's detected JSON. It is the only detected-region data sent with the
overlay to the semantic pass. It contains each region's ID, current kind,
detected order, and the first 10 characters of its `text` field. It omits full
text, bboxes, and all other extractor detail.

```json
{
  "regions": [
    {
      "id": "d-p3-r12",
      "kind": "paragraph",
      "detected_order": 47,
      "text": "The pump o"
    }
  ]
}
```

The semantic pass always uses this view. `--keep-debug-artifacts` also persists
it so that a human can inspect the exact semantic-pass input. It must be
regenerated whenever its source detected JSON changes.

### 3. `detected/<n>.edits.json`

Each page-level `detected/<n>.edits.json` records deterministic containment
suppression and VLM-proposed overrides over that page's detected-region IDs.
It does not contain arbitrary patches or VLM-supplied geometry.

```json
{
  "suppressed": [
    {
      "id": "d-p3-r13",
      "contained_by": "d-p3-r12",
      "contained_area_ratio": 0.97
    }
  ],
  "overrides": [
    {"id": "d-p3-r12", "kind": "diagram"},
    {"id": "d-p3-r14", "reading_order": 48}
  ]
}
```

Deterministic code adds a region to `suppressed` when the intersection of its
bbox with another detected region of equal or larger area covers at least 90%
of the first region's bbox area. It chooses the largest qualifying containing
region; ties use the stable detected-region ID. The record identifies the
containing region and measured ratio so the decision is inspectable. The VLM
does not suggest suppression.

The VLM may override only kind and reading order. Silver text and geometry
remain extractor-owned. Missing regions, splits, and merges need an explicit
future geometry-authoring design.

### 4. `detected/<n>.overlay.png` and VLM curation work order

The same work order is used whether a harness agent or an external VLM performs
the curation pass. The input contains only:

- an image of the page with pruned detected regions overlaid, including each
  detected-region ID, kind, and provisional detected order;
- `detected/<n>.masked.json` for that page;
- the constrained response schema and task instructions.

It does not include full extracted text, region crops, candidate-item JSON, or
per-region bboxes. The short text prefix lets the VLM match an overlay label to
its JSON record while keeping the correction input small.

Each overlay label uses the compact form
`#<detected_order> <detected_region_id> <kind>`, for example
`#47 d-p3-r12 paragraph`. Showing the provisional order directly on the page
makes reading-order errors visible, especially in multi-column layouts. The
stable detected-region ID remains the target of every correction.

The detected overlay is retained only with `--keep-debug-artifacts`.

```json
{
  "overrides": [
    {"id": "d-p3-r12", "kind": "diagram"},
    {"id": "d-p3-r14", "reading_order": 48}
  ],
  "gold_units": [
    {
      "detected_region_ids": ["d-p3-r12", "d-p3-r14"],
      "title": "Cleaning-in-place operating requirements",
      "description": "Temperature, duration, and chemical concentration requirements.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

One VLM call produces both the overrides and the draft Gold units. The draft
units are not Gold artifacts yet: they are keyed to stable detected-region IDs
because final Silver IDs do not exist at call time.

The server rejects unknown or duplicate detected IDs and conflicting overrides.
It persists deterministic suppression and accepted VLM overrides in
`detected/<n>.edits.json`, compiles final Silver, then resolves and validates
the draft units into `gold/<slug>/units/<n>.json`. The raw VLM response is not
a durable Bronze, Silver, or Gold artifact.

### 5. `layout.json` and `layout/<n>.json`

`layout.json` is a compact document-level manifest. It indexes final Silver IDs
in dense document-wide reading order and maps each page to its final layout
file. `layout/<n>.json` contains the final curated regions for one page.
This keeps inspection page-scoped while the manifest supports direct context
queries across page boundaries.

When `--keep-debug-artifacts` is set, render `layout/<n>.overlay.png` from the
clean page image and the final regions. It uses final Silver IDs and labels, so
it can be compared directly with the detected overlay during debugging.

```json
{
  "schema_version": 1,
  "layout_fingerprint": "sha256:...",
  "pages": {"3": "layout/3.json"},
  "order": ["s000047", "s000048", "s000049"],
  "region_index": {
    "s000047": {"page": 3, "index": 46}
  }
}
```

Each page layout file has this shape:

```json
{
  "page": 3,
  "regions": [
    {
      "id": "s000047",
      "order": 47,
      "kind": "paragraph",
      "bbox": [72.0, 610.0, 520.0, 665.0],
      "text": "The pump operates ...",
      "source_detected_region_ids": ["d-p3-r12"]
    }
  ]
}
```

Final Silver IDs encode document-wide order, so neighboring context is easy to
query across page boundaries. The explicit `order` field avoids requiring
consumers to parse the ID. The compiler atomically replaces the manifest and
all page files. Suppressed detected regions do not appear and do not create gaps
in the manifest's `order`.

### 6. `manifest.json` and `units/<n>.json`

Gold is a semantic retrieval layer, not a second layout. The VLM curation pass
is page-scoped, so every Gold unit is page-scoped too. After compiling Silver,
Anchor resolves that call's draft `detected_region_ids` to final
`silver_region_ids`, validates the complete non-overlapping partition, and
persists the result in that page's unit file. Gold therefore always references
final Silver, even though the one VLM call named stable detected IDs.

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

Each page unit file has this shape:

```json
{
  "page": 3,
  "units": [
    {
      "id": "g-p3-u2",
      "silver_region_ids": ["s000047", "s000048", "s000049"],
      "title": "Cleaning-in-place operating requirements",
      "description": "Connected paragraphs that specify temperature, duration, and chemical concentration requirements.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

`title` and `description` are required. `tags` and `entities` are optional.
`silver_region_ids` are ordered. Across all units they form an exact partition
of the final Silver regions, and all IDs in one unit file must resolve to that
file's page. Gold does not duplicate Silver text, bboxes, page numbers, reading
order, or cells. Cross-page Gold units are not supported.

Future improvement: support cross-page Gold units for cases such as continued
tables or a visual whose caption is on the next page. This requires either a
multi-page semantic-pass work order or a deterministic post-pass that links
page-local units. Store such units in an explicit dedicated artifact rather
than weakening the page-scoped unit files.

When `layout.json` changes, Gold and embeddings remain readable but search and
Gold reads issue a non-blocking stale-layout warning when `manifest.json` no
longer matches the current layout fingerprint. There is no automatic rebuild.

### 7. `embeddings.json`

Embeddings are disposable and reproducible. Retrieval text is deterministically
constructed from a Gold unit's title, description, and present tags and
entities. Raw Silver text is not embedded. This one document-level file contains
vectors for every Gold unit in `units/<n>.json`.

```json
{
  "embed_model": "BAAI/bge-small-en-v1.5",
  "layout_fingerprint": "sha256:...",
  "vectors": [
    {
      "gold_id": "g-p3-u2",
      "silver_region_ids": ["s000047", "s000048", "s000049"],
      "text": "Cleaning-in-place operating requirements ...",
      "vector": [0.0]
    }
  ]
}
```

### 8. Search and context resolution

Search embeds the question, ranks Gold vectors, and returns Gold metadata,
score, and final Silver-region IDs. Selecting a hit resolves the authoritative
Silver text, cells, images, and coordinates through the `layout.json` manifest
and its page files.

The search interface must support direct context expansion by final Silver
order, including preceding and following regions on different pages. It must
also surface stale-layout warnings and give users enough evidence to inspect a
retrieval result.

### 9. Multiple documents and global search

Per-document Silver and Gold artifacts are the durable source of truth. The
project-level `documents.json` is a lightweight catalog for discovery and
status, not a duplicate document store.

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

A cross-document search hit carries no page number. It needs only enough data
to find the Gold unit and resolve its Silver content within the named document:

```json
{
  "slug": "alfa-laval-lkh",
  "gold_id": "g-0042",
  "silver_region_ids": ["s000047", "s000048"],
  "score": 0.93,
  "stale": false
}
```

The search service embeds the question once, ranks compatible Gold vectors
across documents, then resolves each hit through that document's layout
manifest and page files. Neighbor expansion is always document-local; a
multi-document answer combines independently resolved contexts.

Per-document `embeddings.json` files remain the durable, regenerable vector
source. Initially, global search may scan or cache those files. If that becomes too
slow, `search-index/<model>/` is a derived, rebuildable index containing vectors
and `{slug, gold_id}` references. It must not become the only copy of vectors or
document metadata.

## Implementation order

1. Define and validate the required Bronze and Silver extractor artifacts.
2. Write page-scoped full `detected/<n>.json` files and deterministic
   `detected/<n>.masked.json` semantic-pass views from the existing Docling
   adapter.
3. Implement deterministic containment suppression, `edits.json`, pruned-region
   overlays, and the single mandatory harness/VLM curation-pass contract.
4. Implement the atomic `layout.json` manifest and page-layout compiler with
   detected-to-final ID resolution.
5. Resolve and validate the draft Gold output after layout compilation, then
   persist page-scoped Gold unit files and the document-level
   embedding file after layout compilation.
6. Add `documents.json` and cross-document search over compatible per-document
   embeddings.
7. Rework embeddings and semantic search around Gold IDs and final Silver IDs.
8. Add an optional rebuildable global vector index only when per-document scans
   or caching become too slow.
9. Add alternate OCR/layout extractors only when they satisfy the same
   normalized artifact contract.
