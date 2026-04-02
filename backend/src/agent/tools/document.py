"""Agent tools for full-document retrieval, chapter navigation, and PDF visual analysis."""
import logging
from copy import deepcopy
from functools import lru_cache

from pydantic_ai import ToolReturn, BinaryContent
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode
from ..helpers import _snapshot, _mark_node_for_run, _ensure_relation

_MAX_PAGES = 6  # cap on pages returned as images in a single call
_LOGGER = logging.getLogger(__name__)


def _bbox_dict_to_list(bbox: dict | None) -> list[float]:
    if not isinstance(bbox, dict):
        return []
    left = bbox.get("l")
    top = bbox.get("t")
    right = bbox.get("r")
    bottom = bbox.get("b")
    if all(isinstance(value, (int, float)) for value in (left, top, right, bottom)):
        values = [float(left), float(top), float(right), float(bottom)]
        if any(value != 0.0 for value in values):
            return values
    return []


def _extract_docling_page_items(docling_data: dict, page_no: int) -> list[dict]:
    """Extract all content items for a specific page from the full docling JSON.

    Returns a list of items, each with: type, text, headings (if any), and bbox.
    Tables are returned with their structured cell data.
    """
    from typing import Any

    items: list[dict[str, Any]] = []

    # Docling JSON structure varies; handle the common formats
    # Format 1: {"body" or "main_text": [{...items...}]}
    body = docling_data.get("body") or docling_data.get("main_text") or []
    if isinstance(body, list):
        for item in body:
            if not isinstance(item, dict):
                continue
            # Check if this item is on the target page
            prov_list = item.get("prov", [])
            if not isinstance(prov_list, list):
                continue
            for prov in prov_list:
                if not isinstance(prov, dict):
                    continue
                item_page = prov.get("page_no") or prov.get("page")
                if item_page != page_no:
                    continue
                entry: dict[str, Any] = {
                    "type": item.get("type", item.get("label", "text")),
                    "text": item.get("text", ""),
                }
                # Extract bbox
                bbox = prov.get("bbox")
                bbox_values = _bbox_dict_to_list(bbox)
                if bbox_values:
                    entry["bbox"] = {
                        "l": bbox_values[0],
                        "t": bbox_values[1],
                        "r": bbox_values[2],
                        "b": bbox_values[3],
                        "coord_origin": bbox.get("coord_origin", "BOTTOMLEFT"),
                    }
                # Extract table data if present
                if item.get("type") == "table" or item.get("label") == "table":
                    table_data = item.get("data") or item.get("table_cells") or item.get("cells")
                    if table_data:
                        entry["table_data"] = table_data
                items.append(entry)
                break  # one match per item is enough

    # Format 2: {"tables": [...], "texts": [...]} (some docling versions)
    for key in ("tables", "texts", "figures"):
        section = docling_data.get(key, [])
        if not isinstance(section, list):
            continue
        for item in section:
            if not isinstance(item, dict):
                continue
            prov_list = item.get("prov", [])
            if not isinstance(prov_list, list):
                prov_list = []
            for prov in prov_list:
                if not isinstance(prov, dict):
                    continue
                item_page = prov.get("page_no") or prov.get("page")
                if item_page != page_no:
                    continue
                entry = {
                    "type": key.rstrip("s"),  # "tables" -> "table"
                    "text": item.get("text", ""),
                }
                bbox = prov.get("bbox")
                bbox_values = _bbox_dict_to_list(bbox)
                if bbox_values:
                    entry["bbox"] = {
                        "l": bbox_values[0],
                        "t": bbox_values[1],
                        "r": bbox_values[2],
                        "b": bbox_values[3],
                        "coord_origin": bbox.get("coord_origin", "BOTTOMLEFT"),
                    }
                if item.get("data") or item.get("cells"):
                    entry["table_data"] = item.get("data") or item.get("cells")
                items.append(entry)
                break

    return items


def _extract_docling_page_payload(docling_data: dict, page_no: int) -> dict:
    """Return the raw docling JSON entries that belong to one page."""
    payload: dict[str, object] = {"page_no": page_no}

    for key in ("body", "main_text", "tables", "texts", "figures"):
        section = docling_data.get(key)
        if not isinstance(section, list):
            continue

        page_entries: list[dict] = []
        for item in section:
            if not isinstance(item, dict):
                continue
            prov_list = item.get("prov", [])
            if not isinstance(prov_list, list):
                continue
            if any(
                isinstance(prov, dict) and (prov.get("page_no") or prov.get("page")) == page_no
                for prov in prov_list
            ):
                page_entries.append(item)

        if page_entries:
            payload[key] = page_entries

    return payload


def _rawdict_span_text(span: dict) -> str:
    chars = span.get("chars")
    if isinstance(chars, list) and chars:
        pieces: list[str] = []
        for char in chars:
            if isinstance(char, dict):
                value = char.get("c")
                if isinstance(value, str):
                    pieces.append(value)
        text = "".join(pieces).strip()
        if text:
            return text
    text = span.get("text")
    return text.strip() if isinstance(text, str) else ""


def _rawdict_bbox_to_payload(bbox: list | tuple | None, page_height: float) -> dict | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    x0, y0, x1, y1 = bbox
    if not all(isinstance(value, (int, float)) for value in (x0, y0, x1, y1)):
        return None
    return {
        "l": float(x0),
        "t": float(page_height - float(y1)),
        "r": float(x1),
        "b": float(page_height - float(y0)),
        "coord_origin": "BOTTOMLEFT",
    }


def _extract_pymupdf_page_items(file_path: str, page_no: int) -> list[dict]:
    import fitz  # PyMuPDF

    items: list[dict] = []
    try:
        with fitz.open(file_path) as pdf:
            if page_no < 1 or page_no > len(pdf):
                return []
            page = pdf[page_no - 1]
            rawdict = page.get_textpage().extractRAWDICT(sort=True)
            page_height = float(rawdict.get("height") or page.rect.height)
    except Exception:
        _LOGGER.exception("Failed to extract PyMuPDF rawdict for %s p.%s", file_path, page_no)
        return []

    blocks = rawdict.get("blocks", [])
    if not isinstance(blocks, list):
        return []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", 0)
        if block_type != 0:
            continue
        lines = block.get("lines", [])
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, dict):
                continue
            spans = line.get("spans", [])
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                text = _rawdict_span_text(span)
                bbox = _rawdict_bbox_to_payload(span.get("bbox"), page_height)
                if text and bbox:
                    items.append({"type": "span", "text": text, "bbox": bbox})

            line_bbox = _rawdict_bbox_to_payload(line.get("bbox"), page_height)
            line_text = " ".join(_rawdict_span_text(span) for span in spans if isinstance(span, dict)).strip()
            if line_text and line_bbox:
                items.append({"type": "line", "text": line_text, "bbox": line_bbox})

    _LOGGER.info(
        "PyMuPDF rawdict page items for %s p.%s: %s items",
        file_path,
        page_no,
        len(items),
    )
    return items


def _extract_pymupdf_page_payload(file_path: str, page_no: int) -> dict:
    import fitz  # PyMuPDF

    try:
        with fitz.open(file_path) as pdf:
            if page_no < 1 or page_no > len(pdf):
                return {}
            page = pdf[page_no - 1]
            rawdict = page.get_textpage().extractRAWDICT(sort=True)
    except Exception:
        _LOGGER.exception("Failed to extract PyMuPDF rawdict payload for %s p.%s", file_path, page_no)
        return {}

    if not isinstance(rawdict, dict):
        return {}
    rawdict["page_no"] = page_no
    return {"page_no": page_no, "pymupdf_rawdict": rawdict}


@lru_cache(maxsize=128)
def _cached_structured_page_data(file_path: str, page_no: int) -> tuple[list[dict], dict]:
    import json as _json
    from pathlib import Path as _Path
    from src.kb_engine.docling_cache import get_docling_json_for_filename

    docling_json_path = _Path(f"{file_path}.docling.json")

    if docling_json_path.exists():
        try:
            docling_data = _json.loads(docling_json_path.read_text(encoding="utf-8"))
        except Exception:
            _LOGGER.exception("Failed to parse docling JSON for %s", file_path)
            return [], {}
        items = _extract_docling_page_items(docling_data, page_no)
        payload = _extract_docling_page_payload(docling_data, page_no)
        return items, payload

    cached_docling = get_docling_json_for_filename(_Path(file_path).name)
    if cached_docling is not None:
        items = _extract_docling_page_items(cached_docling, page_no)
        payload = _extract_docling_page_payload(cached_docling, page_no)
        return items, payload

    items = _extract_pymupdf_page_items(file_path, page_no)
    payload = _extract_pymupdf_page_payload(file_path, page_no)
    return items, payload


def get_docling_page_items_for_file_path(file_path: str, page_no: int) -> list[dict]:
    from pathlib import Path as _Path
    items, _payload = _cached_structured_page_data(file_path, page_no)
    bbox_items = sum(1 for item in items if _bbox_dict_to_list(item.get("bbox")))
    _LOGGER.info(
        "Structured page items for %s p.%s: %s items, %s with bbox",
        _Path(file_path).name,
        page_no,
        len(items),
        bbox_items,
    )
    return deepcopy(items)


def get_docling_page_payload_for_file_path(file_path: str, page_no: int) -> dict:
    from pathlib import Path as _Path
    _items, payload = _cached_structured_page_data(file_path, page_no)
    entry_count = sum(
        len(value)
        for key, value in payload.items()
        if key != "page_no" and isinstance(value, list)
    )
    _LOGGER.info(
        "Structured page payload for %s p.%s: %s entries",
        _Path(file_path).name,
        page_no,
        entry_count,
    )
    return deepcopy(payload)


def get_docling_page_payload_for_filename(filename: str, page_no: int) -> dict:
    from src.api.file_service import get_file_service

    file_path = get_file_service().get_file_path(filename)
    return get_docling_page_payload_for_file_path(file_path, page_no)


def get_docling_page_items_for_filename(filename: str, page_no: int) -> list[dict]:
    from src.api.file_service import get_file_service

    file_path = get_file_service().get_file_path(filename)
    return get_docling_page_items_for_file_path(file_path, page_no)


async def _resolve_document_reference(
    document_id: str | None = None,
    filename: str | None = None,
) -> tuple[str | None, str | None]:
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

    return None, None


async def get_document_tree(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Return the chapter/section tree for a document.

    The tree shows the document's heading hierarchy with page numbers, whether
    each chapter contains tables or figures, and LLM-generated metadata
    (summary, questions answered, key concepts) when available.

    Use this BEFORE get_document_full_text to navigate large documents:
    the tree tells you exactly which pages to load — avoiding loading the whole document.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.

    Returns a JSON object with:
      chapters[]: [{heading, pages, has_table, has_figure, metadata: {summary, questions, key_concepts}}]
      page_descriptions: {page_no: vision description} when vision enrichment has been run
    """
    from src.kb_engine.rag_engine import get_rag_engine

    document_id, resolved_filename = await _resolve_document_reference(document_id, filename)
    filename = filename or resolved_filename

    if not document_id:
        return "Document not found — provide a valid document_id or filename."

    tree = get_rag_engine().get_document_tree(document_id)
    if tree is None:
        return (
            f"No chapter tree found for document_id={document_id}. "
            "The document may have been ingested before tree extraction was available. "
            "Use get_document_full_text to access the content directly."
        )

    # Return a compact but readable representation
    summary_lines = [f"Document: {tree.get('filename')} ({len(tree['chapters'])} chapters)\n"]
    for ch in tree["chapters"]:
        pages_str = f"pp.{ch['pages']}" if ch["pages"] else "p.?"
        flags = []
        if ch.get("has_table"):
            flags.append("table")
        if ch.get("has_figure"):
            flags.append("figure")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        summary_lines.append(f"  {ch['heading']}  {pages_str}{flag_str}")
        if ch.get("metadata") and ch["metadata"].get("summary"):
            summary_lines.append(f"    → {ch['metadata']['summary'][:120]}...")

    if tree.get("page_descriptions"):
        summary_lines.append(f"\nPage descriptions available for pages: {sorted(tree['page_descriptions'].keys())}")

    return "\n".join(summary_lines)


async def get_document_page_count(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Return the page count for a document.

    Use this before sequential page reading when you need to walk a document
    page by page (for example: front matter, table of contents, index, appendices).

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    """
    import fitz  # PyMuPDF
    from src.api.file_service import get_file_service

    document_id, resolved_filename = await _resolve_document_reference(document_id, filename)
    filename = filename or resolved_filename

    if not filename:
        return "Document not found — provide a valid document_id or filename."

    try:
        with fitz.open(get_file_service().get_file_path(filename)) as pdf:
            page_count = len(pdf)
    except Exception as exc:
        return f"Failed to open '{filename}': {exc}"

    if document_id:
        return f"'{filename}' ({document_id}) has {page_count} pages."
    return f"'{filename}' has {page_count} pages."


async def read_document_page(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
    page_no: int = 1,
    include_image: bool = True,
) -> list[str | BinaryContent]:
    """Read one document page — returns text, structured chunks with bboxes, and a page image.

    Each structured chunk from the docling parser includes:
    - text: the chunk content
    - label: type (text, table, section_header, etc.)
    - headings: section path (e.g. ["OPERATING DATA", "Max inlet pressure"])
    - page: page number
    - bbox: {l, t, r, b, coord_origin} — exact position on the PDF page

    Use the bbox data when creating parameter table rows — pass it through to the
    source field so the engineer can click through to the exact location in the PDF.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    page_no: 1-indexed page number.
    include_image: when true, also return a rendered image of the full page.
    """
    import fitz  # PyMuPDF
    from src.api.file_service import get_file_service
    from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes

    document_id, resolved_filename = await _resolve_document_reference(document_id, filename)
    filename = filename or resolved_filename

    if not filename:
        return ["Document not found — provide a valid document_id or filename."]

    file_path = get_file_service().get_file_path(filename)

    try:
        with fitz.open(file_path) as pdf:
            page_count = len(pdf)
            if page_no < 1 or page_no > page_count:
                return [f"Page {page_no} is out of range for '{filename}' ({page_count} pages)."]
            page = pdf[page_no - 1]
            text = page.get_text().strip()
    except Exception as exc:
        return [f"Failed to open page {page_no} of '{filename}': {exc}"]

    result: list[str | BinaryContent] = []
    header = f"[Page {page_no} of {page_count} in '{filename}']"
    result.append(f"{header}\n\n{text}" if text else f"{header}\n\n[No extractable text on this page.]")

    # Load structured page data for internal bbox matching / logging only.
    try:
        page_items = get_docling_page_items_for_file_path(file_path, page_no)
        if page_items:
            bbox_items = sum(1 for item in page_items if _bbox_dict_to_list(item.get("bbox")))
            _LOGGER.info(
                "Structured page items ready for %s p.%s: %s items, %s with bboxes",
                filename,
                page_no,
                len(page_items),
                bbox_items,
            )
        else:
            _LOGGER.info("No structured page items found for %s p.%s", filename, page_no)

        page_payload = get_docling_page_payload_for_file_path(file_path, page_no)
        if page_payload and len(page_payload) > 1:
            payload_sections = {
                key: len(value)
                for key, value in page_payload.items()
                if key != "page_no" and isinstance(value, list)
            }
            _LOGGER.info(
                "Structured raw page payload sections for %s p.%s: %s",
                filename,
                page_no,
                payload_sections,
            )
        else:
            _LOGGER.warning("No structured raw page payload found for %s p.%s", filename, page_no)
    except Exception as exc:
        _LOGGER.warning("Could not load structured page data for %s p.%s: %s", filename, page_no, exc)

    if include_image:
        try:
            image_bytes = render_pdf_page_to_image_bytes(
                pdf_path=file_path,
                page_no=page_no,
            )
            result.append(f"[Rendered page image for page {page_no}]")
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
    """Retrieve the complete text of a document by concatenating all chunks in page order.

    Use when chunk-based answers are incomplete — e.g. for summarising a full document,
    answering questions spanning many pages, or when vector search misses relevant sections
    such as table rows or cross-referenced data.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    include_pages: optional list of 1-indexed page numbers to also return as rendered images.
                   Use this for pages that contain tables, charts, or diagrams that are better
                   read visually (e.g. dimensions tables, flow charts). Capped at 6 pages.
    """
    from src.kb_engine.rag_engine import get_rag_engine
    from src.api.file_service import get_file_service
    from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes
    from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter

    document_id, resolved_filename = await _resolve_document_reference(document_id, filename)
    filename = filename or resolved_filename

    if not document_id:
        return ["Document not found — provide a valid document_id or filename."]

    # Resolve filename for rendering if not provided
    if not filename:
        _, filename = await _resolve_document_reference(document_id=document_id)

    rag_engine = get_rag_engine()
    vs = rag_engine.vector_store

    try:
        filters = MetadataFilters(filters=[
            MetadataFilter(key="document_id", value=document_id)
        ])
        nodes = await vs.aget_nodes(filters=filters)
    except Exception as exc:
        return [f"Failed to retrieve document chunks: {exc}"]

    if not nodes:
        return [f"No text chunks found for document_id={document_id}."]

    def _page(n) -> int:
        m = n.metadata or {}
        return m.get("page_no") or m.get("page_number") or m.get("page") or 0

    sorted_nodes = sorted(nodes, key=_page)

    parts: list[str] = []
    seen: set[str] = set()
    for node in sorted_nodes:
        content = node.get_content().strip()
        if not content or content in seen:
            continue
        seen.add(content)
        page = _page(node)
        parts.append(f"[Page {page}]\n{content}" if page else content)

    text_block = "\n\n".join(parts) or "Document appears to have no extractable text."
    result: list[str | BinaryContent] = [text_block]

    if include_pages and filename:
        file_path = get_file_service().get_file_path(filename)
        pages_to_render = include_pages[:_MAX_PAGES]
        for page_no in pages_to_render:
            try:
                image_bytes = render_pdf_page_to_image_bytes(pdf_path=file_path, page_no=page_no)
                result.append(f"[Page {page_no} image:]")
                result.append(BinaryContent(data=image_bytes, media_type="image/png"))
            except Exception as exc:
                result.append(f"[Could not render page {page_no}: {exc}]")

    return result


async def analyze_pdf_page(
    ctx: RunContext[AgentDeps],
    filename: str,
    page_no: int,
    question: str = "",
    bbox: list[float] | None = None,
    highlights: list[str] | None = None,
) -> list[str | BinaryContent]:
    """Return a rendered PDF page (or cropped region) as an image for visual analysis.

    Use this to read charts, diagrams, flow charts, images, and tables that are
    poorly captured by text extraction. The image is rendered server-side and returned
    directly — the model can read it without a separate vision call.

    filename: PDF filename (must be in the knowledge base).
    page_no: 1-indexed page number.
    question: optional hint describing what you are looking for on this page.
    bbox: optional crop [left, top, right, bottom] in PDF coordinates (BOTTOMLEFT origin).
    highlights: optional list of text phrases to highlight on the rendered page
                (e.g. ["LKH-5", "600 kPa"]). Useful to draw attention to specific values.
    """
    from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes
    from src.api.file_service import get_file_service

    path = get_file_service().get_file_path(filename)
    crop_bbox = None
    if bbox and len(bbox) == 4:
        crop_bbox = {"l": bbox[0], "t": bbox[1], "r": bbox[2], "b": bbox[3], "coord_origin": "BOTTOMLEFT"}

    try:
        image_bytes = render_pdf_page_to_image_bytes(
            pdf_path=path,
            page_no=page_no,
            crop_bbox=crop_bbox,
            phrases=highlights or [],
        )
    except Exception as exc:
        return [f"Failed to render page {page_no} of '{filename}': {exc}"]

    label = f"[Page {page_no} of '{filename}'"
    if question:
        label += f" — {question}"
    label += "]"

    return [label, BinaryContent(data=image_bytes, media_type="image/png")]


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
    Always connect to a parent topic node so it sits in the knowledge graph.

    filename: PDF filename.
    page_no: 1-indexed page number.
    title: descriptive label for the canvas node (e.g. "LKH-5 Flow Curve", "Dimensions Table").
    bbox: optional crop [l, t, r, b] — same coordinates as analyze_pdf_page.
    highlights: text phrases to highlight on the image (e.g. ["LKH-5", "L = LKH-5"]).
                Use to draw the engineer's eye to the relevant part of the page.
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
