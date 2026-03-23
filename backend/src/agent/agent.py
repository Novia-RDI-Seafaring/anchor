# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
from dotenv import load_dotenv

load_dotenv(override=True)

import os
import re
from typing import Any, cast

from pydantic_ai import Agent, ModelRetry
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .deps import AgentDeps
from .helpers import (
    STRICT_CANVAS_VALIDATION,
    _EARLY_CANVAS_EDIT_RE,
    _EARLY_DOCUMENT_LISTING_RE,
    _EARLY_RAW_SEARCH_RE,
    _EARLY_SOCIAL_OR_META_RE,
    _early_prompt_to_text,
    _prompt_to_text,
    _requires_canvas_update,
)
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .state import Canvas
from .tools import canvas, knowledge, vision
from .tools import fmu as fmu_tools

_COMPARISON_QUERY_RE = re.compile(r"\b(compare|comparison|different|difference|diff|vs\.?|versus)\b", re.IGNORECASE)
_LIST_ONLY_TOOLS = {"list_documents"}
_RAW_SEARCH_TOOLS = {"search_knowledge_base", "get_active_document_context", "list_documents"}
_LOW_LEVEL_CANVAS_TOOLS = {
    "add_concept",
    "add_topic",
    "add_fact",
    "add_relation",
    "add_spec_node",
    "update_node",
    "delete_node",
    "check_canvas",
}
_HIGH_LEVEL_TECHNICAL_TOOLS = {
    "resolve_technical_query",
    "compare_documents",
    "get_active_document_context",
    "check_canvas",
    "list_documents",
    "inspect_fmu_tool",
    "simulate_fmu_tool",
    "analyze_simulation_tool",
}
_CANVAS_EDIT_TOOLS = _LOW_LEVEL_CANVAS_TOOLS | _HIGH_LEVEL_TECHNICAL_TOOLS

async def _prepare_tools_for_turn(ctx: RunContext[AgentDeps], tool_defs: list[Any]) -> list[Any]:
    prompt_text = _early_prompt_to_text(getattr(ctx, "prompt", None)).strip().lower()
    if not prompt_text:
        return tool_defs
    if _EARLY_SOCIAL_OR_META_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in _LIST_ONLY_TOOLS]
    if _EARLY_DOCUMENT_LISTING_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in _LIST_ONLY_TOOLS]
    if _EARLY_RAW_SEARCH_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in _RAW_SEARCH_TOOLS]
    if _EARLY_CANVAS_EDIT_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in _CANVAS_EDIT_TOOLS]
    return [tool_def for tool_def in tool_defs if tool_def.name in _HIGH_LEVEL_TECHNICAL_TOOLS]


agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
    instructions=SYSTEM_PROMPT,
    instrument=InstrumentationSettings(include_content=True),
    output_retries=2 if STRICT_CANVAS_VALIDATION else 0,
    prepare_tools=_prepare_tools_for_turn,
)


@agent.instructions
def technical_query_instruction(ctx: RunContext[AgentDeps]) -> str | None:
    prompt_text = _prompt_to_text(cast(Any, ctx.prompt)).strip()
    if not prompt_text or not _requires_canvas_update(prompt_text):
        return None
    normalized = prompt_text.lower()
    if _EARLY_SOCIAL_OR_META_RE.search(normalized) or _EARLY_DOCUMENT_LISTING_RE.search(normalized):
        return None
    if _EARLY_RAW_SEARCH_RE.search(normalized):
        return (
            "This is an explicit raw-retrieval request. Call "
            f"search_knowledge_base(query={prompt_text!r}) and answer from the returned chunks only. "
            "Do not change the canvas unless the user explicitly asks for canvas changes."
        )
    if _EARLY_CANVAS_EDIT_RE.search(normalized):
        return (
            "This is an explicit canvas request. Prefer resolve_technical_query() or compare_documents() "
            "when the user is asking to place technical findings on the canvas. Use low-level canvas tools "
            "only to restructure, connect, update, or delete existing canvas nodes."
        )
    if _COMPARISON_QUERY_RE.search(normalized):
        return (
            "This is a document-comparison query. Before any text answer, call "
            f"compare_documents(query={prompt_text!r}). Use its returned summary as the basis for the reply. "
            "Do not answer from raw retrieval only."
        )
    return (
        "This is a technical knowledge-base query. Before any text answer, call "
        f"resolve_technical_query(query={prompt_text!r}). Use its returned summary as the basis for the reply. "
        "Do not use search_knowledge_base for the final answer unless the user explicitly asks for raw retrieval only."
    )


@agent.output_validator
def ensure_technical_queries_update_canvas(ctx: RunContext[AgentDeps], data: str) -> str:
    if not STRICT_CANVAS_VALIDATION:
        return data

    prompt_text = _prompt_to_text(cast(Any, ctx.prompt))
    if not _requires_canvas_update(prompt_text):
        return data

    canvas_nodes = list(ctx.deps.state.nodes)
    has_topic = any(node.node_type == "topic" for node in canvas_nodes)
    fact_or_spec_nodes = [node for node in canvas_nodes if node.node_type in {"fact", "spec"}]
    resolved_fact_or_spec_nodes = [
        node for node in fact_or_spec_nodes if node.status in {"found", "partial", "not_found"}
    ]

    if not has_topic or not resolved_fact_or_spec_nodes:
        raise ModelRetry(
            "Technical KB answers require a topic plus at least one resolved fact or spec node on the canvas."
        )

    return data


# Register Canvas Tools
agent.tool(canvas.check_canvas)
agent.tool(canvas.add_concept)
agent.tool(canvas.add_topic)
agent.tool(canvas.add_fact)
agent.tool(canvas.add_relation)
agent.tool(canvas.add_spec_node)
agent.tool(canvas.update_node)
agent.tool(canvas.delete_node)

# Register Knowledge Tools
agent.tool(knowledge.list_documents)
agent.tool(knowledge.get_active_document_context)
agent.tool(knowledge.search_knowledge_base)
agent.tool(knowledge.resolve_technical_query)
agent.tool(knowledge.compare_documents)

# Register Vision Tools
agent.tool(vision.analyze_image_content)

# Register FMU Tools
agent.tool(fmu_tools.inspect_fmu_tool)
agent.tool(fmu_tools.simulate_fmu_tool)
agent.tool(fmu_tools.analyze_simulation_tool)

AppState = Canvas
