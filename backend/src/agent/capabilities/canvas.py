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
  add_fact(text, topic_id, doc_id?, page?, bbox?)  — create a focused evidence-backed finding
  add_spec_node(spec_title, sections)  — create a parameter table
  update_node(node_id, spec_title?, parameter_sections?, title?, text?, status?)  — edit an existing node
  delete_node(node_id)  — remove a node and its relations
  add_relation(from_id, to_id, label?, source_handle?, target_handle?)  — connect two nodes

PARAMETER TABLE STRUCTURE (for add_spec_node sections and update_node parameter_sections):
  sections = [
    {
      "name": "Parameter group",
      "rows": [
        {"parameter": "Model or parameter name", "value": "value", "unit": "unit", "source": {"filename": "...", "page": 2}},
        {"parameter": "Another model or parameter", "value": "value", "unit": "unit", "source": {"filename": "...", "page": 2}}
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
1. Use check_canvas() before creating nodes so you can reuse an existing topic/concept when appropriate.
2. Use gold data from context (preferred) or read_document_page() to find values.
3. Use add_fact() for one focused finding.
4. Use add_spec_node() for table-like or multi-row structured data.
5. To refine, call update_node() on the existing node.

AUTO-CANVAS RULE:
- If the user asks a document-grounded extraction question whose answer is one specific scalar
  engineering fact/value and you have source provenance, you MUST create or reuse the canvas
  fact before sending the final answer. Do not answer first and stop. Do not wait for a second
  "add it to canvas" command.
- Scalar facts include sourced pressures, temperatures, dimensions, materials, warranty terms,
  limits, ranges, and single model-specific values.
- The fact text should be concise and include the subject, value, and unit when present.
- Preserve source qualifiers and conditions in canvas values, including parenthetical notes,
  materials, model ranges, frequency/speed conditions, and "only when"/"provided that" clauses.
- Attach source evidence: pass doc_id, page, and bbox/highlights from gold data or document
  context. If you cannot identify at least the source document and page, answer in chat but do
  NOT auto-modify the canvas.
- Use add_fact(doc_id=...) when you know the document id. If only the filename is available,
  use add_fact(filename=...). Use the page/bbox from the gold/silver item that supports the answer.
- Reuse the most specific existing topic/concept when possible. Prefer a scoped topic such as
  "<model or section> facts" or "<model or section> operating data"; create that short topic
  only when no suitable one already exists. Standalone fact cards are only acceptable when the
  scope is ambiguous.
- Before adding a scalar fact, check for an existing matching fact by document + model/section +
  parameter. If it already exists with the same value, do not duplicate it. If the value changed,
  update the existing node instead of creating a second card.
- If a question returns two or more related scalar values, create or update ONE compact
  add_spec_node() table with row-level sources instead of several fact cards.
- Do NOT auto-add nodes for explanations, summaries, comparisons, general descriptions,
  greetings, UI/meta questions, or answers that are not directly traceable to a document source.

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
