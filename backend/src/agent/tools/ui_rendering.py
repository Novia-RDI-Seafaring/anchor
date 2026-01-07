"""UI rendering tools for displaying knowledge base results."""
from typing import Any

from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from pydantic_ai._run_context import RunContext
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai import ToolReturn

from src.core.logging import log_agent_tool_call, log_error

from ..state import RAGState, UIComponentData, UIComponentType


async def render_component(
  ctx: RunContext[StateDeps[RAGState]],
  component_type: str,
  data: Any,
  metadata: Any = None,
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
  from src.core.context import get_active_document_id

  # Be permissive with tool inputs: models sometimes send `data` as a list/string instead of an object.
  # If we reject the call, CopilotKit/pydantic-ai will retry and can get stuck.
  if not isinstance(data, dict):
    if isinstance(data, list):
      data = {"items": data}
    else:
      data = {"value": data}
  if metadata is not None and not isinstance(metadata, dict):
    metadata = {"value": metadata}
  
  log_agent_tool_call("render_component", {
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

    # Idempotency guard: if the UI is already showing a component, prevent a loop.
    # However, allow replacement if the component_type OR significant data has changed.
    # We compare the target component_type with the active one.
    if ctx.deps.state.active_ui_components:
        active_comp = ctx.deps.state.active_ui_components[0]
        # Only block if it's the EXACT same component type and effectively the same data.
        # This allows switching from 'list' to 'page_preview'.
        if active_comp.component_type.value == component_type:
             # Basic idempotency: if the content is the same, don't re-render.
             # This prevents the model from getting stuck in a tool-call loop.
             if active_comp.data == data:
                return ToolReturn(
                    return_value={
                        "success": True,
                        "component_type": component_type,
                        "already_rendered": True,
                        "note": "This exact component is already active. You MUST NOT call render_component again with these identical parameters. Respond to the user now.",
                    },
                    metadata=[
                        StateSnapshotEvent(
                            type=EventType.STATE_SNAPSHOT,
                            snapshot=ctx.deps.state,
                        )
                    ]
                )
    
    # For page_preview, auto-inject document_id if not provided
    if ui_component_type == UIComponentType.PAGE_PREVIEW:
      active_doc_id = get_active_document_id()
      if not data.get("document_id") and active_doc_id:
        data = dict(data)  # Make a copy to avoid mutating original
        data["document_id"] = active_doc_id
        print(f"render_component: Auto-injected document_id: {active_doc_id}")
      
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
                 print(f"render_component: Inferred page_numbers from chunks (ordered): {data['page_numbers']}")
        
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
        print(f"render_component: Attempting to inject bboxes for doc {data.get('document_id')}")
        target_doc_id = data.get("document_id")
        
        # Find the first chunk that matches the document_id (highest relevance)
        # and use ONLY its bboxes to avoid clutter.
        top_chunk = next((c for c in ctx.deps.state.last_chunks if c.get("document_id") == target_doc_id), None)
        
        if top_chunk:
          meta = top_chunk.get("metadata", {})
          injected_bboxes = meta.get("bboxes", [])
          if injected_bboxes:
            print(f"render_component: Injected {len(injected_bboxes)} bboxes from top-ranked chunk {top_chunk.get('id')}")
      
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

  except Exception as e:
    # Catch-all to avoid throwing up to the agent (which triggers retries).
    log_error("Error in render_component (returning fallback)", e, {
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
