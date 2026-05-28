## `anchor_pdfs` — ingest engineering PDFs

Bronze → silver → gold pipeline that turns each page into structured
regions tagged with the page number and bounding box they came from.

### Tools

- `ingest_pdf(pdf_path, slug?, skip_polish?, skip_regions?)` — runs the
  full pipeline; idempotent if the slug already exists.
- `list_documents()` — every document and its current status.
- `get_document_index(slug)` — silver outline (sections, tables, figures).
- `get_gold_regions(slug, page?)` — structured regions with `page + bbox`.
- `get_page_text(slug, page)` — polished or raw page markdown.

### Typical flow

When the user drops a PDF and asks for specs on the canvas:

1. `list_documents()` first — skip ingest if the slug is already golded.
2. `ingest_pdf(pdf_path="/abs/path/to/datasheet.pdf")` only if needed.
3. `get_gold_regions(slug=..., page=2)` to get region IDs and bboxes.
4. Place a `document` node on the canvas via `canvas_add_node`.
5. Place a `spec` node whose `data.rows` reference the regions, and an
   `anchored` evidence edge from each row to the document node.

### Common errors

- `404 / unknown slug` → run `list_documents()` to see what's available.
- `400 / file is not a PDF` → ANCHOR only ingests PDFs in this extension.
- `gold extraction skipped` in the status → no `ANCHOR_OPENAI_API_KEY`
  set; silver is still queryable but regions aren't structured.
