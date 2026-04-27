"""Agent tools for document reading — silver markdown + page images."""
import json as _json
import logging
import re
from pathlib import Path

from pydantic_ai import ToolReturn, BinaryContent
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode
from ..helpers import _snapshot, _mark_node_for_run, _ensure_relation
from ...core.config import get_settings

_MAX_PAGES = 6
_LOGGER = logging.getLogger(__name__)


# ── Silver data helpers ─────────────────────────────────────────────────────

def _slug(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", Path(filename).stem).strip("-").lower() or "doc"


def _silver_dir(filename: str) -> Path | None:
    """Resolve the silver directory for a document filename."""
    data_dir = get_settings().data_dir
    slug = _slug(filename)
    candidate = data_dir / "silver" / slug
    if candidate.exists():
        return candidate
    silver_root = data_dir / "silver"
    if silver_root.exists():
        for d in silver_root.iterdir():
            if d.is_dir() and slug in d.name:
                return d
    return None


def _read_silver_page_md(filename: str, page_no: int) -> str | None:
    """Read polished (or raw fallback) markdown for a silver page."""
    sd = _silver_dir(filename)
    if not sd:
        return None
    pages_dir = sd / "pages"
    md_path = pages_dir / f"{page_no}.md"
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")
    raw_path = pages_dir / f"{page_no}.raw.md"
    if raw_path.exists():
        return raw_path.read_text(encoding="utf-8")
    return None


def _read_silver_page_png(filename: str, page_no: int) -> bytes | None:
    """Read a pre-rendered silver page PNG."""
    sd = _silver_dir(filename)
    if not sd:
        return None
    png_path = sd / "pages" / f"{page_no}.png"
    if png_path.exists():
        return png_path.read_bytes()
    return None


def _silver_page_count(filename: str) -> int:
    """Get page count from silver index, or count page PNGs."""
    sd = _silver_dir(filename)
    if not sd:
        return 0
    index_path = sd / "index.json"
    if index_path.exists():
        try:
            idx = _json.loads(index_path.read_text())
            return idx.get("document", {}).get("page_count", 0)
        except Exception:
            pass
    pages_dir = sd / "pages"
    if pages_dir.exists():
        return len([f for f in pages_dir.iterdir() if f.suffix == ".png"])
    return 0


def _gold_page_regions(filename: str, page_no: int) -> list[dict] | None:
    """Load gold regions for a specific page."""
    data_dir = get_settings().data_dir
    slug = _slug(filename)
    regions_path = data_dir / "gold" / slug / "pages" / f"{page_no}.regions.json"
    if not regions_path.exists():
        return None
    try:
        data = _json.loads(regions_path.read_text())
        return data.get("regions", [])
    except Exception:
        return None


# ── Document reference resolution ───────────────────────────────────────────

async def _resolve_document_reference(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> tuple[str | None, str | None]:
    if filename and _silver_dir(filename):
        return document_id, filename

    if document_id:
        for node in ctx.deps.state.nodes:
            if node.node_type != "document":
                continue
            node_doc_id = node.id.removeprefix("__doc_")
            if node.id == document_id or node_doc_id == document_id:
                return node_doc_id, node.filename or filename

    try:
        from src.knowledge_base.service import get_document_service

        service = await get_document_service()

        if document_id:
            doc = await service.get_document(document_id)
            if doc:
                return doc.get("document_id"), doc.get("filename")

        if filename:
            docs = await service.list_documents()
            match = next((d for d in docs if d.get("filename") == filename), None)
            if match:
                return match.get("document_id"), match.get("filename")
    except Exception:
        pass

    return document_id, filename


# ── Agent tools ─────────────────────────────────────────────────────────────

async def get_document_tree(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Return the outline / table-of-contents for a document.

    Shows the document's heading hierarchy with page numbers, plus an inventory
    of tables and figures with their locations. Use this BEFORE reading pages
    to know where to look.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    """
    document_id, resolved_filename = await _resolve_document_reference(ctx, document_id, filename)
    filename = filename or resolved_filename

    if not document_id and not filename:
        return "Document not found — provide a valid document_id or filename."

    sd = _silver_dir(filename) if filename else None
    if not sd:
        return (
            f"No index found for '{filename}'. "
            "The document may not have been processed yet. "
            "Use read_document_page to access pages directly."
        )

    index_path = sd / "index.json"
    if not index_path.exists():
        return f"No index found for '{filename}'. Use read_document_page instead."

    index = _json.loads(index_path.read_text())
    doc_info = index.get("document", {})
    outline = index.get("outline", [])
    tables = index.get("tables", [])
    figures = index.get("figures", [])

    lines = [f"Document: {doc_info.get('filename', filename)} ({doc_info.get('page_count', '?')} pages)\n"]

    if outline:
        lines.append("Outline:")
        for entry in outline:
            indent = "  " * entry.get("level", 1)
            lines.append(f"{indent}{entry.get('title', '?')}  p.{entry.get('page', '?')}")

    if tables:
        lines.append(f"\nTables ({len(tables)}):")
        for t in tables:
            shape = t.get("shape", {})
            cols = t.get("header_row", [])
            first_col = t.get("first_column_values", [])
            lines.append(
                f"  [{t.get('id', '?')}] p.{t.get('page', '?')} — {t.get('caption', 'untitled')} "
                f"({shape.get('rows', '?')}x{shape.get('cols', '?')})"
            )
            if cols:
                lines.append(f"    headers: {cols}")
            if first_col:
                lines.append(f"    models/rows: {first_col[:8]}{'...' if len(first_col) > 8 else ''}")

    if figures:
        lines.append(f"\nFigures ({len(figures)}):")
        for f in figures:
            lines.append(f"  p.{f.get('page', '?')} — {f.get('caption', 'untitled')}")

    return "\n".join(lines)


async def read_document_page(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
    page_no: int = 1,
    include_image: bool = True,
) -> list[str | BinaryContent]:
    """Read one document page — returns polished markdown text and a page image.

    Uses pre-processed silver data (polished markdown + rendered PNGs) from the
    ingestion pipeline. Falls back to PyMuPDF if silver data isn't available.

    If gold regions exist for this page, they are appended as structured data.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    page_no: 1-indexed page number.
    include_image: when true, also return the rendered page image.
    """
    document_id, resolved_filename = await _resolve_document_reference(ctx, document_id, filename)
    filename = filename or resolved_filename

    if not filename:
        return ["Document not found — provide a valid document_id or filename."]

    page_count = _silver_page_count(filename)

    # Try silver markdown first
    md = _read_silver_page_md(filename, page_no)

    if md is None and page_count > 0 and (page_no < 1 or page_no > page_count):
        return [f"Page {page_no} is out of range for '{filename}' ({page_count} pages)."]

    result: list[str | BinaryContent] = []

    if md is not None:
        header = f"[Page {page_no} of {page_count or '?'} in '{filename}']"
        result.append(f"{header}\n\n{md.strip()}")
    else:
        # Fallback: extract text with PyMuPDF
        try:
            import fitz
            from src.api.file_service import get_file_service
            file_path = get_file_service().get_file_path(filename)
            with fitz.open(file_path) as pdf:
                if page_no < 1 or page_no > len(pdf):
                    return [f"Page {page_no} is out of range for '{filename}' ({len(pdf)} pages)."]
                page = pdf[page_no - 1]
                text = page.get_text().strip()
                page_count = len(pdf)
            header = f"[Page {page_no} of {page_count} in '{filename}']"
            result.append(f"{header}\n\n{text}" if text else f"{header}\n\n[No extractable text on this page.]")
        except Exception as exc:
            return [f"Failed to open page {page_no} of '{filename}': {exc}"]

    # Append gold regions if available
    regions = _gold_page_regions(filename, page_no)
    if regions:
        region_lines = [f"\n[Gold regions for page {page_no}: {len(regions)} regions]"]
        for r in regions:
            region_lines.append(
                f"  [{r.get('kind', '?')}] {r.get('title', 'untitled')}"
                + (f" — {r.get('description', '')}" if r.get('description') else "")
            )
            if r.get("markdown"):
                region_lines.append(f"    {r['markdown'][:200]}")
            if r.get("entities"):
                region_lines.append(f"    entities: {r['entities']}")
        result.append("\n".join(region_lines))

    # Page image
    if include_image:
        png_bytes = _read_silver_page_png(filename, page_no)
        if png_bytes:
            result.append(f"[Page {page_no} image]")
            result.append(BinaryContent(data=png_bytes, media_type="image/png"))
        else:
            # Fallback: render with PyMuPDF
            try:
                from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes
                from src.api.file_service import get_file_service
                file_path = get_file_service().get_file_path(filename)
                image_bytes = render_pdf_page_to_image_bytes(pdf_path=file_path, page_no=page_no)
                result.append(f"[Page {page_no} image]")
                result.append(BinaryContent(data=image_bytes, media_type="image/png"))
            except Exception as exc:
                result.append(f"[Could not render page {page_no}: {exc}]")

    return result


async def get_document_full_text(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
    include_pages: list[int] | None = None,
) -> list[str | BinaryContent]:
    """Retrieve the complete text of a document from silver page markdown.

    Use when you need the full document content — e.g. for summarising, answering
    questions spanning many pages, or when the index/gold data isn't sufficient.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    include_pages: optional list of 1-indexed page numbers to also return as images.
                   Capped at 6 pages.
    """
    document_id, resolved_filename = await _resolve_document_reference(ctx, document_id, filename)
    filename = filename or resolved_filename

    if not document_id and not filename:
        return ["Document not found — provide a valid document_id or filename."]

    if not filename:
        _, filename = await _resolve_document_reference(ctx, document_id=document_id)

    sd = _silver_dir(filename) if filename else None
    if not sd:
        return [f"No silver data found for '{filename}'. The document may not have been processed yet."]

    pages_dir = sd / "pages"
    if not pages_dir.exists():
        return [f"No page content found for '{filename}'."]

    # Read all page markdown (prefer polished, fall back to raw)
    md_files: list[tuple[int, str]] = []
    for f in sorted(pages_dir.iterdir()):
        if f.suffix == ".md" and not f.stem.endswith(".raw"):
            try:
                page_no = int(f.stem)
                md_files.append((page_no, f.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue

    if not md_files:
        for f in sorted(pages_dir.iterdir()):
            if f.name.endswith(".raw.md"):
                try:
                    page_no = int(f.stem.replace(".raw", ""))
                    md_files.append((page_no, f.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    continue

    if not md_files:
        return [f"No page content found for '{filename}'."]

    md_files.sort(key=lambda x: x[0])
    parts = [f"[Page {pg}]\n{content.strip()}" for pg, content in md_files if content.strip()]
    text_block = "\n\n".join(parts) or "Document appears to have no extractable text."
    result: list[str | BinaryContent] = [text_block]

    if include_pages and filename:
        for page_no in (include_pages or [])[:_MAX_PAGES]:
            png_bytes = _read_silver_page_png(filename, page_no)
            if png_bytes:
                result.append(f"[Page {page_no} image:]")
                result.append(BinaryContent(data=png_bytes, media_type="image/png"))
            else:
                result.append(f"[No image available for page {page_no}]")

    return result


async def get_document_page_count(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Return the page count for a document.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    """
    document_id, resolved_filename = await _resolve_document_reference(ctx, document_id, filename)
    filename = filename or resolved_filename

    if not filename:
        return "Document not found — provide a valid document_id or filename."

    count = _silver_page_count(filename)
    if count:
        return f"'{filename}' has {count} pages."

    # Fallback: PyMuPDF
    try:
        import fitz
        from src.api.file_service import get_file_service
        with fitz.open(get_file_service().get_file_path(filename)) as pdf:
            count = len(pdf)
    except Exception as exc:
        return f"Failed to open '{filename}': {exc}"

    return f"'{filename}' has {count} pages."


async def add_page_image_to_canvas(
    ctx: RunContext[AgentDeps],
    filename: str,
    page_no: int,
    title: str = "",
    bbox: list[float] | None = None,
    highlights: list[str] | None = None,
    parent_node_id: str = "",
) -> ToolReturn:
    """Add a PDF page (or cropped region) as an image node on the canvas.

    Use when a visual is worth keeping on the canvas for the engineer:
    performance charts, flow diagrams, dimension drawings, data tables as graphics.

    filename: PDF filename.
    page_no: 1-indexed page number.
    title: descriptive label for the canvas node.
    bbox: optional crop [l, t, r, b] in PDF coordinates (BOTTOMLEFT origin).
    highlights: text phrases to highlight on the image.
    parent_node_id: topic or concept node to connect this image to.
    """
    node = CanvasNode(
        node_type="image",
        title=title or f"{filename} — p.{page_no}",
        image_filename=filename,
        image_page=page_no,
        image_bbox=bbox or [],
        image_highlights=highlights or [],
        status="found",
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)

    if parent_node_id:
        _ensure_relation(ctx, parent_node_id, node.id, label="image")

    result = _snapshot(ctx)
    result.return_value = {
        "node_id": node.id,
        "image_filename": filename,
        "image_page": page_no,
        "bbox": bbox or [],
    }
    return result
