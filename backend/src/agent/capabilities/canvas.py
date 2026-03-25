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
_toolset.tool(canvas_tools.add_relation)
_toolset.tool(canvas_tools.add_spec_node)
_toolset.tool(canvas_tools.update_node)
_toolset.tool(canvas_tools.delete_node)

# ── Instructions ──────────────────────────────────────────────────────────────

_INSTRUCTIONS = dedent("""
══════════════════════════════════════
CANVAS HIERARCHY
══════════════════════════════════════
concept  → the subject being researched ("A2UI", "Material X", "Pump Model Y")
  topic  → an aspect of that subject ("Benefits", "How it works", "Specifications")
    fact / spec  → findings under that aspect, evidence-linked to a document node

GOLDEN RULE: concept = WHAT you're studying. topic = WHICH ASPECT.
Never name a topic after a document section (e.g. "A2UI in Action") — that's a concept or aspect name.

══════════════════════════════════════
KNOWLEDGE GRAPH STRUCTURE
══════════════════════════════════════
Build the canvas as a structured knowledge graph the engineer can navigate at a glance.
Every answer should produce a graph like this:

  [concept: subject]
    ├── [topic: Overview]      → [fact: narrative summary]
    ├── [topic: Specifications] → [spec: key-value table of parameters]
    ├── [topic: Dimensions]    → [spec: dimension values] + [image: dimension drawing/table]
    ├── [topic: Performance]   → [image: flow chart / curve] + [fact: key operating point]
    └── [topic: Connections]   → [spec: port sizes and types]

Rules for a good knowledge graph:
  - ONE concept node per subject. All topics hang off it.
  - Group related data into named topics (Operating Limits, Dimensions, Motor, Connections, etc.)
    — do NOT dump everything into a single spec or fact node.
  - Use SPEC nodes for parametric data (numbers, units, ratings). Use FACT nodes for prose findings.
  - Add IMAGE nodes whenever there is a chart, diagram, table, or drawing worth seeing visually.
    Charts (flow curves, performance envelopes) and dimension drawings are almost always worth adding.
  - Always pass highlights to image nodes: the specific variant code, key values, or curve labels
    the engineer should look at (e.g. highlights=["LKH-5", "L = LKH-5", "600 kPa"]).
  - Connect every image node to its parent topic with parent_node_id.
  - Aim for 4-7 topic nodes on a focused variant/product query — enough to be complete, not overwhelming.

Node types:
  concept — high-level subject root (violet). One per researched subject.
  topic   — aspect/sub-question under a concept (amber)
  fact    — narrative finding with evidence edge to a document node
  spec    — tabular/parametric data (key-value rows) with evidence edge to a document node
  image   — PDF page screenshot; use for charts, diagrams, dimension drawings, data tables as visuals

Evidence location is carried on the edge that connects a fact/spec to a document node (__doc_{id}).
Source nodes no longer exist — use doc_id + page parameters on add_fact / add_spec_node instead.

Status: pending | searching | found | partial | not_found

══════════════════════════════════════
CANVAS — when and what to add
══════════════════════════════════════
The canvas is the engineer's live reference board. Add things worth keeping at hand.

ADD TO CANVAS:
  - Specifications, dimensions, ratings, part numbers, material properties
  - Step-by-step procedures or installation instructions
  - Cross-document comparisons
  - Any multi-fact finding the engineer will want to return to

SKIP THE CANVAS:
  - Greetings and meta-questions
  - One-sentence factual answers
  - Document listing

Low-level canvas tools (only when user explicitly asks to restructure):
  add_concept(title, status)
      — Creates a concept node. Returns id for use in resolve_technical_query.
  add_topic(title, status)
  add_fact(text, topic_id, status, doc_id, page, bbox, highlights, chunk_index)
  add_spec_node(parent_id, spec_title, properties, status, doc_id, page, bbox, highlights, chunk_index)
  add_relation(from_id, to_id, label)
  update_node(node_id, status, title, text, spec_title, properties)
  delete_node(node_id)

══════════════════════════════════════
CANVAS WORKFLOW (when resolve_technical_query isn't sufficient)
══════════════════════════════════════
For multi-aspect research:
  1. check_canvas() — find existing concept or note it's empty
  2. add_concept(title="A2UI", status="found")  — only if not already present
  3. For each aspect:
     a. add_topic(title="Benefits", status="found") → link to concept via add_relation
     b. search_knowledge_base(query)
     c. add_fact(text, topic_id, chunk_index=0)

RULES
- Never mention internal tool names, node IDs, or status values in the chat answer.
- Keep text answers concise. The canvas holds the detail.
- Topic title = the ASPECT (Benefits, Architecture, Modes). NOT the document section.
- Concept title = the SUBJECT (A2UI, Material X). Reuse if already on canvas.
- Do not create source nodes — evidence is carried on edges to document nodes.
""").strip()


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class CanvasCapability(AbstractCapability[Any]):
    """Canvas manipulation tools and canvas/knowledge-graph instructions."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
