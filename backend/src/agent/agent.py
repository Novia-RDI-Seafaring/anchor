from dotenv import load_dotenv
import os
import re

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, ModelRetry, ToolReturn
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from .deps import AgentDeps
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .state import Canvas, CanvasNode, Relation, SourceHighlight, SpecProperty, NodeStatus

load_dotenv(override=True)


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


STRICT_CANVAS_VALIDATION = _env_flag("STRICT_CANVAS_VALIDATION", "0")
_EARLY_SOCIAL_OR_META_RE = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|great|cool|what can you do|who are you)\b",
    re.IGNORECASE,
)
_EARLY_DOCUMENT_LISTING_RE = re.compile(
    r"\b(what|which|list|show)\b.*\bdocuments?\b|\bloaded\b.*\bdocuments?\b",
    re.IGNORECASE,
)
_EARLY_CANVAS_EDIT_RE = re.compile(
    r"\b(canvas|node|nodes|relation|graph|connect|delete|remove|add to canvas)\b",
    re.IGNORECASE,
)


def _early_prompt_to_text(prompt: str | list | tuple | None) -> str:
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, (list, tuple)):
        parts: list[str] = []
        for item in prompt:
            if isinstance(item, str):
                parts.append(item)
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(part for part in parts if part).strip()
    return ""


async def _prepare_tools_for_turn(ctx: RunContext[AgentDeps], tool_defs):
    prompt_text = _early_prompt_to_text(getattr(ctx, "prompt", None)).strip().lower()
    if not prompt_text:
        return tool_defs
    if _EARLY_SOCIAL_OR_META_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in {"list_documents"}]
    if _EARLY_DOCUMENT_LISTING_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in {"list_documents"}]
    if _EARLY_CANVAS_EDIT_RE.search(prompt_text):
        return tool_defs
    allowed = {"resolve_technical_query", "get_active_document_context", "check_canvas", "list_documents"}
    return [tool_def for tool_def in tool_defs if tool_def.name in allowed]


agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
    output_retries=2 if STRICT_CANVAS_VALIDATION else 0,
    prepare_tools=_prepare_tools_for_turn,
)


image_analysis_agent = Agent(
    name="Image Analysis Agent",
    model=os.getenv("IMAGE_ANALYSIS_MODEL", "gpt-4o-mini"),
    system_prompt=(
        "Analyze the provided image URL and answer with factual, concise output. "
        "Do not hallucinate values; if uncertain, say so."
    ),
    output_retries=2,
)

def _snapshot(ctx: RunContext[AgentDeps]) -> ToolReturn:
    if ctx.run_id:
        ctx.deps.state.last_updated_run_id = ctx.run_id
    return ToolReturn(
        return_value={"success": True},
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)],
    )


def _mark_node_for_run(node: CanvasNode, ctx: RunContext[AgentDeps]) -> None:
    if ctx.run_id:
        node.last_updated_run_id = ctx.run_id


def _build_source_node(
    *,
    ctx: RunContext[AgentDeps],
    filename: str,
    page: int,
    bbox: list[float],
    highlights: list[SourceHighlight] | None = None,
) -> CanvasNode:
    resolved = highlights or [SourceHighlight(page=page, bbox=bbox)]
    node = CanvasNode(
        node_type="source",
        status="found",
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=resolved,
    )
    _mark_node_for_run(node, ctx)
    return node


def _get_or_create_source_node(
    *,
    ctx: RunContext[AgentDeps],
    filename: str,
    page: int,
    bbox: list[float],
    highlights: list[SourceHighlight] | None = None,
) -> CanvasNode:
    resolved = highlights or [SourceHighlight(page=page, bbox=bbox)]
    for node in ctx.deps.state.nodes:
        if node.node_type != "source":
            continue
        if node.filename == filename and node.page == page and node.bbox == bbox:
            _mark_node_for_run(node, ctx)
            if resolved and not node.highlights:
                node.highlights = resolved
            return node
    return _build_source_node(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=resolved,
    )


def _ensure_relation(ctx: RunContext[AgentDeps], from_id: str, to_id: str, label: str = "") -> None:
    existing = next(
        (rel for rel in ctx.deps.state.relations if rel.from_id == from_id and rel.to_id == to_id and rel.label == label),
        None,
    )
    if existing is None:
        ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))


def _remember_search_results(ctx: RunContext[AgentDeps], chunks: list[dict]) -> None:
    ctx.deps.last_search_results = [dict(chunk) for chunk in chunks]
    ctx.deps.last_search_run_id = ctx.run_id or ""


def _get_cached_chunk(ctx: RunContext[AgentDeps], chunk_index: int = 0) -> dict | None:
    chunks = ctx.deps.last_search_results or []
    if not chunks:
        return None
    if chunk_index < 0 or chunk_index >= len(chunks):
        return None
    return chunks[chunk_index]


def _coerce_highlights(highlights: list[SourceHighlight] | list[dict] | None) -> list[SourceHighlight]:
    if not highlights:
        return []
    output: list[SourceHighlight] = []
    for item in highlights:
        if isinstance(item, SourceHighlight):
            output.append(item)
            continue
        if not isinstance(item, dict):
            continue
        page = item.get("page")
        bbox = item.get("bbox")
        if isinstance(page, int) and isinstance(bbox, list):
            output.append(SourceHighlight(page=page, bbox=bbox))
    return output


def _resolve_source_details(
    *,
    ctx: RunContext[AgentDeps],
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | list[dict] | None = None,
    chunk_index: int = 0,
) -> tuple[str | None, int | None, list[float], list[SourceHighlight]]:
    cached_chunk = _get_cached_chunk(ctx, chunk_index)
    resolved_filename = filename or (cached_chunk.get("filename") if cached_chunk else None)
    resolved_page = page if page is not None else (_select_page(cached_chunk) if cached_chunk else None)
    resolved_bbox = bbox if bbox is not None else (_select_bbox(cached_chunk) if cached_chunk else [])
    resolved_highlights = _coerce_highlights(highlights)

    if not resolved_highlights and cached_chunk:
        resolved_highlights = _coerce_highlights(_select_highlights(cached_chunk))

    if resolved_page is None and resolved_highlights:
        resolved_page = resolved_highlights[0].page
    if not resolved_bbox and resolved_highlights:
        resolved_bbox = resolved_highlights[0].bbox

    return resolved_filename, resolved_page, resolved_bbox, resolved_highlights


_SOCIAL_OR_META_RE = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|great|cool|what can you do|who are you)\b",
    re.IGNORECASE,
)
_DOCUMENT_LISTING_RE = re.compile(
    r"\b(what|which|list|show)\b.*\bdocuments?\b|\bloaded\b.*\bdocuments?\b",
    re.IGNORECASE,
)
_CANVAS_EDIT_RE = re.compile(
    r"\b(canvas|node|nodes|relation|graph|connect|delete|remove|add to canvas)\b",
    re.IGNORECASE,
)
_TABLE_OR_SPEC_RE = re.compile(
    r"\b(technical data|dimensions?|measures?|specs?|specifications?|materials?|properties|ratings?)\b",
    re.IGNORECASE,
)
_MODEL_CODE_RE = re.compile(r"\b([A-Z]{2,}(?:-\d+[A-Z]?)?)\b")


def _prompt_to_text(prompt: str | list | tuple | None) -> str:
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, (list, tuple)):
        parts: list[str] = []
        for item in prompt:
            if isinstance(item, str):
                parts.append(item)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
                continue
            content = getattr(item, "content", None)
            if isinstance(content, str):
                parts.append(content)
                continue
            parts.append(str(item))
        return " ".join(part for part in parts if part).strip()
    return ""


def _requires_canvas_update(prompt: str) -> bool:
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    if _SOCIAL_OR_META_RE.search(normalized):
        return False
    if _DOCUMENT_LISTING_RE.search(normalized):
        return False
    return True


def _clean_text_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("-•*")).strip()


def _split_candidate_lines(text: str) -> list[str]:
    base_lines = [_clean_text_value(line) for line in text.replace("\r", "\n").split("\n")]
    lines = [line for line in base_lines if line]
    if len(lines) >= 2:
        return lines
    expanded = []
    for part in re.split(r"[;•]", text):
        cleaned = _clean_text_value(part)
        if cleaned:
            expanded.append(cleaned)
    return expanded or lines


def _extract_properties_from_text(text: str, query: str) -> list[SpecProperty]:
    properties: list[SpecProperty] = []
    seen: set[tuple[str, str, str]] = set()
    model_match = _MODEL_CODE_RE.search(query)
    query_model = model_match.group(1) if model_match else ""

    for line in _split_candidate_lines(text):
        if ":" in line:
            key, value = line.split(":", 1)
            key = _clean_text_value(key)
            value = _clean_text_value(value)
            if not key or not value:
                continue
            unit = ""
            unit_match = re.match(r"^(.*?)(?:\s+)(mm|cm|m|bar|kg|kW|W|A|V|Hz|rpm|°C|C)$", value, re.IGNORECASE)
            if unit_match:
                value = _clean_text_value(unit_match.group(1))
                unit = unit_match.group(2)
            signature = (key.lower(), value.lower(), unit.lower())
            if signature in seen:
                continue
            seen.add(signature)
            properties.append(SpecProperty(key=key, value=value, unit=unit))
            continue

        if query_model and re.search(r"\b\d+(?:[.,]\d+)?\s*(mm|cm|m)\b", line, re.IGNORECASE):
            number_match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", line, re.IGNORECASE)
            if not number_match:
                continue
            signature = (query_model.lower(), number_match.group(1).lower(), number_match.group(2).lower())
            if signature in seen:
                continue
            seen.add(signature)
            properties.append(
                SpecProperty(key=query_model, value=number_match.group(1), unit=number_match.group(2))
            )

    return properties


def _summarize_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant data found."
    content = _clean_text_value(str(chunks[0].get("content") or ""))
    if not content:
        return "Relevant content was found, but the extracted text was empty."
    if len(content) > 320:
        content = content[:317].rstrip() + "..."
    return content


def _summarize_properties(properties: list[SpecProperty], filename: str | None = None) -> str:
    details = []
    for item in properties[:8]:
        value = item.value if not item.unit else f"{item.value} {item.unit}"
        details.append(f"{item.key}: {value}")
    summary = "; ".join(details)
    if filename:
        return f"{summary}. Source: {filename}."
    return f"{summary}."


def _derive_topic_title(query: str, active_filename: str | None = None) -> str:
    normalized = query.strip().rstrip("?.!")
    lowered = normalized.lower()
    if "technical data" in lowered and "material" in lowered:
        return "Material Technical Data"
    if "dimension" in lowered or "measure" in lowered:
        model_match = _MODEL_CODE_RE.search(normalized)
        if model_match:
            return f"{model_match.group(1)} Dimensions"
        return "Dimensions"
    if active_filename and any(token in lowered for token in ("material", "technical data", "spec", "dimension", "measure")):
        filename = active_filename.rsplit(".", 1)[0]
        return f"{filename} Technical Data"
    if normalized:
        return normalized[:80]
    return "Technical Query"


def _derive_spec_title(query: str) -> str:
    lowered = query.strip().lower()
    if "dimension" in lowered or "measure" in lowered:
        return "Dimensions"
    if "material" in lowered and "technical data" in lowered:
        return "Material Technical Data"
    if "technical data" in lowered:
        return "Technical Data"
    return "Specifications"


@agent.instructions
def technical_query_instruction(ctx: RunContext[AgentDeps]) -> str | None:
    prompt_text = _prompt_to_text(ctx.prompt)
    if not _requires_canvas_update(prompt_text):
        return None
    if _CANVAS_EDIT_RE.search(prompt_text):
        return None
    return (
        "This is a technical knowledge-base query. Before any text answer, call "
        f"resolve_technical_query(query={prompt_text!r}). Use its returned summary as the basis for the reply. "
        "Do not rely on low-level canvas tools unless the user explicitly asks to edit the canvas structure."
    )


@agent.output_validator
def ensure_technical_queries_update_canvas(ctx: RunContext[AgentDeps], data: str) -> str:
    if not STRICT_CANVAS_VALIDATION:
        return data

    prompt_text = _prompt_to_text(ctx.prompt)
    if not _requires_canvas_update(prompt_text):
        return data

    canvas_nodes = list(ctx.deps.state.nodes)
    has_topic = any(node.node_type == "topic" for node in canvas_nodes)
    fact_or_spec_nodes = [node for node in canvas_nodes if node.node_type in {"fact", "spec"}]
    resolved_fact_or_spec_nodes = [
        node for node in fact_or_spec_nodes if node.status in {"found", "partial", "not_found"}
    ]

    if not has_topic or not resolved_fact_or_spec_nodes:
        raise ModelRetry(
            "Technical KB answers require a topic plus at least one resolved fact or spec node on the canvas."
        )

    return data


def _select_bbox(chunk: dict) -> list[float]:
    bbox = chunk.get("bbox")
    if isinstance(bbox, list):
        return bbox

    bboxes = chunk.get("bboxes")
    if isinstance(bboxes, list):
        for item in bboxes:
            if isinstance(item, dict) and isinstance(item.get("bbox"), list):
                return item["bbox"]

    metadata = chunk.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("bbox"), list):
        return metadata["bbox"]

    return []


def _select_page(chunk: dict) -> int:
    page_no = chunk.get("page_no")
    if isinstance(page_no, int):
        return page_no

    page_numbers = chunk.get("page_numbers")
    if isinstance(page_numbers, list) and page_numbers and isinstance(page_numbers[0], int):
        return page_numbers[0]

    metadata = chunk.get("metadata")
    if isinstance(metadata, dict):
        raw_page = metadata.get("page_no") or metadata.get("page_number") or metadata.get("page")
        if isinstance(raw_page, int):
            return raw_page

    return 1


def _select_highlights(chunk: dict) -> list[dict]:
    highlights = []
    bboxes = chunk.get("bboxes")
    if isinstance(bboxes, list):
        for item in bboxes:
            if not isinstance(item, dict):
                continue
            page_no = item.get("page_no")
            bbox = item.get("bbox")
            if isinstance(page_no, int) and isinstance(bbox, list):
                highlights.append({"page": page_no, "bbox": bbox})

    if highlights:
        return highlights

    return [{"page": _select_page(chunk), "bbox": _select_bbox(chunk)}]

@agent.tool
async def check_canvas(ctx: RunContext[AgentDeps]):
    """Return the current canvas state (nodes + relations)."""
    return ctx.deps.state

@agent.tool
async def list_documents(ctx: RunContext[AgentDeps]):
    """List ingested documents available in the knowledge base."""
    from src.knowledge_base.service import get_document_service

    service = await get_document_service()
    documents = await service.list_documents()
    return {
        "documents": [
            {
                "document_id": doc.get("document_id"),
                "filename": doc.get("filename"),
                "status": doc.get("status"),
                "chunk_count": doc.get("chunk_count"),
                "source_type": doc.get("source_type"),
            }
            for doc in documents
        ]
    }

@agent.tool
async def get_active_document_context(ctx: RunContext[AgentDeps]):
    """Return the currently selected document filter, if any.

    Use this before asking a clarifying question about which document/material
    the user means. If a document is selected, assume generic technical queries
    refer to that document unless the user explicitly says otherwise.
    """
    from src.core.context import get_active_document_id
    from src.knowledge_base.service import get_document_service

    active_document_id = get_active_document_id()
    if not active_document_id:
        return {
            "document_id": None,
            "filename": None,
            "status": "all_documents",
            "chunk_count": 0,
        }

    service = await get_document_service()
    documents = await service.list_documents()
    active_document = next(
        (doc for doc in documents if doc.get("document_id") == active_document_id),
        None,
    )

    if not active_document:
        return {
            "document_id": active_document_id,
            "filename": None,
            "status": "selected_but_missing",
            "chunk_count": 0,
        }

    return {
        "document_id": active_document.get("document_id"),
        "filename": active_document.get("filename"),
        "status": active_document.get("status"),
        "chunk_count": active_document.get("chunk_count", 0),
        "source_type": active_document.get("source_type"),
    }


@agent.tool
async def resolve_technical_query(
    ctx: RunContext[AgentDeps],
    query: str,
    root_title: str | None = None,
    prefer_table: bool | None = None,
    top_k: int = 5,
) -> ToolReturn:
    """Search the KB, populate the canvas, and return a grounded summary.

    This is the primary tool for technical questions. It performs retrieval,
    creates the topic/fact-or-spec/source nodes, emits a canvas snapshot, and
    returns a concise summary for the final chat response.
    """
    from src.core.context import get_active_document_id
    from src.knowledge_base.service import get_document_service
    from src.knowledge_base.vector_store import get_vector_store

    service = await get_document_service()
    active_document_id = get_active_document_id()
    active_document = None
    if active_document_id:
        vector_store = await get_vector_store()
        active_document = await vector_store.get_document(active_document_id)

    chunks = await service.search(query=query, top_k=top_k, document_id=active_document_id)
    normalized_chunks: list[dict] = []
    for chunk in chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        normalized_chunks.append(normalized)
    _remember_search_results(ctx, normalized_chunks)

    topic = CanvasNode(
        node_type="topic",
        title=root_title or _derive_topic_title(query, active_document.get("filename") if active_document else None),
        status="found" if normalized_chunks else "not_found",
    )
    _mark_node_for_run(topic, ctx)
    ctx.deps.state.nodes.append(topic)

    if not normalized_chunks:
        fact = CanvasNode(
            node_type="fact",
            text=f"No relevant data found for: {query}",
            status="not_found",
        )
        _mark_node_for_run(fact, ctx)
        ctx.deps.state.nodes.append(fact)
        _ensure_relation(ctx, topic.id, fact.id)
        result = _snapshot(ctx)
        result.return_value = {
            "summary": f"I could not find relevant technical information for '{query}' in the loaded knowledge base.",
            "topic_id": topic.id,
            "node_id": fact.id,
            "found": False,
        }
        return result

    properties: list[SpecProperty] = []
    for chunk in normalized_chunks[:3]:
        for prop in _extract_properties_from_text(str(chunk.get("content") or ""), query):
            if not any(
                existing.key == prop.key and existing.value == prop.value and existing.unit == prop.unit
                for existing in properties
            ):
                properties.append(prop)

    use_spec = prefer_table if prefer_table is not None else bool(properties) and _TABLE_OR_SPEC_RE.search(query) is not None
    if use_spec and not properties:
        summary_text = _summarize_chunks(normalized_chunks)
        properties = [SpecProperty(key=_derive_spec_title(query), value=summary_text)]

    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(ctx=ctx, chunk_index=0)

    if use_spec:
        spec = CanvasNode(
            node_type="spec",
            spec_title=_derive_spec_title(query),
            properties=properties,
            status="found",
        )
        _mark_node_for_run(spec, ctx)
        ctx.deps.state.nodes.append(spec)
        _ensure_relation(ctx, topic.id, spec.id)

        if resolved_filename and resolved_page is not None:
            source_node = _get_or_create_source_node(
                ctx=ctx,
                filename=resolved_filename,
                page=resolved_page,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )
            if not any(node.id == source_node.id for node in ctx.deps.state.nodes):
                ctx.deps.state.nodes.append(source_node)
            _ensure_relation(ctx, spec.id, source_node.id)

        summary = _summarize_properties(properties, resolved_filename)
        result = _snapshot(ctx)
        result.return_value = {
            "summary": summary,
            "topic_id": topic.id,
            "node_id": spec.id,
            "found": True,
            "format": "spec",
        }
        return result

    fact_text = _summarize_chunks(normalized_chunks)
    fact = CanvasNode(node_type="fact", text=fact_text, status="found")
    _mark_node_for_run(fact, ctx)
    ctx.deps.state.nodes.append(fact)
    _ensure_relation(ctx, topic.id, fact.id)

    if resolved_filename and resolved_page is not None:
        source_node = _get_or_create_source_node(
            ctx=ctx,
            filename=resolved_filename,
            page=resolved_page,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )
        if not any(node.id == source_node.id for node in ctx.deps.state.nodes):
            ctx.deps.state.nodes.append(source_node)
        _ensure_relation(ctx, fact.id, source_node.id)

    summary = fact_text
    if resolved_filename:
        summary = f"{summary} Source: {resolved_filename}."
    result = _snapshot(ctx)
    result.return_value = {
        "summary": summary,
        "topic_id": topic.id,
        "node_id": fact.id,
        "found": True,
        "format": "fact",
    }
    return result

@agent.tool
async def add_topic(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id.

    During the PLAN phase use status="pending". Set status="found" once confirmed.
    """
    node = CanvasNode(node_type="topic", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_fact(
    ctx: RunContext[AgentDeps],
    text: str,
    topic_id: str,
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a fact node linked to a topic. Returns the new node's id.

    During the PLAN phase, pass a placeholder text and status="pending".
    After finding the data, prefer finalize_fact_with_source to fill the real
    text, mark the status, and attach evidence in one step.
    """
    node = CanvasNode(node_type="fact", text=text, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=topic_id, to_id=node.id))
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_source(
    ctx: RunContext[AgentDeps],
    fact_id: str,
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
) -> ToolReturn:
    """Add a source node linked to a fact.

    - page / bbox: primary reference (first/most relevant location).
    - highlights: ordered list of {page, bbox} refs so the PDF viewer can
      step through all relevant locations in the document. If omitted, a
      single highlight is created from page + bbox automatically.
    - If filename/page/bbox are omitted, the tool uses the cached chunk from the
      most recent search_knowledge_base call in this run.

    bbox format: [left, top, right, bottom] in PDF points (BOTTOMLEFT origin).
    Use [0,0,0,0] if the bounding box is unknown.
    """
    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )
    if not resolved_filename or resolved_page is None:
        return ToolReturn(
            return_value={
                "success": False,
                "error": "Source details missing. Provide filename/page/bbox or search the knowledge base first.",
            }
        )

    node = _get_or_create_source_node(
        ctx=ctx,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )
    if not any(n.id == node.id for n in ctx.deps.state.nodes):
        ctx.deps.state.nodes.append(node)
    _ensure_relation(ctx, fact_id, node.id)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


@agent.tool
async def finalize_fact_with_source(
    ctx: RunContext[AgentDeps],
    fact_id: str,
    text: str,
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Finalize an existing fact node and attach a source in one step.

    Use this after you already created a pending fact during the planning phase.
    This is the preferred way to complete a factual finding because it updates the
    fact text/status and adds the supporting source evidence together. If you have
    just called search_knowledge_base, you can omit filename/page/bbox and use
    chunk_index to attach evidence from the cached search results.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == fact_id), None)
    if node is None or node.node_type != "fact":
        return ToolReturn(return_value={"success": False, "error": f"Fact node {fact_id} not found"})

    _mark_node_for_run(node, ctx)
    node.text = text
    node.status = status

    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )
    if not resolved_filename or resolved_page is None:
        return ToolReturn(
            return_value={
                "success": False,
                "error": "Source details missing. Provide filename/page/bbox or search the knowledge base first.",
            }
        )

    source_node = _get_or_create_source_node(
        ctx=ctx,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )
    if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
        ctx.deps.state.nodes.append(source_node)
    _ensure_relation(ctx, fact_id, source_node.id)

    result = _snapshot(ctx)
    result.return_value = {"success": True, "fact_id": fact_id, "source_id": source_node.id}
    return result

@agent.tool
async def add_relation(ctx: RunContext[AgentDeps], from_id: str, to_id: str, label: str = "") -> ToolReturn:
    """Connect any two canvas nodes with an optional relationship label."""
    ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))
    return _snapshot(ctx)

@agent.tool
async def search_knowledge_base(
    ctx: RunContext[AgentDeps],
    query: str,
    filename: str | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
):
    """Search the knowledge base.

    This tool automatically applies the currently selected active document
    filter when one exists. Use it before asking the user to restate which
    document/material they mean if their question is otherwise technical.
    """
    from src.core.context import get_active_document_id
    from src.knowledge_base.service import get_document_service

    active_doc_id = get_active_document_id()
    document_id_filter = active_doc_id
    if document_id_filter is None and doc_ids and len(doc_ids) == 1:
        document_id_filter = doc_ids[0]

    service = await get_document_service()
    fetch_k = max(top_k, 40 if (filename or (doc_ids and len(doc_ids) > 1)) else top_k)
    chunks = await service.search(query=query, top_k=fetch_k, document_id=document_id_filter)

    if filename:
        normalized_filename = filename.strip().lower()
        filtered_by_filename = [
            chunk for chunk in chunks
            if str(chunk.get("filename") or "").strip().lower() == normalized_filename
        ]
        if filtered_by_filename:
            chunks = filtered_by_filename

    if doc_ids:
        doc_id_set = set(doc_ids)
        filtered_by_doc_ids = [chunk for chunk in chunks if chunk.get("document_id") in doc_id_set]
        if filtered_by_doc_ids:
            chunks = filtered_by_doc_ids

    normalized_chunks = []
    for chunk in chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        normalized_chunks.append(normalized)

    _remember_search_results(ctx, normalized_chunks)

    first_provenance = (normalized_chunks[0].get("provenance") if normalized_chunks else {}) or {}
    retrieval = first_provenance.get("pipeline", {}).get("retrieval", {})
    trace = first_provenance.get("trace", {})

    return {
        "chunks": normalized_chunks,
        "sources": list(dict.fromkeys(chunk.get("filename") for chunk in normalized_chunks if chunk.get("filename"))),
        "retrieval_id": retrieval.get("retrieval_id"),
        "trace_id": trace.get("trace_id"),
    }

@agent.tool
async def add_spec_node(
    ctx: RunContext[AgentDeps],
    parent_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a spec (property table) node linked to a topic or fact.

    Use this instead of add_fact when data is tabular/parametric:
    dimensions, temperatures, flow rates, material grades, model numbers, etc.

    During the PLAN phase use status="pending" and an empty properties list.
    After extracting the table data, prefer finalize_spec_with_source so the
    table and supporting evidence are attached together.

    - parent_id: id of the parent topic or fact node
    - spec_title: short label for the table (e.g. "Dimensions (mm)", "Operating Limits")
    - properties: list of {key, value, unit} rows (can be [] during planning)
    """
    node = CanvasNode(
        node_type="spec",
        spec_title=spec_title,
        properties=properties,
        status=status,
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=parent_id, to_id=node.id))
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


@agent.tool
async def finalize_spec_with_source(
    ctx: RunContext[AgentDeps],
    spec_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Finalize an existing spec node and attach a source in one step.

    Use this after planning a pending spec node when the retrieved result is
    best represented as a table or property list. If you have just called
    search_knowledge_base, you can omit filename/page/bbox and use chunk_index.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == spec_id), None)
    if node is None or node.node_type != "spec":
        return ToolReturn(return_value={"success": False, "error": f"Spec node {spec_id} not found"})

    _mark_node_for_run(node, ctx)
    node.spec_title = spec_title
    node.properties = properties
    node.status = status

    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )
    if not resolved_filename or resolved_page is None:
        return ToolReturn(
            return_value={
                "success": False,
                "error": "Source details missing. Provide filename/page/bbox or search the knowledge base first.",
            }
        )

    source_node = _get_or_create_source_node(
        ctx=ctx,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )
    if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
        ctx.deps.state.nodes.append(source_node)
    _ensure_relation(ctx, spec_id, source_node.id)

    result = _snapshot(ctx)
    result.return_value = {"success": True, "spec_id": spec_id, "source_id": source_node.id}
    return result


@agent.tool
async def update_node(
    ctx: RunContext[AgentDeps],
    node_id: str,
    status: NodeStatus | None = None,
    title: str | None = None,
    text: str | None = None,
    spec_title: str | None = None,
    properties: list[SpecProperty] | None = None,
) -> ToolReturn:
    """Update fields on an existing canvas node.

    Use this to:
    - Mark a node's status after searching (status="found"/"partial"/"not_found")
    - Fill in the real content after planning (text, title, spec_title, properties)
    - Correct or refine previously added content

    Only the fields you provide are changed; others stay as-is.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == node_id), None)
    if node is None:
        return ToolReturn(return_value={"success": False, "error": f"Node {node_id} not found"})
    _mark_node_for_run(node, ctx)
    if status is not None:
        node.status = status
    if title is not None:
        node.title = title
    if text is not None:
        node.text = text
    if spec_title is not None:
        node.spec_title = spec_title
    if properties is not None:
        node.properties = properties

    has_linked_source = any(
        rel.from_id == node.id
        and any(candidate.id == rel.to_id and candidate.node_type == "source" for candidate in ctx.deps.state.nodes)
        for rel in ctx.deps.state.relations
    )
    if (
        node.node_type in {"fact", "spec"}
        and node.status in {"found", "partial"}
        and not has_linked_source
    ):
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(ctx=ctx)
        if resolved_filename and resolved_page is not None:
            source_node = _get_or_create_source_node(
                ctx=ctx,
                filename=resolved_filename,
                page=resolved_page,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )
            if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
                ctx.deps.state.nodes.append(source_node)
            _ensure_relation(ctx, node.id, source_node.id)
    return _snapshot(ctx)


@agent.tool
async def delete_node(ctx: RunContext[AgentDeps], node_id: str) -> ToolReturn:
    """Delete a canvas node and all its relations.

    Use this to remove placeholder nodes that turned out to be irrelevant,
    or to clean up duplicates.
    """
    ctx.deps.state.nodes = [n for n in ctx.deps.state.nodes if n.id != node_id]
    ctx.deps.state.relations = [
        r for r in ctx.deps.state.relations
        if r.from_id != node_id and r.to_id != node_id
    ]
    return _snapshot(ctx)


@agent.tool
async def analyze_image_content(
    ctx: RunContext[AgentDeps],
    image_url: str,
    question: str,
) -> str:
    """Download a PDF screenshot and use vision AI to extract structured content.

    Use this when a chunk references a table, diagram, or chart that cannot be
    understood from the text alone. Pass the screenshot URL from the chunk metadata
    and ask a specific question (e.g. "Extract all rows and columns from this table
    as key-value pairs with units").

    Returns the extracted text/data as a string.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/png")

        result = await image_analysis_agent.run(
            [
                BinaryContent(data=image_bytes, media_type=content_type),
                question,
            ]
        )
        return result.response.text
    except Exception as exc:
        return f"Image analysis failed: {exc}"

AppState = Canvas
