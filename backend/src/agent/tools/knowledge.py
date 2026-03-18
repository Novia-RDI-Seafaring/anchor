import re
from pathlib import Path

from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, SpecProperty
from ..helpers import (
    _snapshot,
    _mark_node_for_run,
    _ensure_relation,
    _ensure_evidence_relation,
    _get_cached_document_id,
    _remember_search_results,
    _resolve_source_details,
    _summarize_chunks,
    _summarize_properties,
    _derive_topic_title,
    _derive_spec_title,
    _extract_properties_from_text,
    _TABLE_OR_SPEC_RE,
    _select_page,
    _select_bbox,
    _select_highlights,
    _clean_text_value
)

_COMPARISON_QUERY_RE = re.compile(r"\b(compare|comparison|different|difference|diff|vs\.?|versus)\b", re.IGNORECASE)


def _doc_label(filename: str | None) -> str:
    if not filename:
        return "Unknown document"
    return Path(filename).stem


def _doc_match_score(filename: str | None, query: str) -> int:
    if not filename:
        return 0
    stem = _doc_label(filename).lower()
    score = 0
    if stem and stem in query:
        score += 100
    for token in re.findall(r"[a-z0-9]+", stem):
        if len(token) < 3:
            continue
        if token in query:
            score += 10
    return score


def _pick_comparison_documents(query: str, documents: list[dict]) -> list[dict]:
    processed = [doc for doc in documents if doc.get("status") == "processed"]
    if len(processed) <= 2:
        return processed[:2]

    ranked = sorted(
        processed,
        key=lambda doc: (_doc_match_score(doc.get("filename"), query), str(doc.get("filename") or "")),
        reverse=True,
    )
    top_two = [doc for doc in ranked if _doc_match_score(doc.get("filename"), query) > 0][:2]
    if len(top_two) == 2:
        return top_two
    return ranked[:2]


def _format_property_value(property_row: SpecProperty) -> str:
    return property_row.value if not property_row.unit else f"{property_row.value} {property_row.unit}".strip()


def _normalize_property_key(key: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", key.lower())).strip()


def _extract_doc_properties(chunks: list[dict], query: str) -> tuple[int, list[SpecProperty]]:
    for index, chunk in enumerate(chunks):
        properties = _extract_properties_from_text(str(chunk.get("content") or ""), query)
        if properties:
            return index, properties
    return 0, []


def _build_comparison_properties(
    left_label: str,
    right_label: str,
    left_properties: list[SpecProperty],
    right_properties: list[SpecProperty],
) -> list[SpecProperty]:
    display_keys: dict[str, str] = {}
    left_map: dict[str, str] = {}
    right_map: dict[str, str] = {}
    ordered_keys: list[str] = []

    for row in left_properties:
        norm_key = _normalize_property_key(row.key)
        if not norm_key:
            continue
        if norm_key not in ordered_keys:
            ordered_keys.append(norm_key)
        display_keys.setdefault(norm_key, row.key)
        left_map[norm_key] = _format_property_value(row)

    for row in right_properties:
        norm_key = _normalize_property_key(row.key)
        if not norm_key:
            continue
        if norm_key not in ordered_keys:
            ordered_keys.append(norm_key)
        display_keys.setdefault(norm_key, row.key)
        right_map[norm_key] = _format_property_value(row)

    rows: list[SpecProperty] = []
    for norm_key in ordered_keys:
        left_value = left_map.get(norm_key, "")
        right_value = right_map.get(norm_key, "")
        if left_value and right_value:
            comparison_status = "same" if left_value.strip().lower() == right_value.strip().lower() else "different"
        else:
            comparison_status = "missing"
        rows.append(
            SpecProperty(
                key=display_keys.get(norm_key, norm_key.title()),
                value="",
                left_label=left_label,
                left_value=left_value,
                right_label=right_label,
                right_value=right_value,
                comparison_status=comparison_status,
            )
        )
    return rows

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

async def get_active_document_context(ctx: RunContext[AgentDeps]):
    """Return the currently selected document filter, if any.

    Use this before asking a clarifying question about which document/material
    the user means. If a document is selected, assume generic technical queries
    refer to that document unless the user explicitly says otherwise.
    """
    from src.knowledge_base.service import get_document_service

    active_document_id = ctx.deps.state.active_document_id
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
    from src.knowledge_base.service import get_document_service

    active_doc_id = ctx.deps.state.active_document_id
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
    from src.knowledge_base.service import get_document_service

    service = await get_document_service()
    active_document_id = ctx.deps.state.active_document_id
    active_document = None
    if active_document_id:
        active_document = await service.get_document(active_document_id)

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

    source_chunk_index = 0
    properties: list[SpecProperty] = []
    for index, chunk in enumerate(normalized_chunks):
        chunk_properties = _extract_properties_from_text(str(chunk.get("content") or ""), query)
        if not chunk_properties:
            continue
        source_chunk_index = index
        properties = chunk_properties
        break

    use_spec = prefer_table if prefer_table is not None else bool(properties) and _TABLE_OR_SPEC_RE.search(query) is not None
    if use_spec and not properties:
        summary_text = _summarize_chunks([normalized_chunks[source_chunk_index]])
        properties = [SpecProperty(key=_derive_spec_title(query), value=summary_text)]
    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        chunk_index=source_chunk_index,
    )

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

        resolved_document_id = normalized_chunks[source_chunk_index].get("document_id") if normalized_chunks else None
        if resolved_document_id and (resolved_page or resolved_highlights):
            _ensure_evidence_relation(
                ctx, spec.id, resolved_document_id,
                page=resolved_page or 0,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )

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

    # Create up to MAX_FACTS fact nodes from the retrieved chunks (deduplicated by leading content)
    MAX_FACTS = 4
    created_facts: list[CanvasNode] = []
    seen_prefixes: set[str] = set()

    for fact_chunk in normalized_chunks[:MAX_FACTS * 2]:
        if len(created_facts) >= MAX_FACTS:
            break
        raw = str(fact_chunk.get("content") or "")
        fact_text = _clean_text_value(raw)
        if not fact_text:
            continue
        # Deduplicate by first 30 words
        prefix = " ".join(fact_text.lower().split()[:30])
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)

        if len(fact_text) > 800:
            fact_text = fact_text[:797] + "..."

        fact = CanvasNode(node_type="fact", text=fact_text, status="found")
        _mark_node_for_run(fact, ctx)
        ctx.deps.state.nodes.append(fact)
        _ensure_relation(ctx, topic.id, fact.id)

        doc_id = fact_chunk.get("document_id")
        page = _select_page(fact_chunk)
        if doc_id and page:
            _ensure_evidence_relation(
                ctx, fact.id, doc_id,
                page=page,
                bbox=_select_bbox(fact_chunk),
                highlights=_select_highlights(fact_chunk),
            )
        created_facts.append(fact)

    if not created_facts:
        # Fallback: use the source chunk directly
        fact_chunk = normalized_chunks[source_chunk_index] if normalized_chunks else {}
        fact_text = _summarize_chunks([fact_chunk] if fact_chunk else normalized_chunks)
        fact = CanvasNode(node_type="fact", text=fact_text, status="found")
        _mark_node_for_run(fact, ctx)
        ctx.deps.state.nodes.append(fact)
        _ensure_relation(ctx, topic.id, fact.id)
        created_facts.append(fact)

    first_fact = created_facts[0]
    summary = first_fact.text or ""
    if resolved_filename:
        summary = f"{summary} Source: {resolved_filename}."
    result = _snapshot(ctx)
    result.return_value = {
        "summary": summary,
        "topic_id": topic.id,
        "node_id": first_fact.id,
        "found": True,
        "format": "fact",
        "fact_count": len(created_facts),
    }
    return result


async def compare_documents(
    ctx: RunContext[AgentDeps],
    query: str,
    top_k: int = 5,
) -> ToolReturn:
    """Compare two documents side by side and materialize a comparison table on the canvas."""
    from src.knowledge_base.service import get_document_service

    service = await get_document_service()
    documents = await service.list_documents()
    selected_docs = _pick_comparison_documents(query.lower(), documents)

    if len(selected_docs) < 2:
        topic = CanvasNode(node_type="topic", title="Document Comparison", status="not_found")
        _mark_node_for_run(topic, ctx)
        ctx.deps.state.nodes.append(topic)
        fact = CanvasNode(
            node_type="fact",
            text="I need two processed documents in the knowledge base to compare them.",
            status="not_found",
        )
        _mark_node_for_run(fact, ctx)
        ctx.deps.state.nodes.append(fact)
        _ensure_relation(ctx, topic.id, fact.id)
        result = _snapshot(ctx)
        result.return_value = {
            "summary": "I need two processed documents in the knowledge base before I can build a comparison.",
            "found": False,
        }
        return result

    left_doc, right_doc = selected_docs[:2]
    left_chunks = await service.search(query=query, top_k=top_k, document_id=left_doc.get("document_id"))
    right_chunks = await service.search(query=query, top_k=top_k, document_id=right_doc.get("document_id"))

    left_normalized = []
    for chunk in left_chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        left_normalized.append(normalized)

    right_normalized = []
    for chunk in right_chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        right_normalized.append(normalized)

    left_index, left_properties = _extract_doc_properties(left_normalized, query)
    right_index, right_properties = _extract_doc_properties(right_normalized, query)

    if not left_properties and left_normalized:
        left_properties = [SpecProperty(key=_doc_label(left_doc.get("filename")), value=_summarize_chunks([left_normalized[left_index]]))]
    if not right_properties and right_normalized:
        right_properties = [SpecProperty(key=_doc_label(right_doc.get("filename")), value=_summarize_chunks([right_normalized[right_index]]))]

    comparison_rows = _build_comparison_properties(
        _doc_label(left_doc.get("filename")),
        _doc_label(right_doc.get("filename")),
        left_properties,
        right_properties,
    )

    topic = CanvasNode(
        node_type="topic",
        title=f"{_doc_label(left_doc.get('filename'))} vs {_doc_label(right_doc.get('filename'))}",
        status="found" if comparison_rows else "not_found",
    )
    _mark_node_for_run(topic, ctx)
    ctx.deps.state.nodes.append(topic)

    spec = CanvasNode(
        node_type="spec",
        spec_title="Comparison",
        properties=comparison_rows,
        status="found" if comparison_rows else "not_found",
    )
    _mark_node_for_run(spec, ctx)
    ctx.deps.state.nodes.append(spec)
    _ensure_relation(ctx, topic.id, spec.id)

    if left_normalized:
        _remember_search_results(ctx, left_normalized)
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(ctx=ctx, chunk_index=left_index)
        left_document_id = left_normalized[left_index].get("document_id") if left_normalized else None
        if left_document_id and (resolved_page or resolved_highlights):
            _ensure_evidence_relation(
                ctx, spec.id, left_document_id,
                page=resolved_page or 0,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )

    if right_normalized:
        _remember_search_results(ctx, right_normalized)
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(ctx=ctx, chunk_index=right_index)
        right_document_id = right_normalized[right_index].get("document_id") if right_normalized else None
        if right_document_id and (resolved_page or resolved_highlights):
            _ensure_evidence_relation(
                ctx, spec.id, right_document_id,
                page=resolved_page or 0,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )

    same_count = sum(1 for row in comparison_rows if row.comparison_status == "same")
    different_count = sum(1 for row in comparison_rows if row.comparison_status == "different")
    missing_count = sum(1 for row in comparison_rows if row.comparison_status == "missing")
    summary = (
        f"Compared {_doc_label(left_doc.get('filename'))} and {_doc_label(right_doc.get('filename'))}: "
        f"{same_count} same, {different_count} different, {missing_count} missing."
    )

    result = _snapshot(ctx)
    result.return_value = {
        "summary": summary,
        "topic_id": topic.id,
        "node_id": spec.id,
        "found": bool(comparison_rows),
        "format": "comparison",
    }
    return result
