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
that representation instead of the raw PDF. Concretely, `pdf_agent` has two
jobs:

1. Ingest a PDF into a searchable document representation whose text, tables,
   images, and reading order remain tied to exact locations in the original
   PDF.
2. Retrieve relevant evidence from those documents, returning usable context
   together with page- and bbox-level anchors back to the original PDF.

Silver is the complete, extractor-independent, source-grounded document layout
that makes exact anchoring possible. Gold is the semantic representation used
to find relevant evidence, and embeddings are a regenerable index over Gold.

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
or another coherent context. Silver supplies the source text, geometry, and
table cells.

Documents are independent layout and Gold namespaces. Regions use deterministic
document-local IDs such as `p3-r12`. Cross-document references contain the
document slug and region ID; the layout manifest resolves the ID to its page.

## Artifact layout

`pdf_agent` owns one configured artifact root. Every command uses that root;
the package does not expose separate Bronze, Silver, or Gold directory
settings.

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

`--keep-debug-artifacts` persists the masked VLM input and detected and final
overlays shown above.

## Pipeline

1. Preserve the source PDF in Bronze.
2. Extract and normalize detected layout regions per page, including full text,
   geometry, and stable detected-region IDs. Derive a bounded masked view for
   the semantic pass.
3. Apply deterministic containment suppression, render an overlay of the
   remaining detected regions, and run one mandatory harness or external-VLM
   curation pass. It returns kind and reading-order overrides plus draft Gold
   units, all by detected-region ID.
4. Apply the VLM overrides and compile final Silver layout pages plus a
   document-level ordered manifest.
5. Validate the draft Gold units against final Silver and persist page-scoped
   Gold units with the same retained region IDs.
6. Embed deterministic retrieval text derived from persisted Gold data and
   persist the vectors.

The one-call dependency is:

```text
pruned detected regions -> one VLM call -> overrides ------------> compile final Silver
                                        \-> draft Gold groups ----+
                                                                     -> validate retained IDs
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
a deterministic, document-local ID that is retained through compilation. Each
re-extraction produces a layout version. The VLM and harness name these IDs.

```json
{
  "schema_version": 1,
  "regions": [
    {
      "id": "p3-r12",
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
      "id": "p3-r12",
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
It records suppression decisions plus kind and reading-order overrides; Silver
text and geometry remain extractor-owned.

```json
{
  "suppressed": [
    {
      "id": "p3-r13",
      "contained_by": "p3-r12",
      "contained_area_ratio": 0.97
    }
  ],
  "overrides": [
    {"id": "p3-r12", "kind": "diagram"},
    {"id": "p3-r14", "reading_order": 48}
  ]
}
```

Deterministic code adds a region to `suppressed` when the intersection of its
bbox with another detected region of equal or larger area covers at least 90%
of the first region's bbox area. It chooses the largest qualifying containing
region; ties use the stable detected-region ID. The record identifies the
containing region and measured ratio so the decision is inspectable.

The VLM supplies kind and reading-order overrides. A `reading_order` override
may be any number, including fractional, not only one already in use on that
page: a value below the page's current minimum moves a region to the front, a
value above the current maximum moves it to the back, and a value between two
neighbors, fractional if they are adjacent integers, moves it between them.
Repositioning one region therefore never requires rewriting any other
region's value.

### 4. `detected/<n>.overlay.png` and VLM curation work order

The same work order is used whether a harness agent or an external VLM performs
the curation pass. The input contains:

- an image of the page with pruned detected regions overlaid, including each
  detected-region ID, kind, and provisional detected order;
- `detected/<n>.masked.json` for that page;
- the constrained response schema and task instructions.

The short text prefix lets the VLM match an overlay label to its JSON record
while keeping the correction input small.

Each overlay label uses the compact form
`#<detected_order> <detected_region_id> <kind>`, for example
`#47 p3-r12 paragraph`. Showing the provisional order directly on the page
makes reading-order errors visible, especially in multi-column layouts. The
stable detected-region ID remains the target of every correction.

`--keep-debug-artifacts` retains the detected overlay.

```json
{
  "overrides": [
    {"id": "p3-r12", "kind": "diagram"},
    {"id": "p3-r14", "reading_order": 48}
  ],
  "gold_units": [
    {
      "detected_region_ids": ["p3-r12", "p3-r14"],
      "title": "Cleaning-in-place operating requirements",
      "description": "Temperature, duration, and chemical concentration requirements.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

One VLM call produces both the overrides and draft Gold units, keyed to the
stable detected-region IDs retained through compilation.

The server rejects unknown or duplicate detected IDs and conflicting overrides.
It persists deterministic suppression and accepted VLM overrides in
`detected/<n>.edits.json`, then compiles final Silver.

It then checks the draft `gold_units` against the compiled page: every
retained (non-suppressed) region must appear in exactly one unit's
`detected_region_ids`, with none missing and none duplicated across units.
If the draft units do not form that exact partition, the server rejects the
submission and names the gap instead of guessing or persisting a partial
result:

```json
{
  "accepted": false,
  "missing_region_ids": ["p3-r15"],
  "duplicated_region_ids": []
}
```

Kind and reading-order overrides already accepted in this call stand; only
`gold_units` is re-requested. The server re-issues the same work order for
that page so the VLM or harness can resubmit corrected `gold_units`. After a
small bounded number of failed attempts (for example, three), the page fails
ingestion with a terminal error naming the unresolved regions, visible
through `get_ingest_status`, rather than looping indefinitely or persisting
an incomplete partition.

Only once the partition is valid does the server write
`gold/<slug>/units/<n>.json`.

### 5. `layout.json` and `layout/<n>.json`

`layout.json` is a compact document-level manifest. Its `order` array is the
single canonical document-wide reading order of retained detected-region IDs;
an ID's position in that array is its order. Its `region_pages` index maps each
ID to its final page file. `layout/<n>.json` contains that page's final curated
regions, in the same relative reading order. This keeps inspection page-scoped
while the manifest supports direct context queries across page boundaries.

When `--keep-debug-artifacts` is set, render `layout/<n>.overlay.png` from the
clean page image and the final regions. It uses the retained detected IDs and
final labels, so it can be compared directly with the detected overlay during
debugging.

```json
{
  "schema_version": 1,
  "layout_fingerprint": "sha256:...",
  "pages": {"3": "layout/3.json"},
  "order": ["p3-r12", "p3-r14", "p3-r15"],
  "region_pages": {
    "p3-r12": 3,
    "p3-r14": 3,
    "p3-r15": 3
  }
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

The compiler gives each retained region an effective order: its VLM
`reading_order` override when one was supplied, otherwise its `detected_order`.
It sorts retained regions by page, then by effective order within the page,
breaking ties by the stable detected-region ID. Suppressed regions are dropped
before sorting, not renumbered, so gaps left in `detected_order` or
`reading_order` values never surface: `order` is a positional array, and a
region's rank is its index in that array, not the number that produced it.
Sorting page-first also means a page's curation call, which sees only that
page's regions, can never misplace a region onto another page or collide with
another page's `detected_order` numbering.

The compiler atomically replaces the manifest and page files; suppressed
regions are omitted from both.

### 6. `manifest.json` and `units/<n>.json`

Gold groups final Silver regions into page-scoped semantic units. After
compiling Silver, `pdf_agent` validates the draft `detected_region_ids`, checks
the complete non-overlapping partition, and persists them as `region_ids` in
the page's unit file.

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
      "description": "Connected paragraphs that specify temperature, duration, and chemical concentration requirements.",
      "tags": ["cip", "operating-limits"],
      "entities": ["LKH-5"]
    }
  ]
}
```

`title` and `description` are required. `tags` and `entities` are optional.
`region_ids` are ordered. Across all units they form an exact partition of the
final Silver regions, and all IDs in one unit file must resolve to that file's
page. Gold stores semantic metadata and region references; Silver supplies the
text, bboxes, page numbers, reading order, and cells.

When `layout.json` changes, search and Gold reads return a stale-layout warning
when `manifest.json` no longer matches the current layout fingerprint. Rebuilds
are explicit.

### 7. `embeddings.json`

Embeddings are disposable and reproducible. Retrieval text is deterministically
constructed from a Gold unit's title, description, and present tags and
entities. This document-level file contains vectors for every Gold unit in
`units/<n>.json`.

```json
{
  "embed_model": "BAAI/bge-small-en-v1.5",
  "layout_fingerprint": "sha256:...",
  "vectors": [
    {
      "gold_id": "g-p3-u2",
      "region_ids": ["p3-r12", "p3-r14", "p3-r15"],
      "text": "Cleaning-in-place operating requirements ...",
      "vector": [0.0]
    }
  ]
}
```

### 8. Grounded retrieval

Search is the candidate-finding step of retrieval: it embeds the question,
ranks Gold vectors, and identifies Gold units and their retained region IDs.
Retrieval then resolves those IDs to authoritative Silver text, cells, images,
and coordinates through the `layout.json` manifest and its page files. A
retrieval result is therefore relevant evidence plus the information needed to
anchor it precisely in the original PDF, not a score or generated summary
alone.

The search interface must support direct context expansion through the manifest
`order` array, including preceding and following regions on different pages. It
must also surface stale-layout warnings and give users enough evidence to
inspect a retrieval result.

### 9. Multiple documents and global search

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
  "gold_id": "g-0042",
  "region_ids": ["p3-r12", "p3-r14"],
  "score": 0.93,
  "stale": false
}
```

The search service embeds the question once, ranks compatible Gold vectors
across documents, then resolves each hit through that document's layout
manifest and page files. Neighbor expansion is always document-local; a
multi-document answer combines independently resolved contexts.

Per-document `embeddings.json` files remain the durable, regenerable vector
source; global search scans or caches those files directly. If scanning stops
scaling, a derived, rebuildable cross-document index (vectors plus
`{slug, gold_id}` references) can be added later without changing this
contract; it is not part of the initial design.

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

The reference identifies durable evidence without assuming how a caller displays
or stores it. A caller may keep it beside an extracted claim, open the cited
page, or use it to retrieve a crop through the package interface.

## OIP export

The internal artifact layout above (`detected/`, `layout/`, `units/`) is
shaped for `pdf_agent`'s own multi-stage curation pipeline: page-scoped,
inspectable, free to change as that pipeline evolves. It is not a contract
other producers or consumers should couple to. For that, `pdf_agent` also
writes a thin [OIP](https://github.com/Novia-RDI-Seafaring/OIP)-shaped view at
the artifact root, compiled from `layout.json` and the Gold unit files, so
any OIP-aware consumer, not only one that understands `pdf_agent`'s internal
shape, can discover and read it. This is the mechanical step from "bundled
extension" to "external package" on the producer ladder: the internal shape
stays whatever is useful to the pipeline, and only the boundary speaks the
standard contract.

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

This export is compiled, not authored, and carries no data or invariants that
are not already established internally: it is regenerated whenever
`layout.json` or the Gold unit files it derives from change. Nothing about it
constrains the shape of `detected/`, `layout/`, or `units/`, and nothing about
the internal pipeline changes to produce it; it is a projection at the
boundary, not a second source of truth.

## Agent interface

This is the package's agent-facing interface. The HTTP, CLI, and MCP adapters
call the same package services and return JSON for agent-facing commands. A
host that aggregates tool servers may prefix names for collision safety, but
the inputs and outputs remain package contracts.

### 1. Ingest and monitor

For the normal keyed pipeline, an agent calls:

```text
ingest_pdf(pdf_path, slug?, skip_polish?, skip_regions?, full_page_ocr?, force?)
list_documents()
list_active_ingests()
get_ingest_status(slug)
```

`ingest_pdf` preserves the source, builds Silver, optionally builds Gold, and
embeds the document. It is idempotent when completed Gold exists unless
`force=true`. The status operations expose stage, progress, and terminal error
records rather than requiring an agent to infer completion from filesystem
state.

For no-key or agent-curated ingestion, the package exposes a durable session
protocol:

```text
ingest_begin(pdf_path, slug?, dpi?, force?)
ingest_get_page(session_id, page, format=path|base64)
ingest_submit_page(session_id, page, regions, polished_md?, protocol_version?)
ingest_status(session_id?|slug?)
ingest_finalize(session_id, allow_missing_pages?, declared_model?)
ingest_abort(session_id)
```

The package performs the mechanical work. The agent supplies only the
per-page polished markdown and grounded region grouping the harness flow
requires.

### 2. Inspect a document and its evidence

These operations let an agent browse the stored PDF substrate instead of
relying on a search hit alone:

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
search_documents(query, k=10)
```

`embed_document` backfills or rebuilds embeddings without re-running ingest.
`search_documents` is the public retrieval operation. Internally it searches
for relevant Gold units and resolves the retained Silver evidence. Its results
therefore carry a source anchor, not only ranked semantic metadata:

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

## Implementation order

1. Create the standalone `pdf_agent` package with its own configurable data
   root, HTTP, CLI, and MCP adapters, and `src/pdf_agent/skills/SKILL.md`.
2. Define and validate the required Bronze and Silver extractor artifacts.
3. Write page-scoped full `detected/<n>.json` files and deterministic
   `detected/<n>.masked.json` semantic-pass views from the Docling adapter.
4. Implement deterministic containment suppression, `edits.json`, pruned-region
   overlays, and the single mandatory harness/VLM curation-pass contract.
5. Implement the atomic `layout.json` manifest and page-layout compiler with
   retained region IDs and canonical reading order.
6. Validate the draft Gold output after layout compilation, then persist
   page-scoped Gold unit files and the document-level embedding file.
7. Compile the OIP producer manifest and the per-document `artefacts/<slug>/`
   export from `layout.json` and the Gold unit files.
8. Add `documents.json` and cross-document search over compatible per-document
   embeddings.
9. Implement the retrieval service: search Gold IDs, then resolve
   layout-manifest region IDs into anchored Silver evidence and context.
10. Add the rebuildable global vector index when per-document scans or caching
   need acceleration.
11. Add alternate OCR/layout extractors only when they satisfy the same
   normalized artifact contract.

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
        retrieve/
          search.py                   # rank Gold units
          resolve.py                  # load anchored Silver evidence and context
        export/
          oip.py                      # compile manifest.json + artefacts/<slug>/
      infra/
        filesystem/                   # Bronze, Silver, Gold, session, index storage
        docling/                      # layout extraction
        pymupdf/                      # render, crop, text location
        llm/                          # configured VLM curation and embeddings
      adapters/
        http/
        cli/
        mcp/
      skills/
        SKILL.md                      # ingest, retrieve, inspect, cite workflow
  tests/
```

The configured VLM and the harness ingest workflow both feed the same ingest
validation and artifact-writing path. The harness is an alternate way to
provide curation output, while `infra/llm/` contains clients that invoke a
configured model directly.
