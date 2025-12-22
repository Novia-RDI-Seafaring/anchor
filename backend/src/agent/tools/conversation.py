"""Conversation history management tools."""
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from pydantic_ai._run_context import RunContext
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai import ToolReturn

from src.core.logging import log_agent_tool_call
from evals.trace_logger import log_event

from ..state import RAGState


async def add_message(
  ctx: RunContext[StateDeps[RAGState]], 
  role: str, 
  content: str
) -> StateSnapshotEvent:
  """
  Add a message to the conversation history.
  
  Args:
    role: The role of the message sender ('user' or 'assistant')
    content: The message content
    
  Returns:
    StateSnapshotEvent with updated conversation state
  """
  log_agent_tool_call("add_message", {"role": role, "content_length": len(content)})
  
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
