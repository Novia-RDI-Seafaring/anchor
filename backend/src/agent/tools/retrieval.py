"""Knowledge base retrieval tools for querying the vector database."""
import time
from typing import Optional, Any

from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from pydantic_ai._run_context import RunContext
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai import ToolReturn

from src.core.logging import log_rag_query, log_agent_tool_call, log_error
from evals.trace_logger import log_event
from evals.token_utils import estimate_tokens, estimate_tokens_bulk

from ..deps import AgentDeps
from src.shared.ui_components import determine_component_type


async def search_knowledge_base(
  ctx: RunContext[AgentDeps], 
  query: str,
  filename: Optional[str] = None,
  doc_ids: Optional[list[str]] = None,
  top_k: int = 5
) -> dict[str, list]:
  """
  Query the vector database for relevant context via KETJU.
  """
  start_time = time.time()
  log_agent_tool_call("search_knowledge_base", {"query": query, "top_k": top_k})
  
  try:
    from src.core.context import get_active_document_id
    rag = ctx.deps.doc_service.rag_service
    #active_doc_id = get_active_document_id()
    
    # Query using KETJU's RAG (SimpleLlamaIndexQueryHandler)
    # We use search() if we want raw chunks, or query() if we want a response.
    # The tool returns chunks for the agent to reason over.
    kwargs = {}
    if filename is not None:
      kwargs["filename"] = filename
    if doc_ids is not None:
      kwargs["doc_ids"] = doc_ids
    if top_k is not None:
      kwargs["top_k"] = top_k
    results = rag.query(query, **kwargs)
    
    # KETJU search results are LlamaIndex NodeWithScore objects if using SimpleLlamaIndexQueryHandler.search
    # Wait, let's check what SimpleLlamaIndexQueryHandler.search returns.
    # Actually, we can just use the index directly or the query handler.
    from devtools import debug
    debug(results)
    return results

    chunks = results.source_nodes
    
    sources = list(set(c["filename"] for c in chunks))
    should_render = len(chunks) > 0
    suggested_component = determine_component_type(query, chunks).value if should_render else "list"
    note = f"Internal: You must now call render_component('{suggested_component}', data=...) to display these results."
    
    ctx.deps.state.current_sources = sources
    ctx.deps.state.last_chunks = chunks


    duration_ms = (time.time() - start_time) * 1000
    log_rag_query(query, top_k, len(chunks), duration_ms, context=chunks)
    log_event({
        "type": "retrieval",
        "query_len": len(query),
        "query_tokens_est": estimate_tokens(query),
        "latency_ms": duration_ms,
    })
    
    return ToolReturn(
        return_value={
            "chunks": chunks, 
            "sources": sources,
            "should_render": should_render,
            "suggested_component": suggested_component,
            "_note": note
        },
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)]
    )
    
  except Exception as e:
    log_error("Error in search_knowledge_base", e)
    return ToolReturn(return_value={"chunks": [], "sources": [], "error": str(e)}, metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)])


async def get_database_status(ctx: RunContext[AgentDeps]) -> StateSnapshotEvent:
  """Check status via KETJU."""
  log_agent_tool_call("get_database_status", {})
  try:
    from src.knowledge_base.ketju_integration import get_ketju_rag
    rag = get_ketju_rag()
    # If this doesn't raise, we're likely connected
    status = "connected"
    ctx.deps.state.vector_db_status = status
    return ToolReturn(return_value={"status": status}, metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)])
  except Exception as e:
    return ToolReturn(return_value={"status": "error", "message": str(e)}, metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=ctx.deps.state)])


async def list_documents(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
  """List documents via KETJU or ANCHOR service (shared DB)."""
  log_agent_tool_call("list_documents", {})
  try:
    # We still use the DocumentService for listing as it handles the ANCHOR-specific documents table
    from src.knowledge_base.service import get_document_service
    service = await get_document_service()
    documents = await service.list_documents()
    return {"documents": documents, "should_render": True, "suggested_component": "list"}
  except Exception as e:
    return {"error": str(e)}


async def list_document_toc(
  ctx: RunContext[AgentDeps],
  document_id: Optional[str] = None
) -> dict[str, Any]:
  """Retrieve TOC via KETJU storage."""
  log_agent_tool_call("list_document_toc", {"document_id": document_id})
  try:
    from src.knowledge_base.ketju_integration import get_ketju_rag
    from src.core.context import get_active_document_id
    
    doc_id = document_id or get_active_document_id()
    if not doc_id:
        return {"error": "No document ID provided."}
    
    rag = get_ketju_rag()
    toc = rag.storage_backend.get_toc(doc_id)
    
    # Get filename from common source (ANCHOR documents table for now)
    from src.knowledge_base.vector_store import get_vector_store
    vs = await get_vector_store()
    doc_info = await vs.get_document(doc_id)
    
    return {
        "toc": toc or [],
        "filename": doc_info.get("filename") if doc_info else "Unknown",
        "document_id": doc_id,
        "should_render": len(toc) > 0,
        "suggested_component": "list"
    }
  except Exception as e:
    return {"error": str(e)}


async def get_section_content(
  ctx: RunContext[AgentDeps],
  section_name: str,
  document_id: Optional[str] = None
) -> dict[str, Any]:
  """Retrieve section content via KETJU storage."""
  log_agent_tool_call("get_section_content", {"section_name": section_name, "document_id": document_id})
  try:
    from src.knowledge_base.ketju_integration import get_ketju_rag
    from src.core.context import get_active_document_id
    
    doc_id = document_id or get_active_document_id()
    if not doc_id:
        return {"error": "No document ID provided."}
    
    rag = get_ketju_rag()
    chunks = rag.storage_backend.get_chunks_by_section(doc_id, section_name)
    
    if not chunks:
        return {"error": f"No content found for section '{section_name}'."}
    
    full_content = "\n\n".join([c["content"] for c in chunks])
    if len(full_content) > 15000:
        full_content = full_content[:15000] + "... [Content truncated]"
    
    return {
        "section_name": section_name,
        "content": full_content,
        "chunk_count": len(chunks),
        "document_id": doc_id
    }
  except Exception as e:
    return {"error": str(e)}
