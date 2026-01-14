from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.ag_ui import StateDeps

from .models import get_default_responses_model
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    search_knowledge_base,
    get_database_status,
    list_documents,
    list_document_toc,
    get_section_content,
    add_message,
    render_component,
)
from .state import RAGState

load_dotenv(override=True)

agent = Agent(
    model=get_default_responses_model(),
    deps_type=StateDeps[RAGState],
    system_prompt=SYSTEM_PROMPT,
    tools=[
        get_database_status, 
        search_knowledge_base, 
        list_documents,
        list_document_toc, 
        get_section_content, 
        render_component
    ],
)

AppState = RAGState
