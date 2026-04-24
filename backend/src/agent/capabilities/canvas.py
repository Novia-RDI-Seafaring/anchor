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
_toolset.tool(canvas_tools.check_canvas)
_toolset.tool(canvas_tools.add_concept)
_toolset.tool(canvas_tools.add_topic)
_toolset.tool(canvas_tools.add_fact)
_toolset.tool(canvas_tools.add_spec_node)
_toolset.tool(canvas_tools.update_node)
_toolset.tool(canvas_tools.delete_node)
_toolset.tool(canvas_tools.add_relation)

# ── Instructions ──────────────────────────────────────────────────────────────

_INSTRUCTIONS = dedent("""
══════════════════════════════════════
CANVAS TOOLS
══════════════════════════════════════

TOOLS:
  check_canvas()  — inspect current nodes and relations before adding new content
  add_concept(title)  — create a high-level subject/root node
  add_topic(title)  — create a topic/aspect bucket
  add_fact(text, topic_id, source...)  — create a focused evidence-backed finding
  add_spec_node(spec_title, sections)  — create a parameter table
  update_node(node_id, spec_title?, parameter_sections?, title?, text?, status?)  — edit an existing node
  delete_node(node_id)  — remove a node and its relations
  add_relation(from_id, to_id, label?, source_handle?, target_handle?)  — connect two nodes

PARAMETER TABLE STRUCTURE (for add_spec_node sections and update_node parameter_sections):
  sections = [
    {
      "name": "Max inlet pressure",
      "rows": [
        {"parameter": "LKH-5", "value": "600", "unit": "kPa", "source": {"filename": "...", "page": 2}},
        {"parameter": "LKH-10 - 70", "value": "1000", "unit": "kPa", "source": {"filename": "...", "page": 2}}
      ]
    }
  ]

SOURCES:
  EVERY row MUST have a source with at least filename and page.
  Include bbox [left, top, right, bottom] in BOTTOMLEFT PDF coords when available from gold data.
  "source": {"filename": "...", "page": 2, "bbox": [l, t, r, b]}

EDITING SPEC TABLES:
  To replace a spec table's content, call update_node(node_id=..., parameter_sections=[...]).
  This replaces ALL sections — include the full desired content.
  You can also update just the title: update_node(node_id=..., spec_title="New Title").

WORKFLOW:
1. Use gold data from context (preferred) or read_document_page() to find values.
2. Use add_fact() for one focused finding.
3. Use add_spec_node() for table-like or multi-row structured data.
4. To refine, call update_node() on the existing node.

RULES:
- ONE table per extraction, not multiple small ones.
- Use facts for scalar findings like warranty, pressure, temperature, and single limits.
- Short, clear parameter names.
- Units in the unit field, NOT in the value.
- Group related rows into sections.
- EVERY row needs a source.
- Do NOT modify canvas for greetings or meta-questions.
""").strip()


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class CanvasCapability(AbstractCapability[Any]):
    """Canvas manipulation tools and canvas/knowledge-graph instructions."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
