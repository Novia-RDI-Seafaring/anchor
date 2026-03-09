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
from .state import Canvas, CanvasNode, Relation, SourceHighlight, SpecProperty, NodeStatus

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
async def add_topic(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id.

    During the PLAN phase use status="pending". Set status="found" once confirmed.
    """
    node = CanvasNode(node_type="topic", title=title, status=status)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx.deps.state)
    result.return_value = {"success": True, "id": node.id}
    return result

@agent.tool
async def add_fact(
    ctx: RunContext[AgentDeps],
    text: str,
    topic_id: str,
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a fact node linked to a topic. Returns the new node's id.

    During the PLAN phase, pass a placeholder text and status="pending".
    After finding the data, call update_node to fill in the real text and set status="found".
    """
    node = CanvasNode(node_type="fact", text=text, status=status)
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
        status="found",
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
async def add_spec_node(
    ctx: RunContext[AgentDeps],
    parent_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a spec (property table) node linked to a topic or fact.

    Use this instead of add_fact when data is tabular/parametric:
    dimensions, temperatures, flow rates, material grades, model numbers, etc.

    During the PLAN phase use status="pending" and an empty properties list.
    After extracting the table data, call update_node with the real properties and status="found".

    - parent_id: id of the parent topic or fact node
    - spec_title: short label for the table (e.g. "Dimensions (mm)", "Operating Limits")
    - properties: list of {key, value, unit} rows (can be [] during planning)
    """
    node = CanvasNode(
        node_type="spec",
        spec_title=spec_title,
        properties=properties,
        status=status,
    )
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=parent_id, to_id=node.id))
    result = _snapshot(ctx.deps.state)
    result.return_value = {"success": True, "id": node.id}
    return result


@agent.tool
async def update_node(
    ctx: RunContext[AgentDeps],
    node_id: str,
    status: NodeStatus | None = None,
    title: str | None = None,
    text: str | None = None,
    spec_title: str | None = None,
    properties: list[SpecProperty] | None = None,
) -> ToolReturn:
    """Update fields on an existing canvas node.

    Use this to:
    - Mark a node's status after searching (status="found"/"partial"/"not_found")
    - Fill in the real content after planning (text, title, spec_title, properties)
    - Correct or refine previously added content

    Only the fields you provide are changed; others stay as-is.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == node_id), None)
    if node is None:
        return ToolReturn(return_value={"success": False, "error": f"Node {node_id} not found"})
    if status is not None:
        node.status = status
    if title is not None:
        node.title = title
    if text is not None:
        node.text = text
    if spec_title is not None:
        node.spec_title = spec_title
    if properties is not None:
        node.properties = properties
    return _snapshot(ctx.deps.state)


@agent.tool
async def delete_node(ctx: RunContext[AgentDeps], node_id: str) -> ToolReturn:
    """Delete a canvas node and all its relations.

    Use this to remove placeholder nodes that turned out to be irrelevant,
    or to clean up duplicates.
    """
    ctx.deps.state.nodes = [n for n in ctx.deps.state.nodes if n.id != node_id]
    ctx.deps.state.relations = [
        r for r in ctx.deps.state.relations
        if r.from_id != node_id and r.to_id != node_id
    ]
    return _snapshot(ctx.deps.state)


@agent.tool
async def analyze_image_content(
    ctx: RunContext[AgentDeps],
    image_url: str,
    question: str,
) -> str:
    """Download a PDF screenshot and use vision AI to extract structured content.

    Use this when a chunk references a table, diagram, or chart that cannot be
    understood from the text alone. Pass the screenshot URL from the chunk metadata
    and ask a specific question (e.g. "Extract all rows and columns from this table
    as key-value pairs with units").

    Returns the extracted text/data as a string.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/png")

        result = await image_analysis_agent.run(
            [
                BinaryContent(data=image_bytes, media_type=content_type),
                question,
            ]
        )
        return result.response.text
    except Exception as exc:
        return f"Image analysis failed: {exc}"

AppState = Canvas
