import os
import re
from typing import Any
from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from .deps import AgentDeps
from .state import Canvas, CanvasNode, Relation, SourceHighlight, SpecProperty

def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}

STRICT_CANVAS_VALIDATION = _env_flag("STRICT_CANVAS_VALIDATION", "0")

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
_RAW_SEARCH_RE = re.compile(
    r"\b(raw retrieval|raw search|search results?|retrieved chunks?|inspect chunks?|inspect retrieval|debug retrieval|without (?:changing|updating) the canvas)\b",
    re.IGNORECASE,
)
_EARLY_SOCIAL_OR_META_RE = _SOCIAL_OR_META_RE
_EARLY_DOCUMENT_LISTING_RE = _DOCUMENT_LISTING_RE
_EARLY_CANVAS_EDIT_RE = _CANVAS_EDIT_RE
_EARLY_RAW_SEARCH_RE = _RAW_SEARCH_RE
_MODEL_CODE_RE = re.compile(r"\b([A-Z]{2,}(?:\d+[A-Z]?|-\d+[A-Z]?)?)\b")
_ROW_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9() /-]{0,60}$")
_LEADING_QUERY_PHRASE_RE = re.compile(
    r"^\s*(what(?:'s| is| are)?|which|show(?: me)?|tell me|give me|list|describe|explain)\s+",
    re.IGNORECASE,
)
_TRAILING_CONTEXT_RE = re.compile(r"\s+\bfrom\b\s+.+$", re.IGNORECASE)
_PROPERTY_MATCH_STOPWORDS = {
    "what", "which", "when", "where", "why", "who", "how", "is", "are", "the", "a", "an",
    "for", "from", "of", "to", "in", "on", "with", "and", "or", "does", "do", "it", "its",
    "this", "that", "these", "those", "about", "tell", "me", "show", "give", "list",
}
_SECTION_TABLE_QUERY_RE = re.compile(
    r"\b(operating data|technical data|specs?|specifications?|fact sheet|fact table|properties|dimensions?|parameters?|table|all values|values for)\b",
    re.IGNORECASE,
)
_PROPERTY_GROUP_ALIASES: dict[str, set[str]] = {
    "temperature": {"temperature", "temp", "thermal", "sterilization"},
    "pressure": {"pressure", "pressur", "bar", "kpa", "mpa"},
    "limit": {"limit", "limits", "range", "ranges", "value", "values", "minimum", "maximum", "min", "max"},
    "dimension": {"dimension", "dimensions", "dim", "dims", "length", "width", "height"},
    "flow": {"flow", "capacity", "consumption"},
    "speed": {"speed", "rpm"},
    "power": {"power", "kw", "hp", "horsepower", "w"},
    "connection": {"connection", "connections", "port", "ports", "thread", "inlet", "outlet"},
    "material": {"material", "materials", "steel", "elastomer", "seal"},
    "motor": {"motor", "frequency", "voltage", "current", "phase"},
    "warranty": {"warranty", "warranties", "guarantee", "guarantees"},
}

def _normalize_match_token(token: str) -> str:
    normalized = token.lower().strip()
    if len(normalized) > 4 and normalized.endswith("ies"):
        return normalized[:-3] + "y"
    if len(normalized) > 3 and normalized.endswith("es"):
        return normalized[:-2]
    if len(normalized) > 3 and normalized.endswith("s"):
        return normalized[:-1]
    return normalized

def _query_match_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        normalized = _normalize_match_token(token)
        if len(normalized) > 2 and normalized not in _PROPERTY_MATCH_STOPWORDS:
            tokens.add(normalized)
    return tokens


def _is_section_table_query(query: str) -> bool:
    return bool(_SECTION_TABLE_QUERY_RE.search(query))


def _property_groups_for_text(text: str) -> set[str]:
    tokens = _query_match_tokens(text)
    matched: set[str] = set()
    for group, aliases in _PROPERTY_GROUP_ALIASES.items():
        if tokens & aliases:
            matched.add(group)
    return matched


def _query_requests_multiple_property_groups(query: str) -> bool:
    return len(_property_groups_for_text(query)) > 1

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

_EXPLANATION_OR_META_RE = re.compile(
    r"\b(explain|summari[sz]e|describe|what is this|what does this|why|how does|ui|interface|button|reload|error)\b",
    re.IGNORECASE,
)

def _request_signal_text(prompt: object, output: object | None = None) -> str:
    prompt_text = _prompt_to_text(prompt).strip()
    if prompt_text:
        return prompt_text
    return str(output or "").strip()

def _requires_canvas_materialization(prompt: object, state: Canvas, output: object | None = None) -> bool:
    text = _request_signal_text(prompt, output)
    if not text:
        return False
    if _EXPLANATION_OR_META_RE.search(text) or not _requires_canvas_update(text):
        return False
    if not (_is_section_table_query(text) or _property_groups_for_text(text)):
        return False
    return any(node.node_type == "document" and node.filename for node in state.nodes)

def _has_materialized_canvas_content(ctx: RunContext[AgentDeps]) -> bool:
    run_id = ctx.run_id or ""
    content_nodes = [node for node in ctx.deps.state.nodes if node.node_type in {"fact", "spec"}]
    if run_id and any(node.last_updated_run_id == run_id for node in content_nodes):
        return True

    # If an earlier matching node already exists, the agent may correctly reuse it.
    prompt_tokens = _query_match_tokens(_prompt_to_text(ctx.prompt))
    for node in content_nodes:
        text = " ".join([
            node.title,
            node.text,
            node.spec_title,
            " ".join(
                " ".join([section.name, *[f"{row.parameter} {row.value} {row.unit}" for row in section.rows]])
                for section in node.parameter_sections
            ),
        ]).lower()
        if prompt_tokens and prompt_tokens & _query_match_tokens(text):
            return True
    return False

def _requires_spec_materialization(prompt: object, state: Canvas, output: object | None = None) -> bool:
    if not _requires_canvas_materialization(prompt, state, output):
        return False
    return _is_section_table_query(_request_signal_text(prompt, output))

def _has_materialized_spec(ctx: RunContext[AgentDeps]) -> bool:
    run_id = ctx.run_id or ""
    specs = [node for node in ctx.deps.state.nodes if node.node_type == "spec"]
    if run_id and any(node.last_updated_run_id == run_id for node in specs):
        return True
    return any(node.parameter_sections for node in specs)

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
    normalized_document_id = document_id.removeprefix("__doc_")
    for node in ctx.deps.state.nodes:
        if node.node_type != "document":
            continue
        node_doc_id = node.id.removeprefix("__doc_")
        if normalized_document_id == node_doc_id or normalized_document_id == node.filename:
            normalized_document_id = node_doc_id
            break
    to_id = f"__doc_{normalized_document_id}"
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
            document_id=normalized_document_id,
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
    normalized = re.sub(r":\s*,\s*=\s*", ": ", text)
    normalized = re.sub(r",\s*\d+\s*=", ":", normalized)
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
    model_specific_properties: list[SpecProperty] = []
    seen: set[tuple[str, str, str]] = set()
    model_match = _MODEL_CODE_RE.search(query)
    query_model = model_match.group(1) if model_match else ""
    current_row_label = ""

    def append_property(key: str, value: str, *, model_specific: bool = False) -> None:
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
        prop = SpecProperty(key=key, value=value, unit=unit)
        properties.append(prop)
        if model_specific:
            model_specific_properties.append(prop)

    def looks_like_row_label(segment: str) -> bool:
        return bool(
            segment
            and query_model.lower() not in segment.lower()
            and "=" not in segment
            and ":" not in segment
            and _ROW_LABEL_RE.match(segment)
        )

    for line in _split_candidate_lines(text):
        if looks_like_row_label(line):
            current_row_label = line
            continue

        if query_model and query_model.lower() in line.lower():
            segments = [_clean_text_value(segment) for segment in re.split(r"[;,\t]", line) if _clean_text_value(segment)]
            if segments:
                row_label = ""
                matched_model_segment = False
                for segment in segments:
                    model_value_match = re.search(
                        rf"\b{re.escape(query_model)}\b\s*(?:=|:)?\s*(.+)$",
                        segment,
                        re.IGNORECASE,
                    )
                    if model_value_match:
                        key = row_label or current_row_label or query_model
                        value = _clean_text_value(model_value_match.group(1))
                        if key and value:
                            append_property(key, value, model_specific=True)
                            matched_model_segment = True
                        continue
                    if looks_like_row_label(segment):
                        row_label = segment
                if matched_model_segment:
                    continue

        pair_matches = list(re.finditer(r"([^:=.;\n]+)[:=]\s*([^.;\n]+)", line))
        if pair_matches:
            current_row_label = ""
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
            append_property(query_model, f"{number_match.group(1)} {number_match.group(2)}", model_specific=True)

    if query_model and model_specific_properties:
        return model_specific_properties

    return properties

def _select_relevant_properties(properties: list[SpecProperty], query: str) -> list[SpecProperty]:
    if _is_section_table_query(query):
        return properties

    if _query_requests_multiple_property_groups(query):
        requested_groups = _property_groups_for_text(query)
        multi_matches: list[SpecProperty] = []
        seen_signatures: set[tuple[str, str, str]] = set()
        for prop in properties:
            prop_groups = _property_groups_for_text(f"{prop.key} {prop.value} {prop.unit}".strip())
            if not (prop_groups & requested_groups):
                continue
            signature = (prop.key.lower().strip(), prop.value.lower().strip(), prop.unit.lower().strip())
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            multi_matches.append(prop)
        if multi_matches:
            return multi_matches

    query_tokens = _query_match_tokens(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, int, SpecProperty]] = []
    for index, prop in enumerate(properties):
        key_text = prop.key.lower().strip()
        key_tokens = _query_match_tokens(key_text)
        overlap = len(query_tokens & key_tokens)
        exact = 1 if key_text and key_text in query.lower() else 0
        score = exact * 100 + overlap
        if score > 0:
            scored.append((score, index, prop))

    if not scored:
        return []

    best_score = max(score for score, _, _ in scored)
    return [prop for score, _, prop in scored if score == best_score]

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

def _derive_query_focus(query: str) -> str:
    focus = _LEADING_QUERY_PHRASE_RE.sub("", query.strip().rstrip("?.!"))
    focus = re.sub(r"^(?:the|a|an)\s+", "", focus, flags=re.IGNORECASE)
    focus = _TRAILING_CONTEXT_RE.sub("", focus)
    focus = re.sub(r"\s+", " ", focus).strip(" :-")
    if not focus:
        return ""
    return focus[:1].upper() + focus[1:]

def _derive_topic_title(query: str) -> str:
    normalized = query.strip().rstrip("?.!")
    lowered = normalized.lower()
    if re.search(r"\boperating data\b", lowered):
        return "Operating Data"
    if re.search(r"\btechnical data\b", lowered):
        return "Technical Data"
    if "dimension" in lowered or "measure" in lowered:
        model_match = _MODEL_CODE_RE.search(normalized)
        if model_match:
            return f"{model_match.group(1)} Dimensions"
        return "Dimensions"
    if re.search(r"\b(materials?|construction|wetted parts?|seal material)\b", lowered):
        return "Materials"
    if re.search(r"\b(max|min|maximum|minimum|limit|pressure|temperature|viscosity|density|rating|ratings|operating)\b", lowered):
        return "Operating Limits"
    if re.search(r"\b(flow|curve|performance|capacity|speed|rpm|power|efficiency|head|npsh)\b", lowered):
        return "Performance"
    if re.search(r"\b(connection|connections|port|ports|thread|flange|inlet|outlet)\b", lowered):
        return "Connections"
    if re.search(r"\b(motor|voltage|frequency|current|phase)\b", lowered):
        return "Motor"
    if re.search(r"\b(installation|mounting|setup|wiring)\b", lowered):
        return "Installation"
    if re.search(r"\b(overview|summary|what is|what are|describe|explain|features?|benefits?|capabilities)\b", lowered):
        return "Overview"
    if re.search(r"\bmaterials?\b", lowered):
        return "Materials"
    if re.search(r"\b(technical data|specs?|specifications?|properties|ratings?)\b", lowered):
        return "Technical Data"
    derived_focus = _derive_query_focus(normalized)
    if derived_focus:
        return derived_focus
    if normalized:
        return normalized[:80]
    return "Technical Query"

def _derive_spec_title(query: str) -> str:
    lowered = query.strip().lower()
    if re.search(r"\boperating data\b", lowered):
        return "Operating Data"
    if "dimension" in lowered or "measure" in lowered:
        return "Dimensions"
    if re.search(r"\bmaterials?\b", lowered):
        return "Materials"
    if "technical data" in lowered:
        return "Technical Data"
    return "Specifications"
