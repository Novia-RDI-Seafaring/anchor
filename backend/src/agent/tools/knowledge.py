import re
from pathlib import Path
from urllib.parse import urlencode

from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from src.core.config import get_settings
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
    _MODEL_CODE_RE,
    _select_page,
    _select_bbox,
    _select_highlights,
    _clean_text_value,
    _find_node_by_title,
    _select_relevant_properties,
    _is_section_table_query,
    _query_requests_multiple_property_groups,
)
from . import vision

_COMPARISON_QUERY_RE = re.compile(r"\b(compare|comparison|different|difference|diff|vs\.?|versus)\b", re.IGNORECASE)
_BROAD_FACT_QUERY_RE = re.compile(
    r"\b(overview|summar(?:y|ize)|benefits?|features?|capabilities|advantages|steps?|procedure|process|modes?|how does|how do|how it works|explain)\b",
    re.IGNORECASE,
)


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
    if _is_section_table_query(query) or _query_requests_multiple_property_groups(query):
        aggregate_index = 0
        aggregate_properties: list[SpecProperty] = []
        seen: set[tuple[str, str, str]] = set()
        for index, chunk in enumerate(chunks):
            chunk_text = str(chunk.get("content") or "")
            properties = _extract_properties_from_text(chunk_text, query)
            if not properties:
                continue
            if not aggregate_properties:
                aggregate_index = index
            for prop in properties:
                signature = (
                    _normalize_property_key(prop.key),
                    prop.value.lower().strip(),
                    prop.unit.lower().strip(),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                aggregate_properties.append(prop)
        if aggregate_properties:
            return aggregate_index, aggregate_properties

    fallback_index = 0
    fallback_properties: list[SpecProperty] = []
    for index, chunk in enumerate(chunks):
        chunk_text = str(chunk.get("content") or "")
        properties = _extract_properties_from_text(chunk_text, query)
        if not properties:
            continue
        if not fallback_properties:
            fallback_index = index
            fallback_properties = properties
        matched_properties = _select_relevant_properties(properties, query)
        if matched_properties:
            return index, properties
    return fallback_index, fallback_properties


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


def _apply_property_reference(
    property_row: SpecProperty,
    *,
    filename: str | None,
    page: int | None,
    bbox: list[float],
    highlights: list,
) -> SpecProperty:
    property_row.ref_filename = filename or ""
    property_row.ref_page = page or 0
    property_row.ref_bbox = list(bbox or [])
    property_row.ref_highlights = list(highlights or [])
    return property_row


def _apply_property_references(
    properties: list[SpecProperty],
    *,
    filename: str | None,
    page: int | None,
    bbox: list[float],
    highlights: list,
) -> list[SpecProperty]:
    return [
        _apply_property_reference(
            prop,
            filename=filename,
            page=page,
            bbox=bbox,
            highlights=highlights,
        )
        for prop in properties
    ]

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
    document_ids_filter = doc_ids
    if document_id_filter is None and document_ids_filter and len(document_ids_filter) == 1:
        document_id_filter = document_ids_filter[0]
        document_ids_filter = None
    # Apply workspace filter when no specific doc is active/specified
    workspace_ids = getattr(ctx.deps.state, 'workspace_doc_ids', [])
    if document_id_filter is None and not document_ids_filter and workspace_ids:
        if len(workspace_ids) == 1:
            document_id_filter = workspace_ids[0]
        else:
            document_ids_filter = workspace_ids

    service = await get_document_service()
    chunks = await service.search(
        query=query,
        top_k=top_k,
        document_id=document_id_filter,
        document_ids=document_ids_filter,
    )

    if filename:
        normalized_filename = filename.strip().lower()
        filtered_by_filename = [
            chunk for chunk in chunks
            if str(chunk.get("filename") or "").strip().lower() == normalized_filename
        ]
        if filtered_by_filename:
            chunks = filtered_by_filename

    if document_ids_filter:
        doc_id_set = set(document_ids_filter)
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
        "retrieval_trace": [
            {
                "rank": chunk.get("provenance", {}).get("pipeline", {}).get("retrieval", {}).get("rank"),
                "filename": chunk.get("filename"),
                "page": chunk.get("page_no"),
                "score": chunk.get("similarity"),
            }
            for chunk in normalized_chunks
        ],
    }

async def resolve_technical_query(
    ctx: RunContext[AgentDeps],
    query: str,
    root_title: str | None = None,
    concept_title: str | None = None,
    concept_id: str | None = None,
    prefer_table: bool | None = None,
    top_k: int = 5,
) -> ToolReturn:
    """Search the KB, populate the canvas, and return a grounded summary.

    This is the primary tool for technical questions. It performs retrieval,
    creates the concept/topic/fact-or-spec nodes, emits a canvas snapshot, and
    returns a concise summary for the final chat response.

    concept_title: the high-level concept name (e.g. "A2UI")
    concept_id: if the agent already knows the concept node id
    root_title: title for the sub-topic aspect, e.g. 'Benefits', 'How it works' — NOT the document section title
    """
    from src.knowledge_base.service import get_document_service

    service = await get_document_service()
    active_document_id = ctx.deps.state.active_document_id
    active_document = None
    if active_document_id:
        active_document = await service.get_document(active_document_id)

    workspace_ids = getattr(ctx.deps.state, 'workspace_doc_ids', [])
    if active_document_id:
        chunks = await service.search(query=query, top_k=top_k, document_id=active_document_id)
    elif workspace_ids:
        chunks = await service.search(query=query, top_k=top_k, document_ids=workspace_ids)
    else:
        chunks = await service.search(query=query, top_k=top_k, document_id=None)
    normalized_chunks: list[dict] = []
    for chunk in chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        normalized_chunks.append(normalized)
    _remember_search_results(ctx, normalized_chunks)

    # Find or create concept node
    resolved_concept_id: str | None = concept_id
    if not resolved_concept_id and concept_title:
        existing = _find_node_by_title(ctx, concept_title, "concept")
        if existing:
            resolved_concept_id = existing.id
        else:
            concept_node = CanvasNode(node_type="concept", title=concept_title, status="found")
            _mark_node_for_run(concept_node, ctx)
            ctx.deps.state.nodes.append(concept_node)
            resolved_concept_id = concept_node.id
            # Adopt any standalone spec node created by resolve_simple_query with the same product name.
            # This unifies the canvas when a simple query is followed by a comprehensive one.
            _title_lower = concept_title.lower().strip()
            for _orphan in ctx.deps.state.nodes:
                if (
                    _orphan.node_type == "spec"
                    and (_orphan.spec_title or "").lower().strip() == _title_lower
                    and not any(r.to_id == _orphan.id for r in ctx.deps.state.relations)
                ):
                    _ensure_relation(ctx, resolved_concept_id, _orphan.id)

    requested_topic_title = root_title or _derive_topic_title(query)

    if not normalized_chunks:
        topic = CanvasNode(
            node_type="topic",
            title=requested_topic_title,
            status="not_found",
        )
        _mark_node_for_run(topic, ctx)
        ctx.deps.state.nodes.append(topic)
        if resolved_concept_id:
            _ensure_relation(ctx, resolved_concept_id, topic.id)
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
            "concept_id": resolved_concept_id,
            "found": False,
        }
        return result

    source_chunk_index, properties = _extract_doc_properties(normalized_chunks, query)

    matched_properties = _select_relevant_properties(properties, query) if properties else []
    fallback_answer_text: str | None = None
    query_model_match = _MODEL_CODE_RE.search(query)
    query_model = query_model_match.group(1).strip().lower() if query_model_match else ""

    if not properties:
        source_text = _clean_text_value(str(normalized_chunks[source_chunk_index].get("content") or ""))
        if len(source_text.split()) <= 8:
            for index, chunk in enumerate(normalized_chunks):
                candidate_text = _clean_text_value(str(chunk.get("content") or ""))
                if candidate_text.startswith("- ") or "\n- " in candidate_text or candidate_text.startswith("• ") or "\n• " in candidate_text:
                    source_chunk_index = index
                    fallback_answer_text = candidate_text
                    break

    model_only_match = bool(query_model and matched_properties and all(
        prop.key.strip().lower() == query_model for prop in matched_properties
    ))
    selected_chunk_text = _clean_text_value(str(normalized_chunks[source_chunk_index].get("content") or ""))
    is_list_like_chunk = bool(
        selected_chunk_text.startswith("- ")
        or selected_chunk_text.startswith("• ")
        or "\n- " in selected_chunk_text
        or "\n• " in selected_chunk_text
    )
    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        chunk_index=source_chunk_index,
    )

    if (
        not _BROAD_FACT_QUERY_RE.search(query)
        and (not matched_properties or model_only_match)
        and not is_list_like_chunk
        and resolved_filename
        and resolved_page
    ):
        source_text = _clean_text_value(str(normalized_chunks[source_chunk_index].get("content") or ""))
        if len(source_text.split()) > 24:
            settings = get_settings()
            screenshot_params: dict[str, str | int | float] = {
                "filename": resolved_filename,
                "page_no": resolved_page,
            }
            if len(resolved_bbox) == 4:
                screenshot_params.update(
                    {
                        "bbox_l": resolved_bbox[0],
                        "bbox_t": resolved_bbox[1],
                        "bbox_r": resolved_bbox[2],
                        "bbox_b": resolved_bbox[3],
                    }
                )
            image_url = f"http://127.0.0.1:{settings.port}/api/documents/pdf/screenshot?{urlencode(screenshot_params)}"
            vision_text = await vision.analyze_image_content(
                ctx,
                image_url,
                (
                    f"Extract only the minimal text needed to answer this question from the screenshot: {query}. "
                    "If the answer is a list, return the list items as bullets. "
                    "If the answer is a table row, return concise key-value text only. "
                    "If uncertain, say so."
                ),
            )
            if not vision_text.lower().startswith("image analysis failed:"):
                cleaned_vision_text = _clean_text_value(vision_text)
                vision_properties = _extract_properties_from_text(vision_text, query)
                vision_matched = _select_relevant_properties(vision_properties, query) if vision_properties else []
                if vision_matched:
                    properties = vision_properties
                    matched_properties = vision_matched
                elif cleaned_vision_text:
                    fallback_answer_text = cleaned_vision_text

    topic = None
    if not root_title and not _BROAD_FACT_QUERY_RE.search(query) and matched_properties:
        for node in ctx.deps.state.nodes:
            if node.node_type != "spec" or not node.properties:
                continue
            if not _select_relevant_properties(node.properties, query):
                continue
            parent_topic_relation = next(
                (
                    rel for rel in ctx.deps.state.relations
                    if rel.to_id == node.id
                    and any(candidate.id == rel.from_id and candidate.node_type == "topic" for candidate in ctx.deps.state.nodes)
                ),
                None,
            )
            if parent_topic_relation is None:
                continue
            topic = next(
                (candidate for candidate in ctx.deps.state.nodes if candidate.id == parent_topic_relation.from_id and candidate.node_type == "topic"),
                None,
            )
            if topic is not None:
                break

    if topic is None:
        existing_topic = _find_node_by_title(ctx, requested_topic_title, "topic")
        if existing_topic is not None:
            topic = existing_topic

    if topic is None:
        topic = CanvasNode(
            node_type="topic",
            title=requested_topic_title,
            status="found",
        )
        _mark_node_for_run(topic, ctx)
        ctx.deps.state.nodes.append(topic)
    else:
        _mark_node_for_run(topic, ctx)

    if resolved_concept_id:
        _ensure_relation(ctx, resolved_concept_id, topic.id)
    else:
        concept_relation = next((rel for rel in ctx.deps.state.relations if rel.to_id == topic.id), None)
        if concept_relation is not None:
            concept_node = next(
                (node for node in ctx.deps.state.nodes if node.id == concept_relation.from_id and node.node_type == "concept"),
                None,
            )
            if concept_node is not None:
                resolved_concept_id = concept_node.id

    use_spec = prefer_table if prefer_table is not None else bool(properties) and (
        len(matched_properties) > 1
        or len(properties) > 2
        or (len(properties) > 1 and _MODEL_CODE_RE.search(query) is not None)
    )
    if use_spec and not properties:
        summary_text = _summarize_chunks([normalized_chunks[source_chunk_index]])
        properties = [SpecProperty(key=_derive_spec_title(query), value=summary_text)]
    display_properties = matched_properties if use_spec and matched_properties else properties
    display_properties = _apply_property_references(
        display_properties,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )

    # If this topic already has exactly one fact/spec child, update it instead of appending.
    # New child is only created when the topic is truly empty or content needs to be split.
    _direct_child_ids = {r.to_id for r in ctx.deps.state.relations if r.from_id == topic.id}
    _existing_children = [
        n for n in ctx.deps.state.nodes
        if n.id in _direct_child_ids and n.node_type in ("fact", "spec")
    ]
    if len(_existing_children) == 1:
        _existing = _existing_children[0]
        _resolved_doc_id = normalized_chunks[source_chunk_index].get("document_id") if normalized_chunks else None

        if use_spec and _existing.node_type == "spec" and display_properties:
            # Merge new properties — skip keys already present
            _existing_keys = {_normalize_property_key(p.key) for p in (_existing.properties or [])}
            _new_props = [p for p in display_properties if _normalize_property_key(p.key) not in _existing_keys]
            if _new_props:
                _existing.properties = list(_existing.properties or []) + _new_props
            _mark_node_for_run(_existing, ctx)
            if _resolved_doc_id and (resolved_page or resolved_highlights):
                _ensure_evidence_relation(
                    ctx, _existing.id, _resolved_doc_id,
                    page=resolved_page or 0, bbox=resolved_bbox, highlights=resolved_highlights,
                )
            result = _snapshot(ctx)
            result.return_value = {
                "summary": _summarize_properties(_existing.properties or [], resolved_filename),
                "topic_id": topic.id, "node_id": _existing.id,
                "concept_id": resolved_concept_id, "found": True, "format": "spec",
            }
            return result

        if not use_spec and _existing.node_type == "fact" and not _BROAD_FACT_QUERY_RE.search(query):
            # Update fact text if new content is richer
            _new_text = (
                _summarize_properties(matched_properties).rstrip(".")
                if matched_properties
                else (fallback_answer_text or _summarize_chunks([normalized_chunks[source_chunk_index]]))
            )
            if _new_text and len(_new_text) > len(_existing.text or ""):
                _existing.text = _new_text
            _mark_node_for_run(_existing, ctx)
            _fact_chunk = normalized_chunks[source_chunk_index]
            _page = _select_page(_fact_chunk)
            if _resolved_doc_id and _page:
                _ensure_evidence_relation(
                    ctx, _existing.id, _resolved_doc_id,
                    page=_page, bbox=_select_bbox(_fact_chunk), highlights=_select_highlights(_fact_chunk),
                )
            _summary = _existing.text or ""
            if resolved_filename:
                _summary = f"{_summary} Source: {resolved_filename}."
            result = _snapshot(ctx)
            result.return_value = {
                "summary": _summary, "topic_id": topic.id, "node_id": _existing.id,
                "concept_id": resolved_concept_id, "found": True, "format": "fact", "fact_count": 1,
            }
            return result

    if use_spec:
        spec = CanvasNode(
            node_type="spec",
            spec_title=_derive_spec_title(query),
            properties=display_properties,
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

        summary = _summarize_properties(display_properties, resolved_filename)
        result = _snapshot(ctx)
        result.return_value = {
            "summary": summary,
            "topic_id": topic.id,
            "node_id": spec.id,
            "concept_id": resolved_concept_id,
            "found": True,
            "format": "spec",
        }
        return result

    if not _BROAD_FACT_QUERY_RE.search(query):
        fact_chunk = normalized_chunks[source_chunk_index]
        fact_text = (
            _summarize_properties(matched_properties).rstrip(".")
            if matched_properties
            else (fallback_answer_text or _summarize_chunks([fact_chunk]))
        )
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

        summary = fact.text or ""
        fact_filename = fact_chunk.get("filename") or resolved_filename
        if fact_filename:
            summary = f"{summary} Source: {fact_filename}."
        result = _snapshot(ctx)
        result.return_value = {
            "summary": summary,
            "topic_id": topic.id,
            "node_id": fact.id,
            "concept_id": resolved_concept_id,
            "found": True,
            "format": "fact",
            "fact_count": 1,
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
        "concept_id": resolved_concept_id,
        "found": True,
        "format": "fact",
        "fact_count": len(created_facts),
    }
    return result


_SIMPLE_QUERY_REFACTOR_THRESHOLD = 5


async def resolve_simple_query(
    ctx: RunContext[AgentDeps],
    query: str,
    product_name: str,
    property_key: str,
    top_k: int = 5,
) -> ToolReturn:
    """Answer a single-value factual question and accumulate the result on the canvas.

    Instead of creating a concept → topic → spec chain, this tool maintains ONE spec node
    per product that grows with each simple question. When the user has asked 5+ properties,
    the response signals it's time to reorganize.

    product_name: the product/subject being asked about (e.g. "Alfa Laval LKH 10")
    property_key: the specific property being requested (e.g. "Max Inlet Pressure")
    """
    from src.knowledge_base.service import get_document_service

    service = await get_document_service()
    active_document_id = ctx.deps.state.active_document_id
    workspace_ids = getattr(ctx.deps.state, "workspace_doc_ids", [])
    if active_document_id:
        chunks = await service.search(query=query, top_k=top_k, document_id=active_document_id)
    elif workspace_ids:
        chunks = await service.search(query=query, top_k=top_k, document_ids=workspace_ids)
    else:
        chunks = await service.search(query=query, top_k=top_k, document_id=None)

    normalized_chunks: list[dict] = []
    for chunk in chunks[:top_k]:
        normalized = dict(chunk)
        normalized["page_no"] = _select_page(normalized)
        normalized["bbox"] = _select_bbox(normalized)
        normalized["highlights"] = _select_highlights(normalized)
        normalized_chunks.append(normalized)
    _remember_search_results(ctx, normalized_chunks)

    # Check if a concept node already exists (created by a prior comprehensive query).
    # If so, attach the spec to it. If not, the spec stands alone — no duplicate concept card.
    existing_concept = _find_node_by_title(ctx, product_name, "concept")

    if not normalized_chunks:
        not_found_spec = CanvasNode(
            node_type="spec",
            spec_title=product_name,
            properties=[SpecProperty(key=property_key, value="Not found in knowledge base")],
            status="not_found",
        )
        _mark_node_for_run(not_found_spec, ctx)
        ctx.deps.state.nodes.append(not_found_spec)
        if existing_concept:
            _ensure_relation(ctx, existing_concept.id, not_found_spec.id)
        result = _snapshot(ctx)
        result.return_value = {
            "answer": f"No information found for '{property_key}' in the loaded knowledge base.",
            "spec_node_id": not_found_spec.id,
            "concept_id": existing_concept.id if existing_concept else None,
            "property_count": 1,
            "suggest_refactor": False,
            "found": False,
        }
        return result

    # Extract the property value from search results
    source_chunk_index, properties = _extract_doc_properties(normalized_chunks, query)
    matched_properties = _select_relevant_properties(properties, query) if properties else []

    # Vision fallback when text extraction gives nothing useful
    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx, chunk_index=source_chunk_index,
    )
    if not matched_properties and not properties and resolved_filename and resolved_page:
        source_text = _clean_text_value(str(normalized_chunks[source_chunk_index].get("content") or ""))
        if len(source_text.split()) > 12:
            settings = get_settings()
            screenshot_params: dict[str, str | int | float] = {
                "filename": resolved_filename,
                "page_no": resolved_page,
            }
            if len(resolved_bbox) == 4:
                screenshot_params.update({
                    "bbox_l": resolved_bbox[0], "bbox_t": resolved_bbox[1],
                    "bbox_r": resolved_bbox[2], "bbox_b": resolved_bbox[3],
                })
            image_url = (
                f"http://127.0.0.1:{settings.port}/api/documents/pdf/screenshot"
                f"?{urlencode(screenshot_params)}"
            )
            vision_text = await vision.analyze_image_content(
                ctx, image_url,
                f"Extract only the minimal text needed to answer: {query}. "
                "Return a concise key-value or short phrase only.",
            )
            if not vision_text.lower().startswith("image analysis failed:"):
                vision_properties = _extract_properties_from_text(vision_text, query)
                vision_matched = _select_relevant_properties(vision_properties, query) if vision_properties else []
                if vision_matched:
                    properties = vision_properties
                    matched_properties = vision_matched
                elif _clean_text_value(vision_text):
                    properties = [SpecProperty(key=property_key, value=_clean_text_value(vision_text))]
                    matched_properties = properties

    # Build the single SpecProperty for this question
    if matched_properties:
        best = matched_properties[0]
        new_prop = SpecProperty(key=property_key, value=best.value, unit=best.unit)
    elif properties:
        best = properties[0]
        new_prop = SpecProperty(key=property_key, value=best.value, unit=best.unit)
    else:
        fallback_text = _clean_text_value(str(normalized_chunks[source_chunk_index].get("content") or ""))
        new_prop = SpecProperty(key=property_key, value=fallback_text[:120] if fallback_text else "See source")

    new_prop = _apply_property_reference(
        new_prop,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )

    # Find existing accumulator: any spec node whose spec_title matches the product name.
    # This works whether the spec was previously created standalone or under a concept.
    accumulator = next(
        (n for n in ctx.deps.state.nodes
         if n.node_type == "spec" and (n.spec_title or "").lower().strip() == product_name.lower().strip()),
        None,
    )

    if accumulator is not None:
        # Append to existing accumulator — skip if same key already present
        existing_keys = {p.key.lower().strip() for p in (accumulator.properties or [])}
        if new_prop.key.lower().strip() not in existing_keys:
            accumulator.properties = list(accumulator.properties or []) + [new_prop]
        _mark_node_for_run(accumulator, ctx)
        spec_node_id = accumulator.id
    else:
        # Create new standalone spec node (no concept node — avoids duplicate product title on canvas)
        accumulator = CanvasNode(
            node_type="spec",
            spec_title=product_name,
            properties=[new_prop],
            status="found",
        )
        _mark_node_for_run(accumulator, ctx)
        ctx.deps.state.nodes.append(accumulator)
        # Connect to existing concept if one was created by a prior comprehensive query
        if existing_concept:
            _ensure_relation(ctx, existing_concept.id, accumulator.id)
        spec_node_id = accumulator.id

    # Update evidence to latest source
    resolved_doc_id = normalized_chunks[source_chunk_index].get("document_id") if normalized_chunks else None
    if resolved_doc_id and (resolved_page or resolved_highlights):
        _ensure_evidence_relation(
            ctx, spec_node_id, resolved_doc_id,
            page=resolved_page or 0,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )

    property_count = len(accumulator.properties or [])
    answer = f"{new_prop.key}: {new_prop.value} {new_prop.unit}".strip().rstrip(":")

    result = _snapshot(ctx)
    result.return_value = {
        "answer": answer,
        "spec_node_id": spec_node_id,
        "concept_id": existing_concept.id if existing_concept else None,
        "property_count": property_count,
        "suggest_refactor": property_count >= _SIMPLE_QUERY_REFACTOR_THRESHOLD,
        "found": True,
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
