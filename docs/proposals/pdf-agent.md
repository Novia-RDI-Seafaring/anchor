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
  description with BM25 lexical match over the unit's final Silver text plus
  its Gold entities, then loads their referenced Silver regions as the actual
  agent or user context.

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
    session.json                        # durable ingest-session record (see "Session state and resuming")
    detected/                           # pre-final detection and harness-curation artifacts
      <n>.png                           # clean rendered page for display and bbox clipping
      <n>.json                           # complete canonical per-page layout, normalized from extractor-native output
      <n>.suppression.json               # deterministic containment decisions for page n
      <n>.masked.json                    # retained harness work-item input when debug artifacts are kept
      <n>.overlay.png                   # retained work-item overlay when debug artifacts are kept
      <n>.corrections.json               # accepted harness overrides to Silver regions for page n
      <n>.gold_draft.json                # accepted draft Gold units for page n
      <n>.gold_attempts.jsonl            # one line per rejected partition-check attempt for page n
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
curation. The package creates a page work order and returns it directly from
`ingest_get_page`, so the instructions travel with the data instead of living
only in the installed skill: the skill teaches the outer session loop (call
`ingest_begin`, then `ingest_get_page`/`ingest_submit_page` per page, then
`ingest_finalize`), while the server owns the per-page task statement, so the
two cannot drift apart or fall out of sync with server-side validation. The
work order contains:

- an image of the page with retained detected regions overlaid, including each
  detected-region ID and kind;
- `detected/<n>.masked.json` for that page;
- the fixed task instructions, below;
- when this page already has a schema-valid draft on file — a resumed
  session, or a retry after a rejected partition check — that existing
  `corrections` and `gold_draft` content plus the most recent validation
  error, so the harness agent amends its prior work instead of re-deriving
  the whole page.

The task instructions are a fixed, server-owned string returned on every
`ingest_get_page` call for every page:

> Compare the overlay image against `detected/<n>.masked.json`. For each
> retained region, check whether its labeled `kind` matches what you see and
> whether its position in reading order looks right. Where either is wrong,
> add an override for that region only — `{"id": ..., "kind": ...}` and/or
> `{"id": ..., "reading_order": ...}`; a region that is already correct needs
> no override. Then group every retained region ID into Gold units: each ID
> must appear in exactly one unit's `detected_region_ids` (a unit may hold
> just one region). For each unit, write a `title` and a two-to-three sentence
> `description` naming its content, quantities, and entities, plus optional
> `tags` and `entities`. If this response includes an existing draft or a
> validation error, edit that draft rather than starting over. Submit both
> artifacts with `ingest_submit_page`; a rejection names the exact field or
> region and the repair needed — fix only what is named and resubmit.

The short text prefix in `masked.json` lets the harness agent match an overlay label to its JSON record
while keeping the correction input small.

Each overlay label uses the compact form `<detected_region_id> <kind>`, for
example `p3-r12 paragraph`. The region number in the stable ID is the default
page-local reading order. A harness correction names the same ID and supplies
only a `reading_order` override when that order is wrong.

`--keep-debug-artifacts` retains `masked.json` and the work-item overlay so a
human can inspect the exact harness-curation input.

One harness page review of this work order produces two
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
persisted as final Silver or Gold. The submission is persisted as soon as it
passes the first (schema) stage, before the second (partition) stage runs —
deliberately, not as a byproduct. A submission that only fails the partition
check keeps its schema-valid content on disk as a draft, so a corrected
resubmission edits that draft (fix the one region assigned to two units, add
the one that's missing) instead of regenerating the entire page's grouping
from nothing, and no region is ever silently dropped just because one other
region in the same submission had a problem.

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
`detected/<n>.gold_draft.json` is re-requested. The server appends the
rejection to `detected/<n>.gold_attempts.jsonl` (one line per failed attempt:
timestamp and the same error payload shown above), then re-issues the work
order for that page with the rejected draft and its error attached — see
"Session state and resuming" — so the harness agent corrects the existing
draft rather than reconstructing it. Once `gold_attempts.jsonl` reaches a
small bounded length (for example, three lines) with the page still not
`accepted`, the page moves to the `terminal_error` state naming the
unresolved regions, visible through `ingest_status`.

Only once the partition is valid does the server write
`gold/<slug>/units/<n>.json` from the accepted `gold_draft.json`.

### 8. Session state and resuming

A session's per-page status is never stored as a mutable status field. It is
derived, on every read, from which files exist for that page — so two
concurrent readers (or a restarted agent) always recompute the same answer
from disk instead of trusting a cached blob that another writer might have
raced:

- no `detected/<n>.corrections.json` or `.gold_draft.json` yet: `pending`.
- both exist but `layout/<n>.json` and `gold/<slug>/units/<n>.json` do not:
  `drafted` — a schema-valid submission is staged but has not yet passed the
  partition check (or has not been re-checked since the extraction changed).
- `layout/<n>.json` and `gold/<slug>/units/<n>.json` both exist: `accepted`.
- `detected/<n>.gold_attempts.jsonl` has reached the bounded retry limit (see
  "Validating and persisting a page submission") with no `accepted` state:
  `terminal_error`.

`ingest_status(session_id | slug)` recomputes this ladder for every page by
scanning the artifact directory; it holds no independent source of truth to
go stale. This is also what makes concurrent harness workers safe to run
against one session: each page submission only ever writes that page's own
files, so two workers submitting different pages never contend for the same
write, and a status read is never mid-update for a page it isn't touching.

`silver/<slug>/session.json` itself stays deliberately small — an identity and
idempotency record, not a status cache:

```json
{
  "session_id": "ing-3f2a...",
  "slug": "alfa-laval-lkh",
  "layout_fingerprint": "sha256:...",
  "protocol_version": 1,
  "page_count": 24,
  "dpi": 150,
  "state": "open",
  "created_at": "2026-08-01T12:00:00Z"
}
```

`layout_fingerprint` is computed from the Bronze checksum, the extractor
version, and `dpi` at `ingest_begin` time. It binds a session to one specific
detected-layout version: `p3-r12` and its siblings are only stable IDs within
the layout version that produced them, so a session must not accept
submissions written against a different one.

- **Fresh `ingest_begin(pdf_path, slug)`** with no existing session for that
  slug: computes the fingerprint, runs extraction, writes `session.json` with
  `state: "open"`, and returns the work order.
- **Repeated `ingest_begin`** for a slug with an existing `state: "open"`
  session and a matching fingerprint: returns the existing session
  unchanged (`resumed: true`) — the common "agent process restarted, only
  remembers the slug" case. The per-page ladder above tells it exactly which
  pages still need work; it never needs the original `session_id` to resume,
  though passing it (if remembered) skips the lookup.
- **`force: true`, or a fingerprint mismatch** (the PDF, extractor, or `dpi`
  changed): the old session is superseded. Its `state` moves to `superseded`
  and a new session starts extraction fresh. Draft artifacts under the old
  fingerprint are not reused, since their region IDs are not guaranteed
  stable across a different extraction run.
- **Simple presence check.** A caller that only wants to know "did this
  finish" without session bookkeeping at all can skip `ingest_status` entirely
  and check `gold/<slug>/manifest.json` for existence, or call
  `list_documents()` and read that document's `gold_status` — both are plain
  reads over already-published artifacts, unrelated to any open session.

### 9. `layout.json` and `layout/<n>.json`

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

### 10. `manifest.json` and `units/<n>.json`

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

### 11. `embeddings.json`

Embeddings and the lexical retrieval text stored alongside them are both
disposable and reproducible. `text` is the deterministic embedding input,
constructed from a Gold unit's title, description, and present tags and
entities. `lexical_text` is a separate deterministic field, built by one
uniform rule regardless of whether the unit has much Silver text of its own:
the unit's member regions' text in final Silver (`layout/<n>.json`, resolved
via `region_ids`, joined in reading order — the same assembly the OIP export
uses for `content.text`), followed by the unit's `entities`, if any. Title,
description, and tags never enter `lexical_text` — only `entities` do, because
they are typically copied verbatim from the source rather than paraphrased by
the harness, so they stay within what BM25 is for. A figure region with no
caption and no recorded entities simply yields an empty `lexical_text` and
gets no BM25 rank for that unit; a figure tagged with an entity is still
lexically reachable by that entity even though its own Silver text is empty.
Embedding search matches the harness's curated description; BM25 matches the
document's own wording plus its named entities, so each field carries the text
suited to its retrieval method. This document-level file contains both for
every Gold unit in `units/<n>.json`.

```json
{
  "embed_model": "BAAI/bge-small-en-v1.5",
  "layout_fingerprint": "sha256:...",
  "vectors": [
    {
      "gold_id": "g-p3-u2",
      "region_ids": ["p3-r12", "p3-r14", "p3-r15"],
      "text": "Cleaning-in-place operating requirements ...",
      "lexical_text": "CIP: 85 C for 20 minutes at 1.5% NaOH ... LKH-5",
      "vector": [0.0]
    }
  ]
}
```

`lexical_text` needs no model or version metadata to stay reproducible: it is
literal Silver text plus literal Gold entities, not a model call, so it is
rebuilt directly from `region_ids` and the unit's `entities` whenever this
file is regenerated. `pdf_agent` does not persist a BM25 term index; the
search service builds or caches one from `lexical_text` at query time, the
same way it already scans or caches vectors across documents (see "Multiple
documents and global search," below).

### 12. Grounded retrieval

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

### 13. Multiple documents and global search

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

Four operations below return image or PDF bytes: `ingest_get_page`,
`get_page_image`, `get_crop`, and `get_pdf`. All four return a filesystem
path, on every adapter, never inline bytes — one rule, not three. CLI stdout
is fundamentally a text channel: an agent's shell tool captures it as a
string, so writing raw image bytes there is fragile (encoding, buffering,
line-ending translation) rather than merely inconvenient. HTTP could carry a
real binary response, and MCP could inline base64, but giving each adapter
its own answer means the same operation behaves differently depending on
which surface called it, and a harness built against one adapter silently
breaks when pointed at another. This design picks the invariant every adapter
can honor — a path — over the capability only some of them have.

The tradeoff: a harness that talks to `pdf-agent-mcp` without filesystem
access to the configured artifact root (a fully remote or sandboxed MCP
client, as opposed to one running on the same host as the server) cannot
complete image hand-off in this design. That case is out of scope for the
initial implementation. If it becomes a real need, the fix is an
adapter-specific escape hatch on MCP alone — an explicit, documented exception
to the one-rule invariant above, not a silent per-adapter divergence.

Semantic curation and Gold creation always use the connected harness. The
groups below are ordered as an agent would actually call them: ingest a
document, monitor that ingestion, build its search index, search it, inspect
a hit's evidence, then produce a structured output from that evidence.

### 1. Ingest a document

`pdf_agent` has exactly one ingestion pathway: the harness session protocol
below. The connected harness agent performs every page's curation itself,
driven by the work orders below; `pdf_agent` never calls its own model or
vision provider. There is no separate automatic or key-based pipeline to
conflate this with.

- **`ingest_begin(pdf_path, slug?, dpi?, force?)`** — Starts a harness session
  for a PDF: preserves it as Bronze, extracts and suppresses every page's
  regions, and opens a durable session so per-page harness curation can begin.
  Creates `bronze/<filename>.pdf`, `silver/<slug>/session.json`, and for every
  page, `silver/<slug>/detected/<n>.png`, `<n>.json`, and
  `<n>.suppression.json`, plus `<n>.masked.json` and `<n>.overlay.png` when
  `--keep-debug-artifacts` is set. Returns `session_id, protocol_version,
  page_status[]`.
- **`ingest_get_page(session_id, page)`** — Hands one page's work order to the
  harness: its overlay image, masked region data, and the fixed task
  instructions (see the harness curation work order under
  `detected/<n>.masked.json`, above) — plus, if this page already has a
  drafted-but-not-yet-accepted submission, that existing draft and its most
  recent validation error. Creates no new artifacts — it hands off what
  `ingest_begin` already prepared, or what a prior `ingest_submit_page`
  staged. Returns `overlay_image_path, masked_regions, instructions,
  existing_corrections?, existing_gold_draft?, last_error?`.
- **`ingest_submit_page(session_id, page, overrides, gold_units, protocol_version?)`**
  — Submits the harness's overrides to Silver regions and draft Gold units for
  one page, validating and persisting them through the two-stage check (see
  "Validating and persisting a page submission"). Creates
  `detected/<n>.corrections.json` and `detected/<n>.gold_draft.json` once
  schema validation passes (the durable draft), then `layout/<n>.json` and
  `gold/<slug>/units/<n>.json` once the partition check also passes (the
  accepted result) — a schema pass with a partition failure persists the
  draft alone and appends to `detected/<n>.gold_attempts.jsonl`. Returns
  `accepted: bool; on rejection, errors[] with JSON path, code, and repair`.
- **`ingest_finalize(session_id, allow_missing_pages?)`** — Once every
  required page is accepted, assembles the document-level Silver and Gold
  manifests, builds embeddings and the lexical index, and marks the document
  complete. Creates `silver/<slug>/layout.json`, `gold/<slug>/manifest.json`,
  and `gold/<slug>/embeddings.json`, and updates that document's entry in
  `documents.json`. Returns `gold_status, missing_pages[]? (present only when
  declared)`.
- **`ingest_abort(session_id)`** — Cancels an in-progress harness session
  before it reaches `ingest_finalize`. Creates or modifies no artifacts beyond
  ending the session. Returns `session_id, aborted: true`.

### 2. Monitor ingestion and browse the document catalog

- **`ingest_status(session_id?|slug?)`** — Recomputes per-page status from the
  artifact files present for a session or document (see "Session state and
  resuming"), so an interrupted agent run can resume with only the remaining
  pages, and two concurrent readers never see a stale cached status. Returns
  `per-page status[] (pending|drafted|accepted|terminal_error) and any
  terminal errors`.
- **`list_active_ingests()`** — Lists every ingestion session currently in
  progress, across all documents. Returns `sessions[]: session_id, slug,
  per-page progress`.
- **`list_documents()`** — Lists every document in the project catalog along
  with its status. Returns `documents[] (see documents.json)`.

### 3. Build the search index

- **`embed_document(slug, overwrite?)`** — Backfills or rebuilds a document's
  embedding vectors and `lexical_text` without re-running ingest;
  `ingest_finalize` already does this automatically, so this is for recovery
  or a changed embedding model. Returns `embed_model, vector count, stale:
  false`.
- **`get_embeddings_meta(slug)`** — Reports a document's embedding status, so
  a caller can tell whether its index is stale before searching. Returns
  `embed_model, layout_fingerprint, vector count, stale`.

### 4. Search

- **`search_documents(query, k=10, slugs?)`** — Ranks Gold units across one or
  more documents by fusing embedding similarity and BM25 lexical match, then
  resolves the top hits to anchored Silver evidence. Returns `ranked hits[]:
  slug, page, region_id, text, score`.

```json
{
  "slug": "alfa-laval-lkh",
  "page": 3,
  "region_id": "p3-r12",
  "text": "...",
  "score": 0.93
}
```

`slugs` is optional and, when omitted, searches the whole collection; the
initial implementation is not required to expose it, but the parameter
reserves the extension point so a caller-restricted subset costs nothing
structural to add later — see "Multiple documents and global search," above.
Every hit is resolvable through the inspection operations below. An agent can
preserve the returned source reference beside any downstream claim or
artifact.

### 5. Inspect a document and its evidence

These operations let an agent browse the stored PDF substrate and expand a
search hit into its source evidence:

- **`get_document_index(slug)`** — Returns a document's Silver outline — its
  headings, tables, and figures — for an agent browsing without a search
  query. Returns `Silver outline: pages, headings, tables, figures`.
- **`get_gold_regions(slug, page?)`** — Lists a document's (or one page's)
  Gold units together with the Silver regions and source refs each one
  resolves to. Returns `Gold units and their region source refs`.
- **`get_gold_map(slug)`** — Returns a document's full Gold picture in one
  call — its metadata plus every Gold unit — for callers that need the whole
  document rather than one page at a time. Returns `document metadata plus
  all Gold units`.
- **`get_page_text(slug, page)`** — Returns one page's final Silver text,
  assembled in reading order, for an agent that wants to read a page directly
  rather than search it. Returns `that page's final Silver text, assembled in
  reading order`.
- **`get_page_image(slug, page)`** — Returns the clean rendered image of one
  page, for display or as a starting point for a manual crop. Returns
  `page_image_path`.
- **`get_crop(slug, rel_path)`** — Returns the image at a known crop path
  within the document's artifacts, such as a region's bbox crop. Returns
  `crop_image_path`.
- **`get_pdf(slug)`** — Returns the original, unmodified PDF preserved as
  Bronze. Returns `pdf_path`.
- **`locate_text(slug, page, query, within_bbox?)`** — Locates a specific
  phrase or number within a page, optionally within one region, for
  highlighting a value more precisely than a full region bbox. Returns
  `page-space quads`.

### 6. Produce grounded structured outputs

- **`extract_pointed(slug, select, shape)`** — Fills a caller-defined JSON
  shape using only the selected Gold regions as source material, returning
  leaf-level provenance and explicitly naming any field it couldn't fill.
  Returns `filled shape, leaf-level provenance, unfilled_fields[]`.
- **`compose_synopsis(slug, entity, output=json|pdf|md)`** — Produces a
  structured or rendered summary scoped to one named entity across a
  document. Returns `synopsis: structured JSON, or a path/bytes for pdf|md`.
- **`derive_region(slug, parent_region_id, region)`** — Persists a new,
  package-owned region that inherits its parent region's source reference,
  for evidence an agent derives rather than one the extractor detected.
  Returns `region_id, inherited source_ref`.

### 7. Required CLI, MCP, and HTTP surface

The `pdf-agent` CLI, MCP server, and HTTP API must together cover: ingest,
list, search, index, regions, page text, text location, gold map, page image,
crop, raw PDF, embed, structured extract, synopsis, and harness ingest
sessions. The CLI may group or rename commands for clarity as long as every
operation above is reachable with equivalent JSON inputs and outputs.

The HTTP, CLI, MCP, and programmatic interfaces are the complete package
boundary for this proposal.

## Harness ingestion logic

Harness ingestion has two roles on the agent side, and they are never the
same agent context. The **orchestrator** drives the session end to end but
never reads a page image or a page's full work item — it only ever sees
session bookkeeping (a session ID, a page count, and one short verdict per
page). Every page-level vision task — reading the overlay image, comparing it
against the masked region data, writing corrections and Gold groups, handling
a rejection — happens inside a **page-batch subagent**, spawned by the
orchestrator, that never reports back more than that verdict. This split is
not an optimization applied only to large documents: it applies to every
document, including a two-page one, because the orchestrator's context is
the thing being protected, not the harness's total work. A caller implementing
this protocol needs nothing from `pdf_agent`'s own source beyond what is
written here: the tool contracts in "Agent interface" and the task
instructions in "the harness curation work order," above, are the complete
input a page-batch subagent needs to do its job.

**Orchestrator steps:**

1. Call `ingest_begin(pdf_path, slug)`. Retain `session_id` and `page_count`;
   discard everything else in the response — it is not needed again.
2. Partition `1..page_count` into contiguous batches of 3-5 pages. A document
   with 2 pages is one batch of 2; there is no page-count floor below which
   the orchestrator handles pages itself.
3. Spawn one subagent per batch, in parallel where the host supports
   concurrent subagents. Each subagent's starting prompt carries only:
   `session_id`, its batch's page numbers, and the fixed batch-worker
   instructions below. It does not carry any page content, image, or prior
   conversation context.
4. Collect each subagent's returned verdict list (one entry per page in its
   batch: `{page, accepted, region_count}` or `{page, terminal_error: true,
   errors}`). If a subagent reports a page unresolved without hitting
   `terminal_error` (for example, it ran out of turns), re-spawn a fresh
   subagent for only that page — `ingest_get_page` returns its existing draft
   and last error, so the new subagent picks up where the last one stopped
   rather than starting cold.
5. Once every page is `accepted` or explicitly chosen as missing, call
   `ingest_finalize(session_id, allow_missing_pages: [...])`.
6. If the orchestrator itself is interrupted and restarted, it calls
   `ingest_status(slug)` to recompute the per-page ladder from disk (see
   "Session state and resuming") and re-spawns subagents only for the batches
   with pages not yet `accepted`. It does not need to have retained
   `session_id` across the restart — `ingest_status(slug)` finds it.

**Batch-worker instructions, given verbatim to each page-batch subagent:**

> You are given a `session_id` and a list of page numbers. For each page, in
> order: call `ingest_get_page(session_id, page)`. Open the returned image
> path with your image-reading tool and read it alongside `masked_regions`.
> If the response includes `existing_corrections`, `existing_gold_draft`, or
> `last_error`, you are correcting earlier work — edit that draft, don't
> restart it. Follow `instructions` in the response to produce overrides and
> Gold groups, then call `ingest_submit_page`. On a rejection, fix only the
> named fields and resubmit; after the same page is rejected three times,
> stop retrying it and record it as `terminal_error` with its last error
> attached. When every page in your list is either accepted or
> `terminal_error`, return only a list of `{page, accepted, region_count}` or
> `{page, terminal_error, errors}` — one entry per page, nothing else. Do not
> return image content, full region text, or your intermediate reasoning.

This is safe to run concurrently across subagents and batches because no two
pages ever write the same file: `ingest_submit_page` only writes
`detected/<n>.*`, `layout/<n>.json`, and `gold/<slug>/units/<n>.json` for the
page it was called with, and `ingest_status` recomputes its answer from disk
on every call rather than reading a shared mutable status field (see "Session
state and resuming"). Two subagents submitting different pages of the same
session at the same moment therefore cannot race on each other's writes; the
only shared object either of them touches is the append-only
`detected/<n>.gold_attempts.jsonl` for their own page, never another page's,
and never the session's own identity record.

`ingest_get_page` is the image hand-off: it returns a local PNG path to that
page's overlay image, on every adapter — see "Agent interface," above, for
why this package never hands back inline image bytes. A batch-worker
subagent's host must be able to load an image from a filesystem path into its
model context and have filesystem access to the configured artifact root; a
host with neither cannot complete this step, regardless of whether it runs as
an orchestrator or a page-batch subagent.

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
