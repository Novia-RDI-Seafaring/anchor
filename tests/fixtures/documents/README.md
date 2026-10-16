# Real document fixtures

`synthetic-process-pump-datasheet.pdf` is the exact maintainer-supplied,
four-page PX-42 document. It identifies itself as original ANCHOR author-created
demonstration material, with fictional values and no vendor content. Its values
are for software testing and demonstrations, not engineering decisions.

SHA256: `c9966c8f9b7ccef0e1cbdcf4fbc26b51014f7b627210180f8321546eac601f32`

The normal suite checks the checksum and original page count. Run the real
pipeline and adapter checks explicitly after caching Docling's models:

```bash
uv run --extra dev pytest -m slow tests/extensions/anchor_pdfs/test_px42_document_slow.py
```

These tests use the production CPU Docling extractor, PyMuPDF renderer, text
ingest, filesystem stores, inspection and provenance paths. They ingest every
page, check stable silver membership and complete meaningful-item coverage,
and exercise actual HTTP, MCP and CLI search, inspection, extraction and cell
resolution. Page-2 values include `600 kPa (6 bar)` maximum inlet pressure and
`-10 to 140 degrees C` process temperature. Independent original-PDF glyph
checks allow two points for font-leading differences. The page-3 five-column
performance table remains inspectable without invented scalar pairings.

`px42.py` supplies the reusable runtime and `FixtureLexicalEmbedder`. Only the
embedding dependency is deterministic: normalized hashed token counts, model
ID `fixture-lexical-sha256-256-v1`. PDF content, extraction, cells, geometry,
stores and transport handlers are real. This checks retrieval plumbing, not
a live semantic provider's ranking. No paid calls, vision model, provider
client or provider configuration file is required. Full integration tests are
marked `slow` and excluded from the default CI run. They require cached CPU
Docling models and run with model-network access disabled.

For isolated app checks, build a runtime with `build_px42_runtime(data_dir)`,
ingest this file with `profile="text"`, and pass it to `build_app`. Serve the
current frontend using a disposable runtime data directory. Use inspected source
refs to populate demonstration spec rows; then verify source badges, the real
PDF and page navigation. Document-node data uses `slug: "px42"`; spec-row
citations use `source_ref.slug`. This fixture's lexical dependency does not
validate browser semantic query embedding. For a separate real local-model
smoke, use the production `OnnxEmbedder` with its default model, re-index a copy
of the extracted corpus, and query the actual search API. Record the model ID,
dimensions and rankings separately from deterministic test results. Do not
describe a fixture-only query as live browser semantic search. Keep logs and screenshots
outside the committed fixture directory. Preserve the PDF bytes when creating
visual overlays or crops.
