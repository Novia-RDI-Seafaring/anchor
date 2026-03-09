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
from .state import Canvas, Note, Relation

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
async def check_canvas(ctx: RunContext[AgentDeps]):
    return ctx.deps.state

@agent.tool
async def add_note(ctx: RunContext[AgentDeps], note: Note) -> StateSnapshotEvent:
    ctx.deps.state.notes.append(note)
    return ToolReturn(
        return_value={"success": True},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )

@agent.tool
async def add_relation(ctx: RunContext[AgentDeps], from_id: str, to_id: str, label: str = "") -> StateSnapshotEvent:
    """Connect two notes by id with an optional label describing how they relate."""
    ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))
    return ToolReturn(
        return_value={"success": True},
        metadata=[
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=ctx.deps.state,
            )
        ]
    )

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
