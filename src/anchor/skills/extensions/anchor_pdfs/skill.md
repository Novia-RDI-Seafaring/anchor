## `anchor_pdfs` — ingest engineering PDFs

Bronze → silver → gold pipeline that turns each page into structured
regions tagged with the page number and bounding box they came from.

### Tools

- `ingest_pdf(pdf_path, slug?, skip_polish?, skip_regions?)` — runs the
  full pipeline; idempotent if the slug already exists.
- `search_documents(query, k?)` — **semantic search** across every
  embedded gold region. Returns ranked hits with `slug, page, region_id,
  text, score`. This is how you "find stuff" in the documents by meaning,
  not by guessing a page. CLI `anchor search "<query>"`, HTTP
  `GET /api/search?q=…`. Embeddings are created during `ingest_pdf`; if a
  doc was ingested without them, run `embed` first (`anchor embed`).
- `list_documents()` — every document and its current status.
- `get_document_index(slug)` — silver outline (sections, tables, figures).
- `get_gold_regions(slug, page?)` — structured regions with `page + bbox`.
- `get_page_text(slug, page)` — polished or raw page markdown.

### Finding content — search first, then retrieve

To answer "what does this document say about X" or "find the pricing /
the flow rate / the warranty", **start with `search_documents(query)`** —
it ranks gold regions across all documents by meaning. Each hit already
carries its `slug, page, region_id`, so follow up with
`get_gold_regions(slug, page=…)` or `get_page_text(slug, page)` to read
the full context and cite the page + bbox. Do not page through every
region by hand or re-read whole documents when search points you at the
right region directly.

### Typical flow

When the user drops a PDF and asks for specs on the canvas:

1. `list_documents()` first — skip ingest if the slug is already golded.
2. `ingest_pdf(pdf_path="/abs/path/to/datasheet.pdf")` only if needed.
3. `search_documents("flow rate")` to locate the right region(s), or
   `get_gold_regions(slug=..., page=2)` when you already know the page.
4. Place a `document` node on the canvas via `canvas_add_node`.
5. Place a `spec` node whose `data.rows` reference the regions, and an
   `anchored` evidence edge from each row to the document node.

### Common errors

- `404 / unknown slug` → run `list_documents()` to see what's available.
- `400 / file is not a PDF` → ANCHOR only ingests PDFs in this extension.
- `gold extraction skipped` in the status → no `ANCHOR_OPENAI_API_KEY`
  set; silver is still queryable but regions aren't structured.
