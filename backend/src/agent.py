# agent.py
import time

from .types import (
    os, BaseModel, Field, Agent, RunContext, 
    StateDeps, EventType, StateSnapshotEvent, RAGState
)
from .model import get_default_responses_model
from .prompts.system import SYS_PROMPT as SYSTEM_PROMPT

# load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import logger
from src.logger import log_rag_query, log_agent_tool_call, log_error

# Import tools
from src.tools.rag_tools import query_knowledge_base, check_db_status, add_to_conversation, render_ui_component

# =====
# Agent
# =====
agent = Agent(
  model = get_default_responses_model(), # OpenAIResponsesModel(os.getenv('LLM_MODEL', 'gpt-4o-mini')),
  deps_type=StateDeps[RAGState],
  system_prompt=SYSTEM_PROMPT,
  tools=[check_db_status, query_knowledge_base, add_to_conversation, render_ui_component]
)

# Register tools
# agent.tool(check_db_status)
# agent.tool(query_knowledge_base)
# agent.tool(add_to_conversation)
# agent.tool(render_ui_component)

# Export state for type compatibility with main.py
AppState = RAGState
