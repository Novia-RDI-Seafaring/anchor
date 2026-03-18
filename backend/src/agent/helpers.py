import os
import re
from typing import Any
from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from .deps import AgentDeps
from .state import CanvasNode, Relation, SourceHighlight, SpecProperty

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

def _early_prompt_to_text(prompt: str | list | tuple | None) -> str:
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, (list, tuple)):
        for item in reversed(prompt):
            if isinstance(item, str):
                return item
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(text, str):
                return text
    return ""

def _prompt_to_text(prompt: str | list | tuple | None) -> str:
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, (list, tuple)):
        for item in reversed(prompt):
            if isinstance(item, str):
                return item
            text = getattr(item, "text", None)
            if isinstance(text, str):
                return text
            content = getattr(item, "content", None)
            if isinstance(content, str):
                return content
            rendered = str(item)
            if rendered:
                return rendered
    return ""

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

def _requires_canvas_update(prompt: str) -> bool:
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    if _SOCIAL_OR_META_RE.search(normalized):
        return False
    if _DOCUMENT_LISTING_RE.search(normalized):
        return False
    return True

def _ensure_evidence_relation(
    ctx: RunContext[AgentDeps],
    from_id: str,
    document_id: str,
    page: int = 0,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    label: str = "",
) -> None:
    """Add an evidence edge from a fact/spec node to a document node.

    The document node ID is derived from document_id using the convention __doc_{document_id}.
    Evidence edges carry location metadata (page, bbox, highlights) to open the PDF at the right spot.
    Deduplicates: won't add if identical (from_id, to_id, page) already exists.
    """
    to_id = f"__doc_{document_id}"
    existing = next(
        (rel for rel in ctx.deps.state.relations
         if rel.from_id == from_id and rel.to_id == to_id and rel.page == page),
        None,
    )
    if existing is None:
        ctx.deps.state.relations.append(Relation(
            from_id=from_id,
            to_id=to_id,
            label=label,
            document_id=document_id,
            page=page,
            bbox=bbox or [],
            highlights=highlights or [],
        ))


def _find_node_by_title(ctx: RunContext[AgentDeps], title: str, node_type: str) -> "CanvasNode | None":
    title_lower = title.lower().strip()
    for node in ctx.deps.state.nodes:
        if node.node_type == node_type and node.title.lower().strip() == title_lower:
            return node
    return None


def _get_cached_document_id(ctx: RunContext[AgentDeps], chunk_index: int = 0) -> str | None:
    chunk = _get_cached_chunk(ctx, chunk_index)
    if not chunk:
        return None
    return chunk.get("document_id") or None


def _clean_text_value(value: str) -> str:
    # Preserve newlines but trim leading/trailing space for each line
    lines = [line.strip().strip("-•*") for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()

def _split_candidate_lines(text: str) -> list[str]:
    normalized = re.sub(r",\s*\d+\s*=", ":", text)
    normalized = re.sub(r"\.\s+(?=[A-Z][A-Za-z0-9 /()_-]{2,60}:)", "\n", normalized)
    base_lines = [_clean_text_value(line) for line in normalized.replace("\r", "\n").split("\n")]
    lines = [line for line in base_lines if line]
    if len(lines) >= 2:
        return lines
    expanded = []
    for part in re.split(r"[;•]", normalized):
        cleaned = _clean_text_value(part)
        if cleaned:
            expanded.append(cleaned)
    return expanded or lines

def _extract_properties_from_text(text: str, query: str) -> list[SpecProperty]:
    properties: list[SpecProperty] = []
    seen: set[tuple[str, str, str]] = set()
    model_match = _MODEL_CODE_RE.search(query)
    query_model = model_match.group(1) if model_match else ""

    def append_property(key: str, value: str) -> None:
        nonlocal properties, seen
        unit = ""
        unit_match = re.search(r"^(.*?)(?:\s+)([a-zA-Z°][a-zA-Z0-9/°]*)$", value)
        if unit_match:
            potential_value = _clean_text_value(unit_match.group(1))
            potential_unit = unit_match.group(2)
            if re.search(r"\d", potential_value) or potential_unit.lower() in {"bar", "kg", "mm", "cm", "m", "kw", "w", "a", "v", "hz", "rpm", "c", "f"}:
                value = potential_value
                unit = potential_unit

        signature = (key.lower(), value.lower(), unit.lower())
        if signature in seen:
            return
        seen.add(signature)
        properties.append(SpecProperty(key=key, value=value, unit=unit))

    for line in _split_candidate_lines(text):
        pair_matches = list(re.finditer(r"([^:=.;\n]+)[:=]\s*([^.;\n]+)", line))
        if pair_matches:
            for match in pair_matches:
                key = _clean_text_value(match.group(1))
                value = _clean_text_value(match.group(2))
                if not key or not value:
                    continue
                append_property(key, value)
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

def _flatten_render_payload(value: Any, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(value, SpecProperty):
        rendered_value = value.value if not value.unit else f"{value.value} {value.unit}"
        return f"{value.key} {rendered_value}"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_render_payload(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_render_payload(item, depth + 1) for item in value)
    return str(value)

def _chunk_overlap_score(chunk: dict, rendered_payload: Any) -> float:
    rendered_text = _flatten_render_payload(rendered_payload).lower().strip()
    if not rendered_text:
        return -1.0
    rendered_tokens = set(rendered_text.split())
    if not rendered_tokens:
        return -1.0

    chunk_text = str(chunk.get("content") or "").lower().strip()
    if not chunk_text:
        return -1.0
    chunk_tokens = set(chunk_text.split())
    if not chunk_tokens:
        return -1.0

    overlap = len(rendered_tokens & chunk_tokens)
    if overlap <= 0:
        return 0.0
    return overlap / len(chunk_tokens)

def _select_best_chunk_index(chunks: list[dict], rendered_payload: Any) -> int:
    if not chunks:
        return 0
    best_index = 0
    best_score = -1.0
    for index, chunk in enumerate(chunks):
        score = _chunk_overlap_score(chunk, rendered_payload)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index

def _summarize_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant data found."
    content = _clean_text_value(str(chunks[0].get("content") or ""))
    if not content:
        return "Relevant content was found, but the extracted text was empty."
    if len(content) > 1000:
        content = content[:997].rstrip() + "..."
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
