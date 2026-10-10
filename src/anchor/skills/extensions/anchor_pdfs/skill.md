## `anchor_pdfs` — ingest engineering PDFs

Bronze → silver → gold pipeline that turns each page into structured
regions tagged with the page number and bounding box they came from.

### Tools

- `ingest_pdf(pdf_path, slug?, skip_polish?, skip_regions?, force?)` — runs the
  full pipeline. **Idempotent:** if the slug already has gold it returns
  `{skipped: true}` without recomputing (the gold stage is billed). Pass
  `force=true` (CLI `--force`) to re-ingest and overwrite.

  There are TWO ingestion pathways; do not conflate them. `ingest_pdf`
  (CLI `anchor ingest`) is the BUILT-IN pipeline: Anchor's own configured
  LLM does the polish and region extraction, which needs an API key. The
  HARNESS-DRIVEN session protocol (`ingest_begin` through
  `ingest_finalize`, described below) is the no-key pathway where you,
  the agent, do that extraction work yourself. If the user asks for
  "harness ingestion", "agent-driven ingestion", or "no-key ingestion"
  by name, use the session protocol; calling `anchor ingest` is not the
  harness pathway.
- `search_documents(query, k?)` — **semantic search** across every
  embedded gold region. Returns ranked hits with `slug, page, region_id,
  text, score`. This is how you "find stuff" in the documents by meaning,
  not by guessing a page. CLI `anchor search "<query>"`, HTTP
  `GET /api/search?q=…`. Embeddings are created during `ingest_pdf`; if a
  doc was ingested without them, run `embed` first (`anchor embed`). Search
  text includes title, description, tags, entities and source content. Run
  `anchor embed <slug>` again to include metadata in an existing index.
- `list_documents()` — every document and its current status.
- `list_entities(slug)` - what a document is ABOUT: every entity its gold
  regions name, with counts and pages. A title and a page count do not tell
  you that a four-page leaflet covers thirteen product models. Call this
  before concluding what a document contains, and before telling a user the
  corpus holds only one of something.
- `get_document_index(slug)` - a map of the document: outline, plus one
  entry per table and figure with its caption, shape, header row,
  first-column values, page and bbox. Table cell content is left out;
  read a table with `get_page_text(slug, page)` or, on a gold document,
  `inspect_region`. `include_content=true` returns every cell in one
  result and is much larger, so reach for it only when you truly need
  the whole document at once.
- `get_gold_regions(slug, page?)` — structured regions with `page + bbox`.
- `inspect_region(slug, region_id)` - one region's metadata, stable silver
  membership, source content, table cells and `source_ref`. Qualify a search
  hit with its page: hit `page=2, region_id="r1"` becomes `"p2/r1"`.
  CLI `anchor inspect-region <slug> p2/r1`.
- `get_region_content(slug, region_id)` - the region's stored or reconstructed
  source markdown and cells. Use the same page-qualified locator when
  inspection has no stored content. CLI `anchor region-content <slug> p2/r1`.
- `get_page_text(slug, page)` — polished or raw page markdown.
- `get_crop(slug, "<page>/<region_id>.png")` - LOOK at one region: the crop
  comes back as an image the harness displays, so you can read a chart,
  diagram or scanned table by eye. `get_page_image(slug, page)` does the
  same for a whole page. Use these rather than opening files under
  `.anchor_data/` yourself; reading the store directly bypasses the tool
  surface and may not even be permitted.

### Finding content - search, inspect, answer

To answer "what does this document say about X" or "find the pricing /
the flow rate / the warranty", **start with `search_documents(query)`**.
It ranks gold regions across all documents by meaning. For each relevant
hit, call `inspect_region(hit.slug, "p<page>/<region_id>")` using the hit's
page and region id. Page qualification prevents selecting a different
page's region with the same local id.

Read the inspected source content and cells before answering. A title,
description, tag or entity explains why a hit ranked; it is not evidence
for a value. If stored content is absent, call `get_region_content` with
the same locator. Cite the returned `source_ref`, using the silver item
or cell locator when available, or the region/page/bbox otherwise.
Use `get_page_text` for adjacent context and `get_crop` for visual evidence
when needed. If you already know the exact region locator, inspect it
directly. Search and inspection avoid re-reading whole documents.

### Typical flow

When the user drops a PDF and asks for specs on the canvas:

1. `list_documents()` first — skip ingest if the slug is already golded.
2. `ingest_pdf(pdf_path="/abs/path/to/datasheet.pdf")` only if needed.
3. `search_documents("flow rate")` to locate the right region(s).
4. Inspect each hit with `inspect_region(slug, "p<page>/<region_id>")`.
   Read its source content/cells, using `get_region_content` if needed,
   before extracting values or answering.
5. Place one `spec` node whose `data.rows` each carry a `source_ref` naming
   the document slug, page, and available region/item/cell/bbox locator.
   For a fact, put the reference in the node's `data.source_ref`.
6. The Sources dock shows those documents automatically. Place a `document`
   card or an explicit `anchored` evidence edge only when useful for the
   presentation; neither is required for a source citation. A citation alone
   does not establish a validated claim binding or Verified row status.

### Common errors

- `404 / unknown slug` → run `list_documents()` to see what's available.
- `400 / file is not a PDF` → ANCHOR only ingests PDFs in this extension.
- `gold extraction skipped` in the status → no `ANCHOR_OPENAI_API_KEY`
  set; silver is still queryable but regions aren't structured. With
  provider `harness` this is expected for `ingest_pdf` - use the
  harness-driven session protocol below instead.

### Harness-driven ingestion (you are the extraction model, no API key)

Use this protocol when EITHER applies: the project's provider is
`harness` (check `anchor_status` or `anchor check`), OR the user
explicitly asks for harness/agent-driven/no-key ingestion, regardless
of the configured provider. YOU are the extraction model. Under
provider `harness`, `ingest_pdf` will not produce gold; drive the
session protocol:

1. `ingest_begin(pdf_path)` - Anchor runs docling + page images and
   returns `{session_id, page_count, pages[]}`. If it returns
   `resumed: true`, some pages are already done - check `pages[].status`.
2. Per page: `ingest_get_page(session_id, page)` gives the page image
   (read the returned path with your file tools), the raw markdown, and
   `candidates` (docling boxes with stable ids). Follow the returned
   `instructions`. Then `ingest_submit_page(session_id, page,
   polished_md, regions)`.
   - Name region geometry with `member_item_ids: ["p3-i0", "p3-i1"]`;
     the server computes the bbox. Use `approx_bbox` only when no
     candidate covers a visual.
   - For one logical part of a table, use `table_slice` with the table
     candidate id and exact `rows` plus optional `columns`, for example
     `{"candidate_id": "p3-i2", "rows": [0, 4, 5], "columns": [0, 1]}`.
     Candidate cells provide the indexes. The server keeps only those cells
     and computes cell-level content and bbox provenance.
   - A rejection returns `errors` naming the bad fields; fix and
     resubmit (resubmitting a page replaces it).
3. For documents over ~4 pages, fan out: spawn subagents, each given
   the `session_id` and a contiguous batch of 3-5 pages, returning only
   the submit verdicts. Pages are independent; submits are idempotent.
4. When `ingest_status(session_id)` shows nothing remaining, call
   `ingest_finalize(session_id, declared_model="<your model id>")` -
   Anchor embeds locally and publishes gold atomically.
5. Interrupted or fresh context? `ingest_status(slug="<doc>")` shows
   pages done/remaining; continue from there. `ingest_abort` discards
   staging.

Write descriptions that would rank well in semantic search: name the
quantities and entities ("Max flow, head and motor sizes for LKH-5 to
LKH-90"), not vague labels ("a table with numbers").

CLI parity for shell-only harnesses: `anchor ingest-session
begin|get-page|submit-page|status|finalize|abort` (JSON in/out).
Always pass `--data-dir <data_dir from the begin work order>` on every
command: the default resolves from the directory you invoke from, so a
`cd` between sibling commands silently switches projects and the session
appears unknown.
