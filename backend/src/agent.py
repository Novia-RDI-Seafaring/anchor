# agent.py
import time

from .types import (
    os, BaseModel, Field, Agent, RunContext, 
    StateDeps, EventType, StateSnapshotEvent
)
from .model import get_default_responses_model
from .prompts.system import SYS_PROMPT as SYSTEM_PROMPT

# load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import logger
from src.logger import log_rag_query, log_agent_tool_call, log_error

# =====
# State
# =====
class RAGState(BaseModel):
  """State for RAG-powered conversation."""
  conversation_history: list[dict[str, str]] = Field(
    default_factory=list,
    description='The conversation history',
  )
  current_sources: list[str] = Field(
    default_factory=list,
    description='Sources from the most recent knowledge base query',
  )
  vector_db_status: str = Field(
    default='disconnected',
    description='Status of the vector database connection',
  )

# =====
# Agent
# =====
agent = Agent(
  model = get_default_responses_model(), # OpenAIResponsesModel(os.getenv('LLM_MODEL', 'gpt-4o-mini')),
  deps_type=StateDeps[RAGState],
  system_prompt=SYSTEM_PROMPT,
)

# =====
# Tools
# =====
@agent.tool
async def query_knowledge_base(
  ctx: RunContext[StateDeps[RAGState]], 
  query: str,
  top_k: int = 5
) -> dict[str, list[str]]:
  """
  Query the vector database for relevant context.
  Uses the active document filter if set by the user.
  
  Args:
    query: The search query
    top_k: Number of results to retrieve (default: 5)
  
  Returns:
    Dictionary with 'chunks' and 'sources' from the knowledge base
  """
  start_time = time.time()
  
  # Log tool call
  log_agent_tool_call("query_knowledge_base", {"query": query, "top_k": top_k})
  
  try:
    # Import here to avoid circular imports
    from src.document_service import get_document_service
    import main
    
    # Get active document filter
    active_doc_id = main._active_document_id
    
    # Query the vector store with optional document filter
    service = await get_document_service()
    results = await service.search(query, top_k=top_k, document_id=active_doc_id)
    
    # Extract chunks and sources
    chunks = [r["content"] for r in results]
    sources = list(set(r["filename"] for r in results))
    
    # Update context state
    ctx.deps.state.current_sources = sources
    
    # Log query performance
    duration_ms = (time.time() - start_time) * 1000
    log_rag_query(query, top_k, len(chunks), duration_ms)
    
    return {
      "chunks": chunks,
      "sources": sources
    }
    
  except Exception as e:
    log_error("Error in query_knowledge_base", e, {"query": query, "top_k": top_k})
    # Return empty results on error rather than failing
    return {"chunks": [], "sources": []}

@agent.tool
async def check_db_status(ctx: RunContext[StateDeps[RAGState]]) -> StateSnapshotEvent:
  """Check the status of the vector database connection."""
  log_agent_tool_call("check_db_status", {})
  
  try:
    # TODO: Implement actual health check
    ctx.deps.state.vector_db_status = "connected"  # Placeholder
    
    return StateSnapshotEvent(
      type=EventType.STATE_SNAPSHOT,
      snapshot=ctx.deps.state,
    )
  except Exception as e:
    log_error("Error in check_db_status", e)
    raise

@agent.tool
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
  
  return StateSnapshotEvent(
    type=EventType.STATE_SNAPSHOT,
    snapshot=ctx.deps.state,
  )

# Export state for type compatibility with main.py
AppState = RAGState
