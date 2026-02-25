from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai.models.instrumented import InstrumentationSettings

from .models import get_default_responses_model
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    search_knowledge_base,
    list_documents,
    list_document_toc,
    get_section_content,
    render_component,
)
from .state import RAGState

load_dotenv(override=True)

agent = Agent(
    name="Knowledge Base Agent",
    model=get_default_responses_model(),
    deps_type=StateDeps[RAGState],
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
    tools=[
        search_knowledge_base, 
        list_documents,
        list_document_toc, 
        get_section_content, 
        render_component
    ],
)

AppState = RAGState
