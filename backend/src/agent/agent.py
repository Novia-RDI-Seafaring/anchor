from dotenv import load_dotenv
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, ToolReturn   
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings
from ag_ui.core import EventType, StateSnapshotEvent  # type: ignore
from .deps import AgentDeps
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .tools import (
    render_component as render_component_impl,
)
from .state import Canvas, CanvasNode, Relation, SourceHighlight

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

def _snapshot(state: Canvas) -> ToolReturn:
    return ToolReturn(
        return_value={"success": True},
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )

@agent.tool
async def check_canvas(ctx: RunContext[AgentDeps]):
    """Return the current canvas state (nodes + relations)."""
    return ctx.deps.state

@agent.tool
async def add_topic(ctx: RunContext[AgentDeps], title: str) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id."""
    node = CanvasNode(node_type="topic", title=title)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx.deps.state)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_fact(ctx: RunContext[AgentDeps], text: str, topic_id: str) -> ToolReturn:
    """Add a fact node linked to a topic. Returns the new node's id."""
    node = CanvasNode(node_type="fact", text=text)
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=topic_id, to_id=node.id))
    result = _snapshot(ctx.deps.state)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_source(
    ctx: RunContext[AgentDeps],
    fact_id: str,
    filename: str,
    page: int,
    bbox: list[int],
    highlights: list[SourceHighlight] | None = None,
) -> ToolReturn:
    """Add a source node linked to a fact.

    - page / bbox: primary reference (first/most relevant location).
    - highlights: ordered list of {page, bbox} refs so the PDF viewer can
      step through all relevant locations in the document. If omitted, a
      single highlight is created from page + bbox automatically.

    bbox format: [left, top, right, bottom] in PDF points (BOTTOMLEFT origin).
    Use [0,0,0,0] if the bounding box is unknown.
    """
    resolved = highlights or [SourceHighlight(page=page, bbox=bbox)]
    node = CanvasNode(
        node_type="source",
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=resolved,
    )
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=fact_id, to_id=node.id))
    result = _snapshot(ctx.deps.state)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_relation(ctx: RunContext[AgentDeps], from_id: str, to_id: str, label: str = "") -> ToolReturn:
    """Connect any two canvas nodes with an optional relationship label."""
    ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))
    return _snapshot(ctx.deps.state)

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
async def analyze_image(
    ctx: RunContext[AgentDeps],
    context_or_question: str,
    image_url: str,
    response_schema_hint: str | None = None,
):
    import httpx
    return "This is not yet implemented..."

AppState = Canvas
