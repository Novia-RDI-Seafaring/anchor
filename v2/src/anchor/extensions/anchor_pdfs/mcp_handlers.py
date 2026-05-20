"""MCP tool definitions backed by IngestService and DocStore."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

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
            "description": "Ingest a PDF through bronze → silver → gold. Returns summary.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string"},
                    "slug": {"type": "string"},
                    "skip_polish": {"type": "boolean"},
                    "skip_regions": {"type": "boolean"},
                },
                "required": ["pdf_path"],
            },
        },
        {
            "name": "list_documents",
            "description": "List ingested documents.",
            "inputSchema": {"type": "object", "properties": {}},
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


async def call_tool(
    ingest: IngestService, store: DocStore, name: str, args: dict[str, Any],
    *, synopsis: SynopsisService | None = None,
) -> str:
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
        )
        return json.dumps(summary)
    if name == "list_documents":
        return json.dumps(await store.list_documents())
    if name == "get_document_index":
        out = await store.get_index(args["slug"])
        return json.dumps(out) if out else json.dumps({"error": "not found"})
    if name == "get_gold_regions":
        return json.dumps(await store.get_regions(args["slug"], page=args.get("page")))
    if name == "get_page_text":
        text = await store.get_page_text(args["slug"], int(args["page"]))
        return text if text is not None else json.dumps({"error": "not found"})
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
