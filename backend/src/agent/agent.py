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
        #search_knowledge_base,
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

"""tools=[
    get_database_status, 
    search_knowledge_base, 
    list_documents,
    list_document_toc, 
    get_section_content, 
    render_component
],"""

from llama_index.core.base.response.schema import RESPONSE_TYPE
@agent.tool
def consult_documents(ctx: RunContext[AgentDeps], query: str) -> RESPONSE_TYPE:
    result: RESPONSE_TYPE = ctx.deps.doc_service.query(question=query)
    sources = result.get_formatted_sources()
    print("--------------------------------")
    print("SOURCES")
    print(sources)
    print("--------------------------------")
    return result

AppState = RAGState
