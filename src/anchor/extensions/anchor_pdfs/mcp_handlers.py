"""MCP tool definitions backed by IngestService and DocStore."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService, SynopsisService


# ── Byte-fetch envelope ────────────────────────────────────────────────────
#
# Read endpoints that return binary blobs (page images, region crops, raw
# PDFs) share a single response envelope: an agent on the same host can
# read the path directly; a remote agent (or an in-memory store) gets the
# bytes inlined as base64. The envelope makes the contract explicit and
# lets the agent decide once, up front, which transport it wants.
def _byte_envelope(path: Path | None, *, fmt: str, fallback_ext: str = "") -> str:
    if path is None:
        return json.dumps({"error": "not found"})
    is_memory = str(path).startswith("memory://")
    if fmt == "path":
        if is_memory:
            return json.dumps({"error": "in-memory store has no real path; request format=base64"})
        return json.dumps({"format": "path", "value": str(path), "content_type": _ctype(path, fallback_ext)})
    if fmt == "base64":
        if is_memory:
            # Memory store can't read by path; the caller has nothing to
            # decode. Surface a clear error so the agent doesn't burn
            # tokens on an empty payload.
            return json.dumps({"error": "in-memory store does not expose bytes via MCP yet"})
        try:
            raw = path.read_bytes()
        except OSError as e:
            return json.dumps({"error": f"read failed: {e}"})
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": _ctype(path, fallback_ext),
            "size_bytes": len(raw),
        })
    return json.dumps({"error": f"unknown format: {fmt!r} (use 'path' or 'base64')"})


def _ctype(path: Path, fallback_ext: str) -> str:
    guess, _ = mimetypes.guess_type(path.name or f"x{fallback_ext}")
    return guess or "application/octet-stream"


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "ingest_pdf",
            "description": (
                "Ingest a PDF through bronze → silver → gold. Returns a summary. "
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
        # ── Harness-driven ingestion protocol (no API key needed) ───────
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
                    "rel_path": {"type": "string", "description": "Like '4/r1.png' — comes from region.crops.{png,svg,pdf}."},
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
                "Persist a region derived from an existing gold region — the "
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
                "issuing a semantic search — the client should load the "
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


_SESSION_TOOL_NAMES = {
    "ingest_begin", "ingest_get_page", "ingest_submit_page",
    "ingest_status", "ingest_finalize", "ingest_abort",
}


async def _call_session_tool(
    ingest_session: IngestSessionService, name: str, args: dict[str, Any],
) -> str:
    if name == "ingest_begin":
        path = Path(args["pdf_path"])
        if not path.exists():
            return json.dumps({"error": f"PDF not found: {path}"})
        order = await ingest_session.ingest_begin(
            path.read_bytes(), path.name,
            slug=args.get("slug"),
            dpi=args.get("dpi"),
            force=args.get("force", False),
        )
        return json.dumps(order)
    if name == "ingest_get_page":
        item = await ingest_session.ingest_get_page(args["session_id"], int(args["page"]))
        if "error" in item:
            return json.dumps(item)
        image_path = item.pop("image_path", None)
        item["image"] = json.loads(_byte_envelope(
            Path(image_path) if image_path else None,
            fmt=args.get("format", "path"),
            fallback_ext=".png",
        ))
        return json.dumps(item)
    if name == "ingest_submit_page":
        verdict = await ingest_session.ingest_submit_page(
            args["session_id"], int(args["page"]),
            regions=args.get("regions") or [],
            polished_md=args.get("polished_md"),
            protocol_version=args.get("protocol_version"),
        )
        return json.dumps(verdict)
    if name == "ingest_status":
        return json.dumps(await ingest_session.ingest_status(
            args.get("session_id"), slug=args.get("slug"),
        ))
    if name == "ingest_finalize":
        return json.dumps(await ingest_session.ingest_finalize(
            args["session_id"],
            allow_missing_pages=args.get("allow_missing_pages"),
            declared_model=args.get("declared_model"),
        ))
    if name == "ingest_abort":
        return json.dumps(await ingest_session.ingest_abort(args["session_id"]))
    return json.dumps({"error": f"unknown session tool: {name}"})


async def call_tool(
    ingest: IngestService, store: DocStore, name: str, args: dict[str, Any],
    *, synopsis: SynopsisService | None = None,
    ingest_session: IngestSessionService | None = None,
) -> str:
    if name in _SESSION_TOOL_NAMES:
        if ingest_session is None:
            return json.dumps({"error": "harness ingest sessions not wired on this server"})
        return await _call_session_tool(ingest_session, name, args)
    if name == "ingest_pdf":
        from pathlib import Path
        path = Path(args["pdf_path"])
        if not path.exists():
            return json.dumps({"error": f"PDF not found: {path}"})
        pdf_bytes = path.read_bytes()
        summary = await ingest.ingest_pdf(
            pdf_bytes, path.name,
            slug=args.get("slug"),
            polish=not args.get("skip_polish", False),
            regions=not args.get("skip_regions", False),
            force=args.get("force", False),
        )
        return json.dumps(summary)
    if name == "list_documents":
        return json.dumps(await store.list_documents())
    if name == "list_active_ingests":
        from anchor.core.clock import SystemClock
        from anchor.extensions.anchor_pdfs.core.ingest_activity import (
            IngestActivityRegistry,
        )
        registry = IngestActivityRegistry(store=store, _now=SystemClock().now)
        activities = await registry.snapshot()
        return json.dumps({"ingests": [a.to_dict() for a in activities]})
    if name == "get_ingest_status":
        from anchor.core.clock import SystemClock
        from anchor.extensions.anchor_pdfs.core.ingest_activity import (
            IngestActivityRegistry,
        )
        registry = IngestActivityRegistry(store=store, _now=SystemClock().now)
        activity = await registry.get(args["slug"])
        if activity is None:
            return json.dumps({"slug": args["slug"], "found": False})
        return json.dumps({"found": True, **activity.to_dict()})
    if name == "get_document_index":
        out = await store.get_index(args["slug"])
        return json.dumps(out) if out else json.dumps({"error": "not found"})
    if name == "get_gold_regions":
        return json.dumps(await store.get_regions(args["slug"], page=args.get("page")))
    if name == "get_page_text":
        text = await store.get_page_text(args["slug"], int(args["page"]))
        return text if text is not None else json.dumps({"error": "not found"})
    if name == "locate_text":
        path = await store.get_raw_pdf_path(args["slug"])
        if path is None or str(path).startswith("memory://"):
            return json.dumps({"error": f"raw PDF not available for slug: {args['slug']}"})
        try:
            quads = await ingest.renderer.locate_text(
                path, int(args["page"]), args["query"], args.get("within_bbox"),
            )
        except (IndexError, ValueError) as e:
            return json.dumps({"error": str(e)})
        return json.dumps({
            "slug": args["slug"], "page": int(args["page"]),
            "query": args["query"], "quads": quads,
        })
    if name == "get_gold_map":
        out = await store.get_gold_map(args["slug"])
        return json.dumps(out) if out is not None else json.dumps({"error": "not found"})
    if name == "get_page_image":
        path = await store.get_page_image_path(args["slug"], int(args["page"]))
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=".png")
    if name == "get_crop":
        path = await store.get_crop_path(args["slug"], args["rel_path"])
        # Content-type inference falls back to the extension of rel_path
        # for memory-backed stores that return None.
        ext = "." + args["rel_path"].rsplit(".", 1)[-1] if "." in args["rel_path"] else ""
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=ext)
    if name == "get_pdf":
        path = await store.get_raw_pdf_path(args["slug"])
        return _byte_envelope(path, fmt=args.get("format", "path"), fallback_ext=".pdf")
    if name == "embed_document":
        if ingest.embedder is None:
            return json.dumps({"error": "no embedder wired"})
        slug = args["slug"]
        existing = await store.get_embeddings(slug)
        if existing and not args.get("overwrite", False):
            return json.dumps({
                "slug": slug, "skipped": True, "reason": "already embedded",
                "embed_model": existing.get("embed_model"),
            })
        n = await ingest.embed_document(slug)
        return json.dumps({"slug": slug, "embedded": n, "embed_model": ingest.embed_model_id})
    if name == "search_documents":
        try:
            return json.dumps(await ingest.search(args["query"], k=int(args.get("k", 10))))
        except RuntimeError as e:
            return json.dumps({"error": str(e)})
    if name == "derive_region":
        try:
            return json.dumps(
                await ingest.derive_region(
                    args["slug"], args["parent_region_id"], args["region"]
                )
            )
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})
    if name == "get_embeddings_meta":
        slug = args["slug"]
        data = await store.get_embeddings(slug)
        if data is None:
            return json.dumps({"error": f"no embeddings for {slug}"})
        return json.dumps({
            "slug": slug,
            "embed_model": data.get("embed_model"),
            "dim": data.get("dim"),
            "embedded_at": data.get("embedded_at"),
            "vector_count": len(data.get("vectors", [])),
        })
    if name == "extract_pointed":
        from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
            PointedExtractionError,
        )
        try:
            return json.dumps(await ingest.extract_pointed(
                args["slug"],
                select=args.get("select"),
                shape=args.get("shape"),
            ))
        except PointedExtractionError as e:
            return json.dumps({"error": str(e)})
    if name == "compose_synopsis":
        if synopsis is None:
            return json.dumps({"error": "synopsis service not wired (renderer/store missing)"})
        slug = args["slug"]
        entity = args["entity"]
        output = args.get("output", "json")
        try:
            if output == "json":
                from dataclasses import asdict
                data = await synopsis.compose(slug=slug, entity=entity)
                return json.dumps(asdict(data))
            if output == "pdf":
                pdf_bytes = await synopsis.render_pdf(slug=slug, entity=entity)
                return json.dumps({
                    "format": "base64",
                    "value": base64.b64encode(pdf_bytes).decode("ascii"),
                    "content_type": "application/pdf",
                    "size_bytes": len(pdf_bytes),
                })
            if output == "md":
                md = await synopsis.render_markdown(
                    slug=slug, entity=entity,
                    crop_url_base=args.get("crop_url_base"),
                )
                return json.dumps({"format": "text", "value": md, "content_type": "text/markdown"})
            return json.dumps({"error": f"unknown output: {output}"})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
