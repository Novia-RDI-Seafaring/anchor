import time
from typing import Optional
from src.types import (
    os, BaseModel, Field, Agent, RunContext, 
    StateDeps, EventType, StateSnapshotEvent, RAGState
)
from src.logger import log_rag_query, log_agent_tool_call, log_error
from pydantic_ai import ToolReturn
from evals.trace_logger import log_event
from evals.token_utils import estimate_tokens, estimate_tokens_bulk

async def query_knowledge_base(
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
    Dictionary with 'chunks' (list of dicts) and 'sources' from the knowledge base.
    Each chunk contains: id, content, filename, document_id, similarity, metadata.
  """
  start_time = time.time()
  
  # Log tool call
  log_agent_tool_call("query_knowledge_base", {"query": query, "top_k": top_k})
  
  try:
    # Import here to avoid circular imports
    from src.document_service import get_document_service
    from src.active_document import get_active_document_id
    
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
    
    # Update state with sources and chunks
    ctx.deps.state.current_sources = sources
    ctx.deps.state.last_chunks = chunks
    
    # Log query performance
    duration_ms = (time.time() - start_time) * 1000
    log_rag_query(query, top_k, len(chunks), duration_ms)
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
        return_value={"chunks": chunks, "sources": sources},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )
    
  except Exception as e:
    log_error("Error in query_knowledge_base", e, {"query": query, "top_k": top_k})
    # Return empty results on error with consistent type
    return ToolReturn(
        return_value={"chunks": [], "sources": []},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )

async def check_db_status(ctx: RunContext[StateDeps[RAGState]]) -> StateSnapshotEvent:
  """Check the status of the vector database connection."""
  log_agent_tool_call("check_db_status", {})
  
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
    log_error("Error in check_db_status", e)
    raise

async def add_to_conversation(
  ctx: RunContext[StateDeps[RAGState]], 
  role: str, 
  content: str
) -> StateSnapshotEvent:
  """Add a message to the conversation history."""
  log_agent_tool_call("add_to_conversation", {"role": role, "content_length": len(content)})
  
  ctx.deps.state.conversation_history.append({
    "role": role,
    "content": content
  })
  try:
    log_event({
        "type": "state",
        "conversation_len": len(ctx.deps.state.conversation_history),
        "last_chunks_len": len(ctx.deps.state.last_chunks),
        "ui_components_len": len(ctx.deps.state.active_ui_components),
    })
  except Exception:
    pass
  
  return ToolReturn(
    return_value={"success": True},
    metadata=[
      StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot=ctx.deps.state,
      )
    ]
  )


async def render_ui_component(
  ctx: RunContext[StateDeps[RAGState]],
  component_type: str,
  data: dict,
  metadata: Optional[dict] = None
) -> StateSnapshotEvent:
  """
  Render a UI component to display information from the knowledge base.
  The agent should call this tool after processing query results to display
  the information in an appropriate format (list, table, image, or page preview).
  
  Args:
    component_type: Type of component to render - one of: 'list', 'table', 'image', 'page_preview', 'markdown_table'
    data: Component-specific data payload. For 'page_preview', it may include 'bboxes' list.
    metadata: Optional metadata about the component
    
  Returns:
    StateSnapshotEvent with updated state
  """
  from src.types import UIComponentData, UIComponentType
  from src.active_document import get_active_document_id
  
  log_agent_tool_call("render_ui_component", {
    "component_type": component_type,
    "has_data": bool(data),
    "has_metadata": bool(metadata)
  })
  
  try:
    # Validate and convert component_type
    try:
      ui_component_type = UIComponentType(component_type)
    except ValueError:
      # Invalid component type, default to list
      ui_component_type = UIComponentType.LIST
    
    # For page_preview, auto-inject document_id if not provided
    if ui_component_type == UIComponentType.PAGE_PREVIEW:
      active_doc_id = get_active_document_id()
      if not data.get("document_id") and active_doc_id:
        data = dict(data)  # Make a copy to avoid mutating original
        data["document_id"] = active_doc_id
        print(f"render_ui_component: Auto-injected document_id: {active_doc_id}")
      
      # Also try to get page_numbers from metadata if not provided
      # Also try to get page_numbers from metadata if not provided
      if not data.get("page_numbers"):
        if data.get("page"):
            data["page_numbers"] = [data["page"]]
        elif data.get("page_number"):
            data["page_numbers"] = [data["page_number"]]
        # Fallback: Try to infer page_numbers from last_chunks if document_id matches
        elif ctx.deps.state.last_chunks and data.get("document_id"):
             target_doc_id = data.get("document_id")
             inferred_pages = []
             seen_pages = set()
             
             for chunk in ctx.deps.state.last_chunks:
                 if chunk.get("document_id") == target_doc_id:
                     pages_to_add = []
                     # Check page_numbers list in chunk
                     if chunk.get("page_numbers"):
                         pages_to_add = chunk["page_numbers"]
                     # Check metadata for page_numbers (list) or page_no (int)
                     elif chunk.get("metadata", {}).get("page_numbers"):
                         pages_to_add = chunk["metadata"]["page_numbers"]
                     elif chunk.get("metadata", {}).get("page_no"):
                          pages_to_add = [chunk["metadata"]["page_no"]]
                     
                     for p in pages_to_add:
                         if p not in seen_pages:
                             inferred_pages.append(p)
                             seen_pages.add(p)
             
             if inferred_pages:
                 data["page_numbers"] = inferred_pages
                 print(f"render_ui_component: Inferred page_numbers from chunks (ordered): {data['page_numbers']}")
        
      # Validation: document_id is mandatory for page_preview. Instead of raising (which triggers tool retries),
      # emit a friendly error component so the UI can surface the issue without exploding the stream.
      if not data.get("document_id"):
        error_component = UIComponentData(
          component_type=UIComponentType.LIST,
          data={
            "items": [
              {
                "title": "Page preview unavailable",
                "description": "Missing document_id for page preview. Ensure the chunk includes document_id and page numbers."
              }
            ],
            "title": "Display Error"
          },
          metadata={"error": "missing_document_id"}
        )
        ctx.deps.state.active_ui_components = [error_component]
        ctx.deps.state.render_mode = "list"
        return ToolReturn(
          return_value={"success": False, "error": "missing_document_id"},
          metadata=[
            StateSnapshotEvent(
              type=EventType.STATE_SNAPSHOT,
              snapshot=ctx.deps.state,
            )
          ]
        )
      # Auto-inject bboxes if missing, using last_chunks
      injected_bboxes = []
      if not data.get("bboxes") and ctx.deps.state.last_chunks:
        print(f"render_ui_component: Attempting to inject bboxes for doc {data.get('document_id')}")
        target_doc_id = data.get("document_id")
        
        # Find the first chunk that matches the document_id (highest relevance)
        # and use ONLY its bboxes to avoid clutter.
        top_chunk = next((c for c in ctx.deps.state.last_chunks if c.get("document_id") == target_doc_id), None)
        
        if top_chunk:
          meta = top_chunk.get("metadata", {})
          injected_bboxes = meta.get("bboxes", [])
          if injected_bboxes:
            print(f"render_ui_component: Injected {len(injected_bboxes)} bboxes from top-ranked chunk {top_chunk.get('id')}")
      
      if injected_bboxes:
          data = dict(data)
          data["bboxes"] = injected_bboxes
    
    # Create UI component data
    ui_component = UIComponentData(
      component_type=ui_component_type,
      data=data,
      metadata=metadata or {}
    )
    
    # Update state with new UI component (replace existing ones)
    ctx.deps.state.active_ui_components = [ui_component]
    ctx.deps.state.render_mode = component_type
    
    # Return ToolReturn to signal success to the agent framework
    return ToolReturn(
        return_value={"success": True, "component_type": component_type},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )
    
    # Dead code removed here


  except Exception as e:
    # Catch-all to avoid throwing up to the agent (which triggers retries).
    log_error("Error in render_ui_component (returning fallback)", e, {
      "component_type": component_type,
      "data_keys": list(data.keys()) if isinstance(data, dict) else "not_dict"
    })
    error_component = UIComponentData(
      component_type=UIComponentType.LIST,
      data={"items": [{"title": "Error rendering component", "description": str(e)}], "title": "Display Error"},
      metadata={"error": str(e)}
    )
    ctx.deps.state.active_ui_components = [error_component]
    ctx.deps.state.render_mode = "list"
    return ToolReturn(
        return_value={"success": False, "error": str(e)},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )
