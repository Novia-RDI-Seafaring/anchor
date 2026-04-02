# pyright: reportUnknownVariableType=false
"""Canvas capability — canvas manipulation tools and canvas/knowledge-graph instructions."""
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import canvas as canvas_tools

# ── Tool names (used by RouterCapability) ────────────────────────────────────

LOW_LEVEL_TOOLS: frozenset[str] = frozenset({
    "check_canvas",
    "add_concept",
    "add_topic",
    "add_fact",
    "add_relation",
    "add_spec_node",
    "update_node",
    "delete_node",
})

# ── Toolset ───────────────────────────────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
# Minimal set: only spec table creation for now
_toolset.tool(canvas_tools.add_spec_node)

# ── Instructions ──────────────────────────────────────────────────────────────

_INSTRUCTIONS = dedent("""
══════════════════════════════════════
CANVAS — PARAMETER TABLE
══════════════════════════════════════
You have ONE canvas tool: add_spec_node. It creates a parameter table on the canvas.

  add_spec_node(
    spec_title: str,           — title at the top (e.g. "LKH-5 Operating Data")
    sections: list,            — parameter groups (see structure below)
  )

Structure:
  sections = [
    {
      "name": "Max inlet pressure",
      "rows": [
        {"parameter": "LKH-5", "value": "600", "unit": "kPa", "source": {"filename": "...", "page": 2}},
        {"parameter": "LKH-10 - 70", "value": "1000", "unit": "kPa", "source": {"filename": "...", "page": 2}}
      ]
    },
    {
      "name": "Temperature",
      "rows": [
        {"parameter": "Range", "value": "-10 to +140", "unit": "°C", "source": {"filename": "...", "page": 2}},
        {"parameter": "Flush media max", "value": "70", "unit": "°C", "source": {"filename": "...", "page": 2}}
      ]
    }
  ]

EVERY row MUST have a source with at least filename and page number.
When you know the exact location on the page, include bbox coordinates in the
source so the PDF viewer highlights the exact location:
  "source": {"filename": "...", "page": 2, "bbox": [l, t, r, b]}
The bbox is [left, top, right, bottom] in PDF coordinates (BOTTOMLEFT origin).
The engineer needs to click through to verify each value.
If you only know filename + page, provide that. The backend will try to enrich bbox
automatically from the PDF text layout.

WORKFLOW:
1. Read the document with read_document_page() to find the data.
2. Extract the relevant values, noting which page each comes from.
3. Call add_spec_node() ONCE with ALL the data organized in sections.
4. Answer the user concisely — the table on the canvas holds the detail.

RULES:
- ONE table per answer, not multiple.
- Short, clear parameter names.
- Units go in the unit field, NOT in the value.
- Group related rows into sections.
- EVERY row must have a source (filename + page).
- Do NOT add to canvas for greetings or meta-questions.
""").strip()


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class CanvasCapability(AbstractCapability[Any]):
    """Canvas manipulation tools and canvas/knowledge-graph instructions."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
