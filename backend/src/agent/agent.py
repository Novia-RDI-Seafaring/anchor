# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
from dotenv import load_dotenv

load_dotenv(override=True)

import os
from typing import Any, cast

from pydantic_ai import Agent, ModelRetry
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .capabilities import CAPABILITIES
from .deps import AgentDeps
from .helpers import STRICT_CANVAS_VALIDATION, _prompt_to_text, _requires_canvas_update
from .prompts import AGENT_PREAMBLE
from .state import Canvas

agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=AGENT_PREAMBLE,
    instrument=InstrumentationSettings(include_content=True),
    output_retries=2 if STRICT_CANVAS_VALIDATION else 0,
    capabilities=CAPABILITIES,
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


AppState = Canvas
