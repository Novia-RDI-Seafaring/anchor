from dotenv import load_dotenv
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent   
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .deps import AgentDeps
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    render_component as render_component_impl,
)
from .state import RAGState

load_dotenv(override=True)
agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
)


image_analysis_agent = Agent(
    name="Image Analysis Agent",
    model=os.getenv("IMAGE_ANALYSIS_MODEL", "gpt-4o-mini"),
    system_prompt=(
        "Analyze the provided image URL and answer with factual, concise output. "
        "Do not hallucinate values; if uncertain, say so."
    ),
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
    return ctx.deps.rag.list_document_toc(document_id=document_id or "")

class PdfBBox(BaseModel):
    l: float
    t: float
    r: float
    b: float
    coord_origin: str = "BOTTOMLEFT"

@agent.tool
def look_at_scrreenshot_of_pdf_bounding_box(
    ctx: RunContext[AgentDeps],
    context_or_question: str,
    filename: str,
    page_no: int,
    bbox: PdfBBox,
    phrase: str | None = None,
    response_schema_hint: str | None = None,
):
    """
    Use this tool to have a multimodal llm look at an image and tell you what it contains.
    
    """
    from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes
    from src.api.file_service import get_file_service
    path = get_file_service().get_file_path(filename)
    image_bytes = render_pdf_page_to_image_bytes(
        pdf_path=path,
        page_no=page_no or 1,
        phrases=phrase,
        crop_bbox={
            "l": bbox.l,
            "t": bbox.t,
            "r": bbox.r,
            "b": bbox.b,
            "coord_origin": bbox.coord_origin,
        },
    )
    result = image_analysis_agent.run_sync(
        [
            'Give a super detailed description of the image, and a good query to help the llm provide you with the needde infor, you can suggest a schema etc..',
            context_or_question,
            f"response_schema_hint: {response_schema_hint}",
            BinaryContent(data=image_bytes, media_type='image/png'),  
        ]
    )
    return result.output

@agent.tool
async def analyze_image(
    ctx: RunContext[AgentDeps],
    context_or_question: str,
    image_url: str,
    response_schema_hint: str | None = None,
):
    import httpx
    return "it is a pic of a fish"
    image_response = httpx.get(image_url)  # Pydantic logo
    result = image_analysis_agent.run_sync(
        [
            'Give a super detailed description of the image, and a good query to help the llm provide you with the needde infor, you can suggest a schema etc..',
            context_or_question,
            f"response_schema_hint: {response_schema_hint}",
            BinaryContent(data=image_response.content, media_type='image/png'),  
        ]
    )
    return result.output

"""
@agent.tool
def get_section_content(
    ctx: RunContext[AgentDeps],
    section_name: str | None = None,
    section_id: str | None = None,
    document_id: str | None = None,
):
    return "not implemented yet"
   return await get_section_content_impl(
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
