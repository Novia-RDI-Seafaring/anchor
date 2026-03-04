"""UI rendering tools for displaying knowledge base results."""
from typing import Any

from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from pydantic_ai._run_context import RunContext
from pydantic_ai import ToolReturn
from src.agent.deps import AgentDeps
from src.core.logging import log_agent_tool_call, log_error

from ..state import RAGState, UIComponentData, UIComponentType


async def render_component(
  ctx: RunContext[AgentDeps],
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
    
    # For page_preview, auto-inject provenance fields when possible.
    if ui_component_type == UIComponentType.PAGE_PREVIEW:
      data = dict(data)
      active_doc_id = get_active_document_id()

      def _extract_pages(chunk: dict[str, Any]) -> list[int]:
        pages: list[int] = []
        if chunk.get("page_numbers"):
          pages.extend(chunk.get("page_numbers") or [])
        citation = chunk.get("citation", {}) or {}
        if citation.get("page_numbers"):
          pages.extend(citation.get("page_numbers") or [])
        provenance = chunk.get("provenance", {}) or {}
        artifact = provenance.get("artifact", {}) if isinstance(provenance, dict) else {}
        if artifact.get("page_numbers"):
          pages.extend(artifact.get("page_numbers") or [])
        metadata_chunk = chunk.get("metadata", {}) or {}
        if metadata_chunk.get("page_numbers"):
          pages.extend(metadata_chunk.get("page_numbers") or [])
        elif metadata_chunk.get("page_no") is not None:
          pages.append(metadata_chunk.get("page_no"))
        return [int(p) for p in pages if isinstance(p, int)]

      def _extract_bboxes(chunk: dict[str, Any]) -> list[dict[str, Any]]:
        if chunk.get("bboxes"):
          return chunk.get("bboxes") or []
        metadata_chunk = chunk.get("metadata", {}) or {}
        if metadata_chunk.get("bboxes"):
          return metadata_chunk.get("bboxes") or []
        provenance = chunk.get("provenance", {}) or {}
        artifact = provenance.get("artifact", {}) if isinstance(provenance, dict) else {}
        return artifact.get("bboxes") or []

      if not data.get("document_id") and active_doc_id:
        data["document_id"] = active_doc_id
        print(f"render_component: Auto-injected document_id: {active_doc_id}")

      if not data.get("page_numbers"):
        if data.get("page"):
          data["page_numbers"] = [data["page"]]
        elif data.get("page_number"):
          data["page_numbers"] = [data["page_number"]]
        elif ctx.deps.state.last_chunks and data.get("document_id"):
          target_doc_id = data.get("document_id")
          inferred_pages = []
          seen_pages = set()

          for chunk in ctx.deps.state.last_chunks:
            if chunk.get("document_id") == target_doc_id:
              for page_number in _extract_pages(chunk):
                if page_number not in seen_pages:
                  inferred_pages.append(page_number)
                  seen_pages.add(page_number)

          if inferred_pages:
            data["page_numbers"] = inferred_pages
            print(f"render_component: Inferred page_numbers from chunks (ordered): {data['page_numbers']}")

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

      target_doc_id = data.get("document_id")
      top_chunk = None
      if ctx.deps.state.last_chunks and target_doc_id:
        top_chunk = next((c for c in ctx.deps.state.last_chunks if c.get("document_id") == target_doc_id), None)

      if top_chunk:
        if not data.get("citation") and top_chunk.get("citation"):
          data["citation"] = top_chunk.get("citation")
        if not data.get("provenance") and top_chunk.get("provenance"):
          data["provenance"] = top_chunk.get("provenance")

      retrieval_meta = ctx.deps.state.last_retrieval_meta or {}
      if not data.get("retrieval_id"):
        retrieval_id = (
          (top_chunk or {}).get("provenance", {}).get("pipeline", {}).get("retrieval", {}).get("retrieval_id")
          or retrieval_meta.get("retrieval_id")
        )
        if retrieval_id:
          data["retrieval_id"] = retrieval_id

      if not data.get("trace_id"):
        trace_id = (
          (top_chunk or {}).get("provenance", {}).get("trace", {}).get("trace_id")
          or retrieval_meta.get("trace_id")
        )
        if trace_id:
          data["trace_id"] = trace_id

      if not data.get("bboxes") and top_chunk:
        injected_bboxes = _extract_bboxes(top_chunk)
        if injected_bboxes:
          data["bboxes"] = injected_bboxes
          print(f"render_component: Injected {len(injected_bboxes)} bboxes from top-ranked chunk {top_chunk.get('id')}")
    
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
