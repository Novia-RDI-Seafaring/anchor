from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, SpecProperty
from ..helpers import (
    _snapshot,
    _mark_node_for_run,
    _ensure_relation,
    _remember_search_results,
    _select_best_chunk_index,
    _resolve_source_details,
    _get_or_create_source_node,
    _summarize_chunks,
    _summarize_properties,
    _derive_topic_title,
    _derive_spec_title,
    _extract_properties_from_text,
    _TABLE_OR_SPEC_RE,
    _select_page,
    _select_bbox,
    _select_highlights
)

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

    source_chunk_index = _select_best_chunk_index(
        normalized_chunks,
        properties if use_spec else _summarize_chunks(normalized_chunks),
    )
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
