"""Agent tools for full-document retrieval, chapter navigation, and PDF visual analysis."""
from pydantic_ai import ToolReturn, BinaryContent
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode
from ..helpers import _snapshot, _mark_node_for_run, _ensure_relation

_MAX_PAGES = 6  # cap on pages returned as images in a single call


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
    import json
    from src.knowledge_base.service import get_document_service
    from src.kb_engine.rag_engine import get_rag_engine

    service = await get_document_service()

    if not document_id and filename:
        docs = await service.list_documents()
        match = next((d for d in docs if d.get("filename") == filename), None)
        if match:
            document_id = match.get("document_id")

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
    from src.knowledge_base.service import get_document_service
    from src.kb_engine.rag_engine import get_rag_engine
    from src.api.file_service import get_file_service
    from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes
    from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter

    service = await get_document_service()

    if not document_id and filename:
        docs = await service.list_documents()
        match = next((d for d in docs if d.get("filename") == filename), None)
        if match:
            document_id = match.get("document_id")
            filename = filename or match.get("filename")

    if not document_id:
        return ["Document not found — provide a valid document_id or filename."]

    # Resolve filename for rendering if not provided
    if not filename:
        docs = await service.list_documents()
        doc = next((d for d in docs if d.get("document_id") == document_id), None)
        if doc:
            filename = doc.get("filename")

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
