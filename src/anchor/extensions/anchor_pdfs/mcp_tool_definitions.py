"""Declarative MCP tool catalog for the PDF extension."""

from __future__ import annotations

from typing import Any


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "ingest_pdf",
            "description": (
                "Ingest a PDF through bronze -> silver -> gold. Returns a summary. "
                "Idempotent: if the slug already has gold it returns {skipped: true} "
                "without recomputing; pass force=true to re-ingest and overwrite."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string"},
                    "slug": {"type": "string"},
                    "skip_polish": {"type": "boolean"},
                    "skip_regions": {"type": "boolean"},
                    "force": {"type": "boolean"},
                },
                "required": ["pdf_path"],
            },
        },
        # -- Harness-driven ingestion protocol (no API key needed) -------
        # The agent itself performs polish + region grouping, page by page,
        # against a journaled staging session. Mechanical steps (docling,
        # PNGs, embeddings, validation, atomic publish) stay server-side.
        {
            "name": "ingest_begin",
            "description": (
                "Open a harness ingest session: runs the mechanical front half "
                "(bronze, docling, silver, page images, candidate boxes) and "
                "returns a work order {session_id, page_count, pages[]}. "
                "Idempotent: published gold returns {skipped: true} unless "
                "force; an open session for the slug is resumed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string"},
                    "slug": {"type": "string"},
                    "dpi": {"type": "integer"},
                    "force": {"type": "boolean"},
                },
                "required": ["pdf_path"],
            },
        },
        {
            "name": "ingest_get_page",
            "description": (
                "Work item for one page of a harness ingest session: page image "
                "(path by default; format='base64' from off-machine agents), raw "
                "markdown, candidate boxes {id, label, bbox, text}, and the "
                "per-page instructions."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "page": {"type": "integer"},
                    "format": {"type": "string", "enum": ["path", "base64"], "default": "path"},
                },
                "required": ["session_id", "page"],
            },
        },
        {
            "name": "ingest_submit_page",
            "description": (
                "Submit one polished page to the staging session. Each region: "
                "{kind, title, description?, member_item_ids: [candidate ids], "
                "tags?, entities?} - the server computes bbox from the members; "
                "for a logical sub-table use table_slice: {candidate_id, rows, "
                "columns?} to compute cell-level content and bbox; "
                "send approx_bbox [l,t,r,b] (BOTTOMLEFT) only when no candidate "
                "covers the visual. Idempotent per page (resubmit replaces). "
                "Returns {accepted, errors?} - repair named fields and resubmit."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "page": {"type": "integer"},
                    "regions": {"type": "array", "items": {"type": "object"}},
                    "polished_md": {"type": "string"},
                    "protocol_version": {"type": "integer"},
                },
                "required": ["session_id", "page", "regions"],
            },
        },
        {
            "name": "ingest_status",
            "description": (
                "Resume surface for harness ingest: pages done/remaining and the "
                "session state, by session_id or by slug ('continue ingesting X')."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "slug": {"type": "string"},
                },
            },
        },
        {
            "name": "ingest_finalize",
            "description": (
                "Finalize a harness ingest session: verifies every page is "
                "submitted (or listed in allow_missing_pages), embeds regions "
                "locally, and publishes staging to gold atomically. Pass "
                "declared_model with your own model id for the ingest report."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "allow_missing_pages": {"type": "array", "items": {"type": "integer"}},
                    "declared_model": {"type": "string"},
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "ingest_abort",
            "description": "Abort a harness ingest session and discard its staged pages.",
            "inputSchema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
        {
            "name": "list_documents",
            "description": "List ingested documents.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_active_ingests",
            "description": (
                "List ingests in flight for this project, including ones started "
                "by the CLI, another agent, or the web UI. Each entry: {slug, "
                "filename, stage, current, total, pct, status, started_at}. Call "
                "this before assuming an ingest finished, or to show progress."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_ingest_status",
            "description": (
                "Report the live ingest-activity record for one document slug: "
                "its current stage, progress, and terminal state (done / failed "
                "+ failed stage). Returns {found: false} when nothing is ingesting "
                "or has recently ingested that slug. Use it to poll a specific "
                "ingest you (or another process) kicked off."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "get_document_index",
            "description": "Silver index for a document (outline, tables, figures).",
            "inputSchema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "get_gold_regions",
            "description": "Gold regions for a document; optionally filter to one page.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "get_page_text",
            "description": "Polished or raw markdown for one page.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["slug", "page"],
            },
        },
        {
            "name": "locate_text",
            "description": (
                "Find where a value/text appears on a page and return its "
                "page-space quad(s) in the same coordinate convention region "
                "bboxes use. Pass within_bbox (a region's bbox) to disambiguate "
                "a value that repeats elsewhere on the page. Returns an empty "
                "quads list when the text is not found (caller falls back to the "
                "region-level highlight). Powers the value-precise highlight in "
                "the canvas doc preview and PDF viewer."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "page": {"type": "integer"},
                    "query": {"type": "string", "description": "The text to locate."},
                    "within_bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "Optional [left, top, right, bottom] region clip.",
                    },
                },
                "required": ["slug", "page", "query"],
            },
        },
        {
            "name": "get_gold_map",
            "description": "Full gold extraction: document metadata + outline + all regions + per-page meta.",
            "inputSchema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "get_page_image",
            "description": "Page screenshot as a path (default) or base64. Use format='base64' from off-machine agents.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "page": {"type": "integer"},
                    "format": {"type": "string", "enum": ["path", "base64"], "default": "path"},
                },
                "required": ["slug", "page"],
            },
        },
        {
            "name": "get_crop",
            "description": "A gold-extracted region crop (PNG/SVG/PDF) by its rel_path (returned by get_gold_regions). Path or base64.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "rel_path": {"type": "string", "description": "Like '4/r1.png' - comes from region.crops.{png,svg,pdf}."},
                    "format": {"type": "string", "enum": ["path", "base64"], "default": "path"},
                },
                "required": ["slug", "rel_path"],
            },
        },
        {
            "name": "get_pdf",
            "description": "The original bronze-layer PDF for a document, as a path or base64.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "format": {"type": "string", "enum": ["path", "base64"], "default": "path"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "embed_document",
            "description": (
                "Embed gold regions of a document and persist embeddings.json. "
                "Auto-runs after ingest_pdf; this tool backfills already-ingested docs "
                "without re-running the full pipeline. Set overwrite=true to re-embed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "search_documents",
            "description": (
                "Semantic search across every gold-extracted, embedded document. "
                "Returns top-k {slug, page, region_id, text, score} grounded hits. "
                "Also returns skipped documents when their stored embed_model "
                "does not match the query embedder. "
                "Use the returned (slug, page, region_id) with get_crop or "
                "canvas.add_node to surface evidence on the canvas."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "derive_region",
            "description": (
                "Persist a region derived from an existing gold region - the "
                "consumer side of an OIP region producer. Give the parent "
                "region id and the new region; it inherits the parent's "
                "source_ref (so provenance points at the same page and bbox) "
                "and records derived_from, then stores it durably. Example: a "
                "chart digitizer returns a chart_series; derive_region files it "
                "beside the chart region it came from. Re-run `embed` to make "
                "it searchable."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "parent_region_id": {"type": "string"},
                    "region": {
                        "type": "object",
                        "description": "The derived region: id, kind, title, content.data, ...",
                    },
                },
                "required": ["slug", "parent_region_id", "region"],
            },
        },
        {
            "name": "get_embeddings_meta",
            "description": (
                "Return metadata about a document's embeddings (model id, "
                "dimension, vector count, embedded_at timestamp). Useful for "
                "verifying which embed_model a doc was indexed with before "
                "issuing a semantic search - the client should load the "
                "matching WASM bundle on its side."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "extract_pointed",
            "description": (
                "Pointed extraction: pull a selected set of regions/entities out of "
                "a gold-extracted document into a caller-defined JSON shape, with "
                "every filled leaf grounded to its source cell. select = any of "
                "{regions: ['p2/r4'], pages: [2,3], entity: 'LKH-5'} (entity reuses "
                "synopsis scoping). shape is by-example (leaf types: string, number, "
                "quantity, bool, or nested object/array) OR a JSON Schema. Returns "
                "{doc_slug, data (filled to the shape), provenance (JSON-Pointer -> "
                "source_ref {page, region_id, bbox, quote}), unfilled (JSON-Pointers "
                "the source did not cover)}. Leaves are never guessed: a leaf is "
                "either filled from a real cell with provenance or listed in unfilled."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "select": {
                        "type": "object",
                        "description": (
                            "Any of regions (['p2/r4']), pages ([2,3]), entity "
                            "('LKH-5'). Empty selects every gold region."
                        ),
                        "properties": {
                            "regions": {"type": "array", "items": {"type": "string"}},
                            "pages": {"type": "array", "items": {"type": "integer"}},
                            "entity": {"type": "string"},
                        },
                    },
                    "shape": {
                        "type": "object",
                        "description": (
                            "By-example shape (leaf types string|number|quantity|bool, "
                            "or nested object/array) or a JSON Schema."
                        ),
                    },
                },
                "required": ["slug", "shape"],
            },
        },
        {
            "name": "compose_synopsis",
            "description": (
                "Compose an entity-scoped synopsis from a document's gold-layer data. "
                "Returns the structured SynopsisData (JSON) by default; pass "
                "output='pdf' or output='md' for a rendered artefact (base64 PDF or "
                "raw Marp markdown text)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "entity": {"type": "string", "description": "e.g. 'LKH-5'"},
                    "output": {
                        "type": "string",
                        "enum": ["json", "pdf", "md"],
                        "default": "json",
                    },
                    "crop_url_base": {
                        "type": "string",
                        "description": "(md only) URL prefix for crop references in the markdown.",
                    },
                },
                "required": ["slug", "entity"],
            },
        },
    ]
