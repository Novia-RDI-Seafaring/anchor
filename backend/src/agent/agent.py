# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
from dotenv import load_dotenv

load_dotenv(override=True)

import os

from pydantic_ai import Agent, ModelRetry
from pydantic_ai._run_context import RunContext
from pydantic_ai.models.instrumented import InstrumentationSettings

from .capabilities import CAPABILITIES
from .deps import AgentDeps
from .helpers import (
    _has_materialized_canvas_content,
    _has_materialized_spec,
    _requires_canvas_materialization,
    _requires_spec_materialization,
)
from .prompts import AGENT_PREAMBLE
from .state import Canvas


agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=AGENT_PREAMBLE,
    instrument=InstrumentationSettings(include_content=True),
    capabilities=CAPABILITIES,
    output_retries=int(os.getenv("CANVAS_OUTPUT_RETRIES", "3")),
)


@agent.output_validator
async def _require_canvas_for_document_facts(ctx: RunContext[AgentDeps], output: str) -> str:
    if _requires_spec_materialization(ctx.prompt, ctx.deps.state, output) and not _has_materialized_spec(ctx):
        raise ModelRetry(
            "This request asks for multiple related document values. A fact card is not sufficient. "
            "Do not answer in text only. First call add_spec_node with row-level filename/page/bbox sources, "
            "then answer briefly."
        )
    if _requires_canvas_materialization(ctx.prompt, ctx.deps.state, output) and not _has_materialized_canvas_content(ctx):
        raise ModelRetry(
            "This document-backed engineering value/spec request must update the canvas before the final answer. "
            "Do not answer in text only. First call add_fact(text=..., filename or doc_id=..., page=..., "
            "bbox=[...]) for one scalar value, or add_spec_node with row-level sources for multiple values. "
            "Then answer briefly."
        )
    return output


AppState = Canvas
