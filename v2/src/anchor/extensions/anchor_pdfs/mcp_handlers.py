"""MCP tool definitions backed by IngestService and DocStore."""
from __future__ import annotations

import json
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService


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
    ]


async def call_tool(
    ingest: IngestService, store: DocStore, name: str, args: dict[str, Any],
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
    return json.dumps({"error": f"unknown tool: {name}"})
