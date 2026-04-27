import json
import logging
import re

from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, Relation, SourceHighlight, SpecProperty, ParameterSection, NodeStatus
from ..helpers import (
    _snapshot,
    _mark_node_for_run,
    _ensure_relation,
    _ensure_evidence_relation,
    _resolve_source_details,
    _get_cached_document_id,
    _find_node_by_title,
)
# bbox backfill from docling items removed — gold regions carry bboxes now

_LOGGER = logging.getLogger(__name__)


def _clean_markdown_cell(cell: str) -> str:
    cell = re.sub(r"<br\s*/?>", " ", cell, flags=re.IGNORECASE)
    cell = re.sub(r"\s+", " ", cell)
    return cell.strip().strip("*_`")


def _is_markdown_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell.strip()) for cell in cells)


def _markdown_table_rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "|" not in stripped[1:]:
            continue
        cells = [_clean_markdown_cell(cell) for cell in stripped.strip("|").split("|")]
        if _is_markdown_separator(cells):
            continue
        if len(cells) >= 2 and any(cells):
            rows.append(cells)
    return rows


def _without_parenthetical_qualifiers(text: str) -> str:
    return re.sub(r"\s*\([^)]{1,80}\)", "", text).strip()


def _replace_value_fragment(text: str, old_value: str, new_value: str) -> str:
    if old_value in text:
        return text.replace(old_value, new_value, 1)
    pattern = re.escape(old_value).replace(r"\ ", r"\s+")
    replaced = re.sub(pattern, new_value, text, count=1, flags=re.IGNORECASE)
    if replaced != text:
        return replaced
    return f"{text.rstrip('.')} (source value: {new_value})."


def _enrich_fact_text_from_source_row(text: str, filename: str | None, page: int) -> str:
    """Preserve source-row qualifiers when a fact is condensed for the canvas."""
    if not filename or page <= 0:
        return text

    try:
        from .product_data import find_silver_pages_by_filename

        page_md = (find_silver_pages_by_filename(filename) or {}).get(page)
    except Exception:
        page_md = None

    if not page_md:
        return text

    normalized_text = _normalize_for_match(text)
    text_tokens = _match_tokens(text)
    best: tuple[int, str, str] | None = None

    for cells in _markdown_table_rows(page_md):
        for label, value in zip(cells, cells[1:]):
            if not label or not value:
                continue
            label_tokens = _match_tokens(label)
            if label_tokens and not (label_tokens & text_tokens):
                continue

            normalized_value = _normalize_for_match(value)
            if normalized_value and normalized_value in normalized_text:
                continue

            core_value = _without_parenthetical_qualifiers(value)
            normalized_core = _normalize_for_match(core_value)
            if not normalized_core or normalized_core not in normalized_text:
                continue

            extra_tokens = _match_tokens(value) - _match_tokens(core_value)
            if not extra_tokens:
                continue

            score = (4 * len(label_tokens & text_tokens)) + len(extra_tokens)
            if best is None or score > best[0]:
                best = (score, core_value, value)

    if best is None:
        return text
    _, old_value, new_value = best
    return _replace_value_fragment(text, old_value, new_value)


def _document_id_from_filename(ctx: RunContext[AgentDeps], filename: str | None) -> str | None:
    if not filename:
        return None
    target = filename.lower().removesuffix(".pdf").strip()
    for node in ctx.deps.state.nodes:
        if node.node_type != "document" or not node.filename:
            continue
        candidate = node.filename.lower().removesuffix(".pdf").strip()
        if candidate == target or candidate.startswith(target) or target.startswith(candidate):
            return node.id.removeprefix("__doc_")
    return None


def _filename_from_document_id(ctx: RunContext[AgentDeps], document_id: str | None) -> str | None:
    if not document_id:
        return None
    normalized_document_id = document_id.removeprefix("__doc_")
    for node in ctx.deps.state.nodes:
        if node.node_type != "document":
            continue
        node_doc_id = node.id.removeprefix("__doc_")
        if normalized_document_id == node_doc_id or normalized_document_id == node.filename:
            return node.filename or None
    return None


def _match_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1
    }


def _normalize_for_match(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9./+-]+", text.lower()))


def _score_docling_item(item: dict, section_name: str, parameter: str, value: str, unit: str) -> tuple[int, list[float]]:
    bbox = item.get("bbox")
    if isinstance(bbox, dict):
        bbox_list = [
            float(bbox.get("l", 0)),
            float(bbox.get("t", 0)),
            float(bbox.get("r", 0)),
            float(bbox.get("b", 0)),
        ]
    else:
        bbox_list = []
    if len(bbox_list) != 4 or not any(value != 0.0 for value in bbox_list):
        return -1, []

    item_text = str(item.get("text") or "")
    if not item_text and item.get("table_data") is not None:
        item_text = json.dumps(item.get("table_data"), ensure_ascii=True, default=str)
    normalized_item = _normalize_for_match(item_text)
    if not normalized_item:
        return -1, []

    score = 0
    normalized_parameter = _normalize_for_match(parameter)
    normalized_value = _normalize_for_match(value)
    normalized_unit = _normalize_for_match(unit)
    normalized_section = _normalize_for_match(section_name)

    if normalized_parameter and normalized_parameter in normalized_item:
        score += 10
    if normalized_value and normalized_value in normalized_item:
        score += 12
    if normalized_unit and normalized_unit in normalized_item:
        score += 3
    if normalized_section and normalized_section in normalized_item:
        score += 2

    item_tokens = _match_tokens(item_text)
    score += 2 * len(_match_tokens(parameter) & item_tokens)
    score += 3 * len(_match_tokens(value) & item_tokens)
    score += 1 * len(_match_tokens(unit) & item_tokens)
    score += 1 * len(_match_tokens(section_name) & item_tokens)

    if score <= 0:
        return -1, []
    return score, bbox_list


def _backfill_section_row_bboxes(sections: list[ParameterSection]) -> int:
    page_item_cache: dict[tuple[str, int], list[dict]] = {}
    backfilled = 0

    for section in sections:
        for row in section.rows:
            source = row.source
            if source.bbox or not source.filename or source.page <= 0:
                if source.bbox:
                    _LOGGER.info(
                        "Spec row already has bbox: section='%s' parameter='%s' value='%s' page=%s",
                        section.name,
                        row.parameter,
                        row.value,
                        source.page,
                    )
                else:
                    _LOGGER.info(
                        "Skipping bbox backfill: section='%s' parameter='%s' value='%s' filename='%s' page=%s",
                        section.name,
                        row.parameter,
                        row.value,
                        source.filename,
                        source.page,
                    )
                continue

            cache_key = (source.filename, source.page)
            if cache_key not in page_item_cache:
                page_item_cache[cache_key] = []  # docling items removed; gold regions carry bboxes
            page_items = page_item_cache[cache_key]
            if not page_items:
                _LOGGER.warning(
                    "No docling page items available for bbox backfill: filename='%s' page=%s section='%s' parameter='%s' value='%s'",
                    source.filename,
                    source.page,
                    section.name,
                    row.parameter,
                    row.value,
                )
                continue

            best_score = -1
            best_bbox: list[float] = []
            best_item_text = ""
            for item in page_items:
                score, bbox = _score_docling_item(
                    item=item,
                    section_name=section.name,
                    parameter=row.parameter,
                    value=row.value,
                    unit=row.unit,
                )
                if score > best_score and bbox:
                    best_score = score
                    best_bbox = bbox
                    best_item_text = str(item.get("text") or "")[:180]

            if best_bbox:
                source.bbox = best_bbox
                backfilled += 1
                _LOGGER.info(
                    "Backfilled bbox: filename='%s' page=%s section='%s' parameter='%s' value='%s' score=%s bbox=%s item='%s'",
                    source.filename,
                    source.page,
                    section.name,
                    row.parameter,
                    row.value,
                    best_score,
                    best_bbox,
                    best_item_text,
                )
            else:
                _LOGGER.warning(
                    "Failed to match bbox: filename='%s' page=%s section='%s' parameter='%s' value='%s' items=%s",
                    source.filename,
                    source.page,
                    section.name,
                    row.parameter,
                    row.value,
                    len(page_items),
                )

    return backfilled


async def check_canvas(ctx: RunContext[AgentDeps]):
    """Return the current canvas state (nodes + relations)."""
    return ctx.deps.state


async def add_topic(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id."""
    node = CanvasNode(node_type="topic", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_concept(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a concept node — the root organizer for a knowledge cluster.
    A concept represents the high-level subject (e.g. 'A2UI', 'Material X').
    Returns the node id; reuse it when calling resolve_technical_query.
    """
    node = CanvasNode(node_type="concept", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_fact(
    ctx: RunContext[AgentDeps],
    text: str,
    topic_id: str = "",
    status: NodeStatus = "found",
    doc_id: str | None = None,
    filename: str | None = None,
    page: int = 0,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
) -> ToolReturn:
    """Add a fact node linked to a topic.

    Optionally attach evidence by providing doc_id or filename + page (or chunk_index
    to use cached search results). The evidence creates an edge from this fact to the
    document node.
    """
    if not topic_id:
        topic = _find_node_by_title(ctx, "Extracted facts", "topic")
        if topic is None:
            topic = CanvasNode(node_type="topic", title="Extracted facts", status="found")
            _mark_node_for_run(topic, ctx)
            ctx.deps.state.nodes.append(topic)
        topic_id = topic.id

    resolved_doc_id = doc_id or _document_id_from_filename(ctx, filename) or _get_cached_document_id(ctx, chunk_index)
    resolved_filename = filename or _filename_from_document_id(ctx, resolved_doc_id)
    resolved_page = page
    resolved_bbox = bbox or []
    resolved_highlights = highlights or []

    if resolved_doc_id:
        resolved_filename, resolved_page_value, resolved_bbox, resolved_highlights = _resolve_source_details(
            ctx=ctx,
            filename=resolved_filename,
            page=page if page else None,
            bbox=bbox,
            highlights=highlights,
            chunk_index=chunk_index,
        )
        resolved_filename = resolved_filename or _filename_from_document_id(ctx, resolved_doc_id)
        resolved_page = resolved_page_value or page or 0

    enriched_text = _enrich_fact_text_from_source_row(text, resolved_filename, resolved_page)
    node = CanvasNode(node_type="fact", text=enriched_text, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    _ensure_relation(ctx, topic_id, node.id)

    if resolved_doc_id:
        _ensure_evidence_relation(
            ctx, node.id, resolved_doc_id,
            page=resolved_page or page or 0,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )

    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_spec_node(
    ctx: RunContext[AgentDeps],
    spec_title: str,
    sections: list[ParameterSection],
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a parameter table node to the canvas.

    spec_title: title shown at the top (e.g. "LKH-5 Operating Data").
    sections: list of parameter groups. Each section has:
      - name: section header (e.g. "Max inlet pressure", "Temperature")
      - rows: list of parameter rows, each with:
          - parameter: label (e.g. "LKH-5", "Temperature range")
          - value: the value (e.g. "600", "-10 to +140")
          - unit: optional unit (e.g. "kPa", "°C")
          - source: { doc_id, filename, page } — where this value was found

    Every row should have a source so the engineer can click through to the PDF page.
    Evidence edges from rows to document nodes are created automatically by the frontend.
    """
    backfilled_rows = _backfill_section_row_bboxes(sections)
    if backfilled_rows:
        _LOGGER.info("Backfilled bbox for %s spec rows in '%s'", backfilled_rows, spec_title)

    node = CanvasNode(
        node_type="spec",
        spec_title=spec_title,
        parameter_sections=sections,
        status=status,
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)

    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_relation(
    ctx: RunContext[AgentDeps],
    from_id: str,
    to_id: str,
    label: str = "",
    source_handle: str = "",
    target_handle: str = "",
) -> ToolReturn:
    """Connect any two canvas nodes with an optional relationship label."""
    ctx.deps.state.relations.append(
        Relation(
            from_id=from_id,
            to_id=to_id,
            label=label,
            source_handle=source_handle,
            target_handle=target_handle,
        )
    )
    return _snapshot(ctx)


async def update_node(
    ctx: RunContext[AgentDeps],
    node_id: str,
    status: NodeStatus | None = None,
    title: str | None = None,
    text: str | None = None,
    spec_title: str | None = None,
    properties: list[SpecProperty] | None = None,
    parameter_sections: list[ParameterSection] | None = None,
) -> ToolReturn:
    """Update fields on an existing canvas node.

    Only the fields you provide are changed; others stay as-is.
    For spec nodes, pass parameter_sections to replace the table content entirely.
    Same structure as add_spec_node sections — list of {name, rows: [{parameter, value, unit, source}]}.
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
    if parameter_sections is not None:
        backfilled = _backfill_section_row_bboxes(parameter_sections)
        if backfilled:
            _LOGGER.info("Backfilled bbox for %s rows updating node '%s'", backfilled, node_id)
        node.parameter_sections = parameter_sections
    return _snapshot(ctx)


async def delete_node(ctx: RunContext[AgentDeps], node_id: str) -> ToolReturn:
    """Delete a canvas node and all its relations."""
    ctx.deps.state.nodes = [n for n in ctx.deps.state.nodes if n.id != node_id]
    ctx.deps.state.relations = [
        r for r in ctx.deps.state.relations
        if r.from_id != node_id and r.to_id != node_id
    ]
    return _snapshot(ctx)
