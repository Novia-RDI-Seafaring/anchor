from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.ag_ui import StateDeps

from .llm import get_default_responses_model
from .prompts.system import SYS_PROMPT as SYSTEM_PROMPT
from .tools.rag_tools import (
    add_to_conversation,
    check_db_status,
    query_knowledge_base,
    render_ui_component,
)
from .types import RAGState

load_dotenv(override=True)

agent = Agent(
    model=get_default_responses_model(),
    deps_type=StateDeps[RAGState],
    system_prompt=SYSTEM_PROMPT,
    tools=[check_db_status, query_knowledge_base, add_to_conversation, render_ui_component],
)

AppState = RAGState
