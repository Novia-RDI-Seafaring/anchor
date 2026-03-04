"""Knowledge base retrieval tools for querying the vector database."""
import time
from typing import Optional, Any

from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from pydantic_ai._run_context import RunContext
from pydantic_ai import ToolReturn

from src.core.logging import log_rag_query, log_agent_tool_call, log_error
from evals.trace_logger import log_event
from evals.token_utils import estimate_tokens
from src.core.config import get_settings

from ..deps import AgentDeps
from src.shared.ui_components import determine_component_type



async def search_knowledge_base(
  ctx: RunContext[AgentDeps],
  query: str,
  filename: Optional[str] = None,
  doc_ids: Optional[list[str]] = None,
  top_k: int = 5,
) -> dict[str, list]:
  """Query the vector database for relevant context via KETJU."""
  start_time = time.time()
  log_agent_tool_call("search_knowledge_base", {
      "query": query,
      "top_k": top_k,
      "filename": filename,
      "doc_ids": doc_ids,
  })

  try:
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
      by_filename = [
          chunk for chunk in chunks
          if str(chunk.get("filename") or "").strip().lower() == normalized_filename
      ]
      if by_filename:
        chunks = by_filename

    if doc_ids:
      doc_id_set = set(doc_ids)
      by_doc_ids = [chunk for chunk in chunks if chunk.get("document_id") in doc_id_set]
      if by_doc_ids:
        chunks = by_doc_ids

    chunks = chunks[:top_k]

    sources = list(set(c["filename"] for c in chunks))
    should_render = len(chunks) > 0
    suggested_component = determine_component_type(query, chunks).value if should_render else "list"
    note = f"Internal: You must now call render_component('{suggested_component}', data=...) to display these results."

    first_provenance = (chunks[0].get('provenance') if chunks else {}) or {}
    retrieval_meta = {
        'retrieval_id': first_provenance.get('pipeline', {}).get('retrieval', {}).get('retrieval_id'),
        'trace_id': first_provenance.get('trace', {}).get('trace_id'),
        'query': query,
        'top_k': top_k,
        'returned_k': len(chunks),
        'document_filter': document_id_filter,
        'doc_ids': doc_ids,
        'filename_filter': filename,
        'collection': first_provenance.get('pipeline', {}).get('index', {}).get('collection'),
    }
    ctx.deps.state.current_sources = sources
    ctx.deps.state.last_chunks = chunks
    ctx.deps.state.last_retrieval_meta = retrieval_meta

    duration_ms = (time.time() - start_time) * 1000
    log_rag_query(query, top_k, len(chunks), duration_ms, context=chunks)
    log_event({
        "type": "retrieval",
        "query_len": len(query),
        "query_tokens_est": estimate_tokens(query),
        "latency_ms": duration_ms,
    })
    log_event({
        'type': 'retrieval_lineage',
        'retrieval_id': retrieval_meta.get('retrieval_id'),
        'trace_id': retrieval_meta.get('trace_id'),
        'document_filter': document_id_filter,
        'doc_ids': doc_ids,
        'filename_filter': filename,
    })

    return ToolReturn(
        return_value={
            "chunks": chunks,
            "sources": sources,
            "should_render": should_render,
            "suggested_component": suggested_component,
            "_note": note,
        },
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)],
    )

  except Exception as e:
    log_error("Error in search_knowledge_base", e)
    return ToolReturn(
        return_value={"chunks": [], "sources": [], "error": str(e)},
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)],
    )


async def get_database_status(ctx: RunContext[AgentDeps]) -> StateSnapshotEvent:
  """Check status via KETJU."""
  log_agent_tool_call("get_database_status", {})
  try:
    status = "connected"
    ctx.deps.state.vector_db_status = status
    return ToolReturn(
        return_value={"status": status},
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)],
    )
  except Exception as e:
    return ToolReturn(
        return_value={"status": "error", "message": str(e)},
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)],
    )


async def list_documents(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
  """List documents via KETJU or ANCHOR service (shared DB)."""
  log_agent_tool_call("list_documents", {})
  try:
    from src.knowledge_base.service import get_document_service2

    service = await get_document_service()
    documents = await service.list_documents()
    return {"documents": documents, "should_render": True, "suggested_component": "list"}
  except Exception as e:
    return {"error": str(e)}


async def list_document_toc(
  ctx: RunContext[AgentDeps],
  document_id: Optional[str] = None,
) -> dict[str, Any]:
  """Retrieve TOC via KETJU storage."""
  log_agent_tool_call("list_document_toc", {"document_id": document_id})
  try:
    raise NotImplementedError("list_document_toc is not implemented")
    from src.core.context import get_active_document_id

    doc_id = document_id or get_active_document_id()
    if not doc_id:
        return {"error": "No document ID provided."}

    rag = _get_ketju_rag()
    toc = rag.storage_backend.get_toc(doc_id)

    from src.knowledge_base.vector_store import get_vector_store

    vs = await get_vector_store()
    doc_info = await vs.get_document(doc_id)

    return {
        "toc": toc or [],
        "filename": doc_info.get("filename") if doc_info else "Unknown",
        "document_id": doc_id,
        "should_render": len(toc) > 0,
        "suggested_component": "list",
    }
  except Exception as e:
    return {"error": str(e)}


async def get_section_content(
  ctx: RunContext[AgentDeps],
  section_name: Optional[str] = None,
  section_id: Optional[str] = None,
  document_id: Optional[str] = None,
) -> dict[str, Any]:
  """Retrieve section content via KETJU storage."""
  resolved_section_name = section_name or section_id
  log_agent_tool_call("get_section_content", {
      "section_name": section_name,
      "section_id": section_id,
      "resolved_section_name": resolved_section_name,
      "document_id": document_id,
  })
  try:
    raise NotImplementedError("get_section_content is not implemented")
    from src.core.context import get_active_document_id
    from src.knowledge_base.service import get_document_service

    if not resolved_section_name:
        return {"error": "No section name provided."}

    doc_id = document_id or get_active_document_id()
    if not doc_id and ctx.deps.state.last_chunks:
        doc_id = ctx.deps.state.last_chunks[0].get("document_id")

    if not doc_id:
        return {"error": "No document ID provided."}

    target_filename = None
    if ctx.deps.state.last_chunks:
        for chunk in ctx.deps.state.last_chunks:
            if chunk.get("document_id") == doc_id and chunk.get("filename"):
                target_filename = chunk.get("filename")
                break
        if not target_filename:
            target_filename = ctx.deps.state.last_chunks[0].get("filename")

    rag = _get_ketju_rag()
    chunks = []
    try:
        chunks = rag.storage_backend.get_chunks_by_section(doc_id, resolved_section_name)
    except Exception:
        chunks = []

    if not chunks:
        service = await get_document_service()
        fallback_query_parts = [resolved_section_name, "section content"]
        if target_filename:
            fallback_query_parts.append(str(target_filename))

        candidate_chunks = await service.search(
            query=" ".join(fallback_query_parts),
            top_k=40,
            document_id=None,
        )

        scoped_chunks = candidate_chunks
        if doc_id:
            by_document = [chunk for chunk in scoped_chunks if chunk.get("document_id") == doc_id]
            if by_document:
                scoped_chunks = by_document

        if target_filename:
            normalized_filename = str(target_filename).strip().lower()
            by_filename = [
                chunk
                for chunk in scoped_chunks
                if str(chunk.get("filename") or "").strip().lower() == normalized_filename
            ]
            if by_filename:
                scoped_chunks = by_filename

        normalized_section = resolved_section_name.strip().lower()
        filtered_chunks = []
        for chunk in scoped_chunks:
            section_path = (
                chunk.get("section_path")
                or chunk.get("metadata", {}).get("headings")
                or []
            )
            section_values = [str(value).strip().lower() for value in section_path if value]
            if normalized_section in section_values:
                filtered_chunks.append(chunk)

        chunks = filtered_chunks or scoped_chunks

    if not chunks:
        return {"error": f"No content found for section '{resolved_section_name}'."}

    full_content = "\n\n".join([(c.get("content") or c.get("text") or "") for c in chunks])
    if len(full_content) > 15000:
        full_content = full_content[:15000] + "... [Content truncated]"

    return {
        "section_name": resolved_section_name,
        "content": full_content,
        "chunk_count": len(chunks),
        "document_id": doc_id,
    }
  except Exception as e:
    return {"error": str(e)}
