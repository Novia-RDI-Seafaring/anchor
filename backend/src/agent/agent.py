# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
from dotenv import load_dotenv

load_dotenv(override=True)

import os

from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings

from .capabilities import CAPABILITIES
from .deps import AgentDeps
from .prompts import AGENT_PREAMBLE
from .state import Canvas

agent = Agent(
    name="Knowledge Base Agent",
    model=os.getenv("DEFAULT_MODEL"),
    deps_type=AgentDeps,
    system_prompt=AGENT_PREAMBLE,
    instrument=InstrumentationSettings(include_content=True),
    capabilities=CAPABILITIES,
)

AppState = Canvas
