# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
from dotenv import load_dotenv

load_dotenv(override=True)

import os
from typing import Any, cast

from pydantic_ai import Agent, ModelRetry
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .deps import AgentDeps
from .helpers import (
    STRICT_CANVAS_VALIDATION,
    _EARLY_CANVAS_EDIT_RE,
    _EARLY_DOCUMENT_LISTING_RE,
    _EARLY_SOCIAL_OR_META_RE,
    _early_prompt_to_text,
    _prompt_to_text,
    _requires_canvas_update,
)
from .prompts import SYS_PROMPT as SYSTEM_PROMPT
from .state import Canvas
from .tools import canvas, knowledge, vision

async def _prepare_tools_for_turn(ctx: RunContext[AgentDeps], tool_defs: list[Any]) -> list[Any]:
    prompt_text = _early_prompt_to_text(getattr(ctx, "prompt", None)).strip().lower()
    if not prompt_text:
        return tool_defs
    if _EARLY_SOCIAL_OR_META_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in {"list_documents"}]
    if _EARLY_DOCUMENT_LISTING_RE.search(prompt_text):
        return [tool_def for tool_def in tool_defs if tool_def.name in {"list_documents"}]
    if _EARLY_CANVAS_EDIT_RE.search(prompt_text):
        return tool_defs
    allowed = {
        "resolve_technical_query", "compare_documents",
        "search_knowledge_base", "get_active_document_context",
        "check_canvas", "list_documents", "add_concept",
    }
    return [tool_def for tool_def in tool_defs if tool_def.name in allowed]


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

AppState = Canvas
