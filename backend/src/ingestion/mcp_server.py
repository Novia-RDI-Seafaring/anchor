"""Anchor Ingestion MCP Server — expose pipeline as tools for AI agents.

Start with:
    python -m src.ingestion.mcp_server --data-dir ./data

Or add to Claude Code's MCP config:
    {
      "mcpServers": {
        "anchor-ingest": {
          "command": "python",
          "args": ["-m", "src.ingestion.mcp_server", "--data-dir", "/path/to/data"]
        }
      }
    }
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

# Will be set from CLI args
_data_dir: Path = Path("./data").resolve()


def _slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "doc"


def _find_slug(name: str) -> str:
    """Resolve a name to a slug."""
    slug = _slugify(Path(name).stem)
    silver = _data_dir / "silver"
    if (silver / slug).exists():
        return slug
    if silver.is_dir():
        for d in silver.iterdir():
            if d.is_dir() and slug in d.name:
                return d.name
    return slug


app = Server("anchor-ingest")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ingest_pdf",
            description="Ingest a PDF through the full pipeline (bronze → silver → gold). "
                        "Returns a summary with page count and region count.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "Absolute path to the PDF file"},
                    "slug": {"type": "string", "description": "Override slug name (optional)"},
                    "skip_polish": {"type": "boolean", "description": "Skip LLM markdown polishing", "default": False},
                    "skip_regions": {"type": "boolean", "description": "Skip gold region extraction", "default": False},
                },
                "required": ["pdf_path"],
            },
        ),
        Tool(
            name="list_documents",
            description="List all ingested documents with their pipeline status (silver/gold), page counts, and region counts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_document_status",
            description="Get detailed pipeline status for a document — what artifacts exist in bronze, silver, and gold layers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Document slug or filename"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="get_document_index",
            description="Get the silver index for a document: outline (sections with headings), tables (with headers and model values), and figures. "
                        "This is a compact table of contents showing what's in the document and on which pages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Document slug or filename"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="get_gold_regions",
            description="Get gold regions for a document — structured semantic blocks (spec_block, table, chart, diagram, figure, text) "
                        "with titles, descriptions, entities, tags, and crop image paths. Optionally filter to a specific page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Document slug or filename"},
                    "page": {"type": "integer", "description": "Filter to specific page number (optional)"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="get_page_text",
            description="Get the polished markdown text for a specific page of a document. "
                        "Falls back to raw deterministic markdown if polished version doesn't exist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Document slug or filename"},
                    "page": {"type": "integer", "description": "Page number (1-indexed)"},
                },
                "required": ["name", "page"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = _handle_tool(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


def _handle_tool(name: str, args: dict) -> str:
    if name == "ingest_pdf":
        return _tool_ingest(args)
    elif name == "list_documents":
        return _tool_list()
    elif name == "get_document_status":
        return _tool_status(args["name"])
    elif name == "get_document_index":
        return _tool_index(args["name"])
    elif name == "get_gold_regions":
        return _tool_regions(args["name"], args.get("page"))
    elif name == "get_page_text":
        return _tool_page_text(args["name"], args["page"])
    else:
        return f"Unknown tool: {name}"


def _tool_ingest(args: dict) -> str:
    from .pipeline import run_full_pipeline
    import shutil

    pdf_path = Path(args["pdf_path"]).resolve()
    if not pdf_path.exists():
        return f"PDF not found: {pdf_path}"

    # Copy to bronze
    bronze_dir = _data_dir / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_dir / pdf_path.name
    if not bronze_path.exists():
        shutil.copy2(pdf_path, bronze_path)

    slug = args.get("slug") or _slugify(pdf_path.stem)
    result = run_full_pipeline(
        pdf_path,
        _data_dir,
        slug=slug,
        polish=not args.get("skip_polish", False),
        regions=not args.get("skip_regions", False),
    )
    return json.dumps(result, indent=2)


def _tool_list() -> str:
    silver = _data_dir / "silver"
    gold = _data_dir / "gold"

    if not silver.is_dir():
        return "No documents ingested yet."

    docs = []
    for d in sorted(silver.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        index_path = d / "index.json"
        page_count = 0
        title = slug
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            page_count = idx.get("document", {}).get("page_count", 0)
            title = idx.get("document", {}).get("title", slug)

        has_gold = (gold / slug / "pages").is_dir() if gold.is_dir() else False
        region_count = 0
        if has_gold:
            for rf in (gold / slug / "pages").glob("*.regions.json"):
                rdata = json.loads(rf.read_text())
                region_count += len(rdata.get("regions", []))

        docs.append({
            "slug": slug, "title": title, "pages": page_count,
            "silver": True, "gold": has_gold, "regions": region_count,
        })

    return json.dumps(docs, indent=2)


def _tool_status(name: str) -> str:
    slug = _find_slug(name)
    status: dict = {"slug": slug, "bronze": False, "silver": False, "gold": False}

    bronze = _data_dir / "bronze"
    if bronze.is_dir():
        for f in bronze.iterdir():
            if _slugify(f.stem) == slug:
                status["bronze"] = True
                status["pdf"] = str(f)
                break

    silver_dir = _data_dir / "silver" / slug
    if silver_dir.is_dir():
        status["silver"] = True
        status["silver_files"] = [f.name for f in sorted(silver_dir.iterdir()) if f.is_file()]
        pages_dir = silver_dir / "pages"
        if pages_dir.is_dir():
            status["page_pngs"] = len(list(pages_dir.glob("*.png")))
            status["page_mds"] = len(list(pages_dir.glob("*.md"))) - len(list(pages_dir.glob("*.raw.md")))

    gold_dir = _data_dir / "gold" / slug
    if gold_dir.is_dir() and (gold_dir / "pages").is_dir():
        status["gold"] = True
        region_files = list((gold_dir / "pages").glob("*.regions.json"))
        status["gold_pages"] = len(region_files)
        total_regions = 0
        for rf in region_files:
            rdata = json.loads(rf.read_text())
            total_regions += len(rdata.get("regions", []))
        status["gold_regions"] = total_regions

    return json.dumps(status, indent=2)


def _tool_index(name: str) -> str:
    slug = _find_slug(name)
    index_path = _data_dir / "silver" / slug / "index.json"
    if not index_path.exists():
        return f"No index for '{slug}'"
    return index_path.read_text()


def _tool_regions(name: str, page: int | None = None) -> str:
    slug = _find_slug(name)
    gold_pages = _data_dir / "gold" / slug / "pages"
    if not gold_pages.is_dir():
        return f"No gold data for '{slug}'"

    result: dict = {"slug": slug, "pages": {}}
    for rf in sorted(gold_pages.glob("*.regions.json")):
        rdata = json.loads(rf.read_text())
        pg = rdata.get("page", 0)
        if page is not None and pg != page:
            continue
        result["pages"][pg] = rdata.get("regions", [])

    return json.dumps(result, indent=2)


def _tool_page_text(name: str, page: int) -> str:
    slug = _find_slug(name)
    pages_dir = _data_dir / "silver" / slug / "pages"

    md_path = pages_dir / f"{page}.md"
    if not md_path.exists():
        raw_path = pages_dir / f"{page}.raw.md"
        if raw_path.exists():
            md_path = raw_path
        else:
            return f"No text for page {page} of '{slug}'"

    return md_path.read_text()


async def run(data_dir: Path) -> None:
    global _data_dir
    _data_dir = data_dir.resolve()
    logger.info("Anchor Ingestion MCP server starting (data_dir=%s)", _data_dir)

    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Anchor Ingestion MCP Server")
    parser.add_argument("--data-dir", "-d", default="./data", help="Root data directory")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(run(Path(args.data_dir)))


if __name__ == "__main__":
    main()
