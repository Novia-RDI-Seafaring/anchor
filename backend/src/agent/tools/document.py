"""Agent tools for full-document retrieval and PDF visual analysis."""
import os
import base64
from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode
from ..helpers import _snapshot, _mark_node_for_run, _ensure_relation


async def get_document_full_text(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
    filename: str | None = None,
) -> str:
    """Retrieve the complete text of a document by concatenating all chunks in page order.

    Use when chunk-based answers are incomplete — e.g. for summarising a full document,
    answering questions spanning many pages, or when vector search misses relevant sections.

    document_id: the KB document ID (preferred).
    filename: alternatively, resolve by filename.
    """
    from src.knowledge_base.service import get_document_service
    from src.kb_engine.rag_engine import get_rag_engine
    from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter

    service = await get_document_service()

    if not document_id and filename:
        docs = await service.list_documents()
        match = next((d for d in docs if d.get("filename") == filename), None)
        if match:
            document_id = match.get("document_id")

    if not document_id:
        return "Document not found — provide a valid document_id or filename."

    rag_engine = get_rag_engine()
    vs = rag_engine.vector_store

    try:
        filters = MetadataFilters(filters=[
            MetadataFilter(key="document_id", value=document_id)
        ])
        nodes = await vs.aget_nodes(filters=filters)
    except Exception as exc:
        return f"Failed to retrieve document chunks: {exc}"

    if not nodes:
        return f"No text chunks found for document_id={document_id}."

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

    return "\n\n".join(parts) or "Document appears to have no extractable text."


def _build_vision_client():
    """Return (client, model) for the configured vision provider."""
    provider = os.getenv("DEFAULT_PROVIDER", "").lower()
    if provider == "azure" or os.getenv("AZURE_OPENAI_API_KEY"):
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.getenv("OPENAI_API_VERSION", "2024-12-01-preview"),
        )
        model = os.getenv("VISION_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    else:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("VISION_MODEL", "gpt-4o-mini")
    return client, model


async def analyze_pdf_page(
    ctx: RunContext[AgentDeps],
    filename: str,
    page_no: int,
    question: str = "",
    bbox: list[float] | None = None,
) -> str:
    """Visually analyse a specific page or region of a PDF using a vision model.

    Use this to read charts, diagrams, flow charts, images, and tables that are
    poorly captured by text extraction. The image is rendered server-side and sent
    to the vision model — no external URL needed.

    filename: PDF filename (must be in the knowledge base).
    page_no: 1-indexed page number.
    question: specific question, e.g. "What flow rates does the LKH-70 achieve?".
              Leave empty for a full description of the page content.
    bbox: optional crop [left, top, right, bottom] in PDF coordinates (BOTTOMLEFT origin).
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
        )
    except Exception as exc:
        return f"Failed to render page {page_no} of '{filename}': {exc}"

    question_text = question.strip() or (
        f"Describe all content on page {page_no} of '{filename}'. "
        "Include data values, chart legends, axis labels, table contents, and any notable findings."
    )

    image_b64 = base64.b64encode(image_bytes).decode()
    client, model = _build_vision_client()

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "high"},
                    },
                    {"type": "text", "text": question_text},
                ],
            }],
        )
        return response.choices[0].message.content or "No analysis returned."
    except Exception as exc:
        return f"Vision analysis failed: {exc}"


async def add_page_image_to_canvas(
    ctx: RunContext[AgentDeps],
    filename: str,
    page_no: int,
    title: str = "",
    bbox: list[float] | None = None,
    parent_node_id: str = "",
) -> ToolReturn:
    """Add a PDF page (or cropped region) as an image node on the canvas.

    Use after analyze_pdf_page when the image itself is worth preserving — e.g. a
    pump flow chart, a process diagram, a data table as a graphic.

    filename: PDF filename.
    page_no: 1-indexed page number.
    title: label for the canvas node.
    bbox: optional crop [l, t, r, b] — same coordinates as analyze_pdf_page.
    parent_node_id: optional node to connect this image to with an edge.
    """
    node = CanvasNode(
        node_type="image",
        title=title or f"{filename} — p.{page_no}",
        image_filename=filename,
        image_page=page_no,
        image_bbox=bbox or [],
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
