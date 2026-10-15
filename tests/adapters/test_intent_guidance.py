"""Published agent guidance must distinguish action from staged human review."""
import re

import pytest

from anchor.adapters.mcp.handlers_intents import tool_definitions
from anchor.adapters.mcp.server_instructions import HELP_RESOURCE_TEXT, INSTRUCTIONS


@pytest.mark.parametrize("surface", ["instructions", "help", "suggestion_tool"])
def test_guidance_names_immediate_and_staged_paths_without_self_approval(surface):
    tools = {tool["name"]: tool for tool in tool_definitions()}
    guidance = {
        "instructions": INSTRUCTIONS,
        "help": HELP_RESOURCE_TEXT,
        "suggestion_tool": tools["intent_add_item"]["description"],
    }[surface]
    assert "intent_act" in guidance
    assert re.search(r"apply\s*[:=]\s*false", guidance, re.IGNORECASE)
    assert "intent_apply" in guidance
    assert not re.search(r"call\s+`?intent_apply`?[^.]*yourself", guidance)
    assert "human" in tools["intent_apply"]["description"].lower()
    assert "intent_act" in tools["intent_apply"]["description"]
