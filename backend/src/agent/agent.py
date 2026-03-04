from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .deps import AgentDeps
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    render_component as render_component_impl,
)
from .state import RAGState

load_dotenv(override=True)
import os
agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
)

@agent.tool
async def get_database_status(ctx: RunContext[AgentDeps]):
    return "Not implemented yet"

@agent.tool
async def search_knowledge_base(
    ctx: RunContext[AgentDeps],
    query: str,
    filename: str | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
):
    return ctx.deps.rag.query(question=query, filename=filename, doc_ids=doc_ids, top_k=top_k)


@agent.tool
def list_documents(ctx: RunContext[AgentDeps]):
    return ctx.deps.rag.list_documents()


@agent.tool
def list_document_toc(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
):
    return ctx.deps.rag.list_document_toc(document_id=document_id)


@agent.tool
def get_section_content(
    ctx: RunContext[AgentDeps],
    section_name: str | None = None,
    section_id: str | None = None,
    document_id: str | None = None,
):
    return "not implemented yet"
    """ return await get_section_content_impl(
        ctx,
        section_name=section_name,
        section_id=section_id,
        document_id=document_id,
    )"""


@agent.tool
def render_component(
    ctx: RunContext[AgentDeps],
    component_type: str,
    data: object,
    metadata: object | None = None,
):
    return render_component_impl(
        ctx,
        component_type=component_type,
        data=data,
        metadata=metadata,
    )


AppState = RAGState
