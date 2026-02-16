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

from ..state import RAGState
from src.shared.ui_components import determine_component_type


async def search_knowledge_base(
  ctx: RunContext[StateDeps[RAGState]], 
  query: str,
  top_k: int = 5
) -> dict[str, list]:
  """
  Query the vector database for relevant context.
  Uses the active document filter if set by the user.
  
  Args:
    query: The search query
    top_k: Number of results to retrieve (default: 5)
  
  Returns:
    Dictionary with 'chunks', 'sources', and rendering hints:
    - should_render: bool
    - suggested_component: str
    - _note: Internal instruction
    - chunks: List of content chunks
    - sources: List of source filenames
  """
  start_time = time.time()
  
  # Log tool call
  log_agent_tool_call("search_knowledge_base", {"query": query, "top_k": top_k})
  
  try:
    # Import here to avoid circular imports
    from src.knowledge_base.service import get_document_service
    from src.core.context import get_active_document_id
    
    # Get active document filter
    active_doc_id = get_active_document_id()
    
    # Query the vector store with optional document filter
    service = await get_document_service()
    results = await service.search(query, top_k=top_k, document_id=active_doc_id)
    
    # Extract chunks and sources with rich data
    chunks = []
    for r in results:
        chunks.append({
            "id": r.get("id"),  # Include chunk ID for page image queries
            "content": r["content"],
            "filename": r["filename"],
            "document_id": r.get("document_id"),  # Include document_id for page preview
            "similarity": r.get("similarity", 0.0),
            "metadata": r.get("metadata", {})
        })
    
    sources = list(set(r["filename"] for r in results))
    
    # Determine the best component type for these results
    should_render = len(chunks) > 0
    suggested_component = determine_component_type(query, chunks).value if should_render else "list"
    
    # Internal note to guide the model (not for user display)
    note = f"Internal: You must now call render_component('{suggested_component}', data=...) to display these results."
    
    # Update state with sources and chunks
    ctx.deps.state.current_sources = sources
    ctx.deps.state.last_chunks = chunks
    
    # Log query performance
    duration_ms = (time.time() - start_time) * 1000
    log_rag_query(query, top_k, len(chunks), duration_ms, context=chunks)
    log_event({
        "type": "retrieval",
        "query_len": len(query),
        "query_tokens_est": estimate_tokens(query),
        "top_k": top_k,
        "result_count": len(chunks),
        "total_chunk_chars": sum(len(c.get("content", "")) for c in chunks),
        "total_chunk_tokens": estimate_tokens_bulk((c.get("content", "") for c in chunks)),
        "doc_ids": list({c.get("document_id") for c in chunks if c.get("document_id")}),
        "latency_ms": duration_ms,
    })
    log_event({
        "type": "state",
        "conversation_len": len(ctx.deps.state.conversation_history),
        "last_chunks_len": len(ctx.deps.state.last_chunks),
        "ui_components_len": len(ctx.deps.state.active_ui_components),
    })
    
    # Return with state update
    return ToolReturn(
        return_value={
            "chunks": chunks, 
            "sources": sources,
            "should_render": should_render,
            "suggested_component": suggested_component,
            "_note": note
        },
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )
    
  except Exception as e:
    import traceback
    error_trace = traceback.format_exc()
    log_error("Error in search_knowledge_base", e, {
        "query": query, 
        "top_k": top_k,
        "traceback": error_trace
    })
    # Return empty results on error with consistent type
    return ToolReturn(
        return_value={"chunks": [], "sources": [], "error": str(e)},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )


async def get_database_status(ctx: RunContext[StateDeps[RAGState]]) -> StateSnapshotEvent:
  """Check the status of the vector database connection."""
  log_agent_tool_call("get_database_status", {})
  
  try:
    # TODO: Implement actual health check
    ctx.deps.state.vector_db_status = "connected"  # Placeholder
    
    return ToolReturn(
      return_value={"status": "connected"},
      metadata=[
        StateSnapshotEvent(
          type=EventType.STATE_SNAPSHOT,
          snapshot=ctx.deps.state,
        )
      ]
    )
  except Exception as e:
    log_error("Error in get_database_status", e)
    raise


async def list_documents(
  ctx: RunContext[StateDeps[RAGState]]
) -> dict[str, Any]:
  """
  List all documents currently available in the knowledge base.
  Use this to find a document_id if one is not provided.
  
  Returns:
    Dictionary with 'documents' list.
  """
  log_agent_tool_call("list_documents", {})
  
  try:
    from src.knowledge_base.service import get_document_service
    service = await get_document_service()
    documents = await service.list_documents()
    
    return {
        "documents": documents,
        "should_render": True,
        "suggested_component": "list",
        "_note": "Internal: You must now call render_component('list', data=...) to display these documents."
    }
  except Exception as e:
    log_error("Error in list_documents", e)
    return {"error": str(e)}


async def list_document_toc(
  ctx: RunContext[StateDeps[RAGState]],
  document_id: Optional[str] = None
) -> dict[str, Any]:
  """
  Retrieve the Table of Contents (TOC) for a specific document.
  If document_id is not provided, uses the active document.
  
  Args:
    document_id: Optional ID of the document to get the TOC for.
    
  Returns:
    Dictionary with 'toc' (list of items) and 'filename'.
  """
  log_agent_tool_call("list_document_toc", {"document_id": document_id})
  
  try:
    from src.knowledge_base.service import get_document_service
    from src.knowledge_base.vector_store import get_vector_store
    from src.core.context import get_active_document_id
    
    doc_id = document_id or get_active_document_id()
    if not doc_id:
        return {"error": "No document ID provided and no active document set. Please provide a document_id or use search first."}
    
    vector_store = await get_vector_store()
    toc = await vector_store.get_toc(doc_id)
    doc_info = await vector_store.get_document(doc_id)
    
    should_render = len(toc) > 0
    note = "Internal: You must now call render_component('list', data=...) to display the TOC." if should_render else "Internal: No TOC found."
    
    return {
        "toc": toc or [],
        "filename": doc_info.get("filename") if doc_info else "Unknown",
        "document_id": doc_id,
        "should_render": should_render,
        "suggested_component": "list",
        "_note": note
    }
  except Exception as e:
    log_error("Error in list_document_toc", e, {"document_id": document_id})
    return {"error": str(e)}


async def get_section_content(
  ctx: RunContext[StateDeps[RAGState]],
  section_name: str,
  document_id: Optional[str] = None
) -> dict[str, Any]:
  """
  Retrieve all text content associated with a specific section or subsection.
  Useful for reading a whole chapter or section at once.
  
  Args:
    section_name: The name of the section or heading to retrieve (from TOC).
    document_id: Optional ID of the document. Uses active document if not set.
    
  Returns:
    Dictionary with 'content' (concatenated text) and 'chunks'.
  """
  log_agent_tool_call("get_section_content", {"section_name": section_name, "document_id": document_id})
  
  try:
    from src.knowledge_base.vector_store import get_vector_store
    from src.core.context import get_active_document_id
    
    doc_id = document_id or get_active_document_id()
    if not doc_id:
        return {"error": "No document ID provided and no active document set."}
    
    vector_store = await get_vector_store()
    chunks = await vector_store.get_chunks_by_section(doc_id, section_name)
    
    if not chunks:
        return {"error": f"No content found for section '{section_name}' in this document."}
    
    full_content = "\n\n".join([c["content"] for c in chunks])
    
    # Strictly limit content to avoid overwhelming the model or prompting it to 'fetch more'
    if len(full_content) > 15000:
        full_content = full_content[:15000] + "... [Content truncated for brevity]"
    
    return {
        "section_name": section_name,
        "content": full_content,
        "chunk_count": len(chunks),
        "document_id": doc_id
    }
  except Exception as e:
    log_error("Error in get_section_content", e, {"section_name": section_name})
    return {"error": str(e)}
