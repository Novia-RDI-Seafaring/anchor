from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .deps import AgentDeps
from .models import get_default_responses_model
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    search_knowledge_base as search_knowledge_base_impl,
    get_database_status as get_database_status_impl,
    list_documents as list_documents_impl,
    list_document_toc as list_document_toc_impl,
    get_section_content as get_section_content_impl,
    render_component as render_component_impl,
)
from .state import RAGState

load_dotenv(override=True)

agent = Agent(
    name="Knowledge Base Agent",
    model=get_default_responses_model(),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
)

@agent.tool
async def get_database_status(ctx: RunContext[AgentDeps]):
    return await get_database_status_impl(ctx)


@agent.tool
async def search_knowledge_base(
    ctx: RunContext[AgentDeps],
    query: str,
    filename: str | None = None,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
):
    return await search_knowledge_base_impl(
        ctx,
        query=query,
        filename=filename,
        doc_ids=doc_ids,
        top_k=top_k,
    )


@agent.tool
async def list_documents(ctx: RunContext[AgentDeps]):
    return await list_documents_impl(ctx)


@agent.tool
async def list_document_toc(
    ctx: RunContext[AgentDeps],
    document_id: str | None = None,
):
    return await list_document_toc_impl(ctx, document_id=document_id)


@agent.tool
async def get_section_content(
    ctx: RunContext[AgentDeps],
    section_name: str | None = None,
    section_id: str | None = None,
    document_id: str | None = None,
):
    return await get_section_content_impl(
        ctx,
        section_name=section_name,
        section_id=section_id,
        document_id=document_id,
    )


@agent.tool
async def render_component(
    ctx: RunContext[AgentDeps],
    component_type: str,
    data: object,
    metadata: object | None = None,
):
    return await render_component_impl(
        ctx,
        component_type=component_type,
        data=data,
        metadata=metadata,
    )


AppState = RAGState
