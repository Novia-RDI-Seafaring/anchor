from dotenv import load_dotenv
from pydantic_ai import Agent
from .deps import AgentDeps
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

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
    name="Knowledge Base Agent",
    model=get_default_responses_model(),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    tools=[
        render_component,

    ],
    instrument=InstrumentationSettings(include_content=True),
)

@agent.tool
def list_documents(ctx: RunContext[AgentDeps]):
    return ctx.deps.doc_service.list_files()

@agent.tool
def list_document_toc(ctx: RunContext[AgentDeps]):
    return "nothing"

@agent.tool
def get_section_content(ctx: RunContext[AgentDeps], section_id: str):
    return "nothing here"

@agent.tool
def search_knowledge_base(ctx: RunContext[AgentDeps], question: str):
    return ctx.deps.doc_service.query(question=question)

"""tools=[
    get_database_status, 
    search_knowledge_base, 
    list_documents,
    list_document_toc, 
    get_section_content, 
    render_component
],"""

@agent.tool
def consult_documents(ctx: RunContext[AgentDeps], query: str):
    return ctx.deps.doc_service.query(question=query)

AppState = RAGState
