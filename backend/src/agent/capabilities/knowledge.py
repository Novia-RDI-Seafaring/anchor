# pyright: reportUnknownVariableType=false
"""Knowledge capability — RAG/search tools and intent-routing instructions."""
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import knowledge as knowledge_tools

# ── Tool names (used by RouterCapability) ────────────────────────────────────

LIST_ONLY_TOOLS: frozenset[str] = frozenset({"list_documents"})
RAW_SEARCH_TOOLS: frozenset[str] = frozenset({
    "search_knowledge_base",
    "get_active_document_context",
    "list_documents",
})
HIGH_LEVEL_TOOLS: frozenset[str] = frozenset({
    "resolve_technical_query",
    "compare_documents",
    "get_active_document_context",
    "check_canvas",
    "list_documents",
})

# ── Toolset ───────────────────────────────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(knowledge_tools.list_documents)
_toolset.tool(knowledge_tools.get_active_document_context)
_toolset.tool(knowledge_tools.search_knowledge_base)
_toolset.tool(knowledge_tools.resolve_technical_query)
_toolset.tool(knowledge_tools.compare_documents)

# ── Instructions ──────────────────────────────────────────────────────────────

_INSTRUCTIONS = dedent("""
══════════════════════════════════════
INTENT ROUTING
══════════════════════════════════════
Greetings / thanks / capability questions
  → plain text only, no tools.

"What documents are loaded?" / listing questions
  → call list_documents(), answer in text.

Ambiguous technical question with no active document selected
  → call get_active_document_context() first, then proceed.

Technical question with findings worth preserving — use resolve_technical_query():
  specs, dimensions, procedures, comparisons, part numbers,
  modes, how something works, processes, steps,
  benefits, features, capabilities, advantages, characteristics,
  list of items, summary of a topic, "what does X do", "explain X"
  and, by default, any technical KB question that should appear on the canvas
  → ALWAYS call check_canvas() first to find existing concept nodes.
  → Then call resolve_technical_query(
        query=<the specific question>,
        concept_title=<the SUBJECT, e.g. "A2UI">,
        root_title=<the ASPECT, e.g. "Benefits">,
    )
  → This creates: concept → topic(aspect) → facts(evidence-linked)

For multi-aspect queries ("show me", "explain", "overview"):
  Call resolve_technical_query MULTIPLE TIMES with the SAME concept_title.
  The first call returns concept_id — pass it directly to subsequent calls.

  ✗ WRONG — different concept_title each time creates disconnected islands:
    resolve_technical_query(concept_title="Dividend Benefits", root_title="Benefits")
    resolve_technical_query(concept_title="Dividend Strategy", root_title="Strategy")

  ✓ RIGHT — same concept_title groups all aspects under one root:
    r1 = resolve_technical_query(concept_title="Dividends", root_title="Benefits")
    resolve_technical_query(concept_id=r1["concept_id"], root_title="Strategy")
    resolve_technical_query(concept_id=r1["concept_id"], root_title="Tax Optimization")

For COMPREHENSIVE queries ("tell me everything", "all about X", "full overview", "all things about"):
  NEVER stop after 1-2 tool calls. NEVER say "That's all I found" or "Want me to continue?".
  The mandatory sequence is:
    1. check_canvas() — find existing concept node IDs to reuse
    2. get_document_tree(document_id=<active doc>) — identify chapters and pages with tables/figures
    3. get_document_full_text(document_id=<active doc>, include_pages=[all table/chart pages]) —
       cosine search MISSES table rows and variant-specific data; full text is essential
    4. resolve_technical_query() for EACH major aspect, passing the SAME concept_id each time:
       Overview, Operating Limits, Dimensions, Connections, Motor, Performance, Features, etc.
    5. add_page_image_to_canvas() for every chart, data table, or diagram page found
  Keep calling tools until the canvas fully represents the subject.
Simple raw retrieval / debugging request — use search_knowledge_base():
  only when the user explicitly asks to search, inspect chunks, or avoid changing the canvas.

Table/section queries:
  Queries like "operating data", "technical data", "specifications", or questions that ask
  for multiple properties at once (e.g. temperature and pressure) require DOCUMENT READING,
  not just vector search. Tables are poorly captured by embeddings.

  Before creating canvas nodes, ALWAYS read the relevant document pages:
    - Short docs (≤6 pages): read the entire document with get_document_full_text(include_pages=all)
    - Longer docs: use get_document_tree() to find the right section, then read those pages
    - Look at the page screenshots — tables are visual, trust what you see

  Then create:
    - one concept node for the product
    - one topic bucket such as Operating Data or Technical Data
    - one spec table containing ALL relevant rows you found by reading
  Do NOT split this intent into multiple aspect calls or chart/image nodes unless the user asks.
  Do NOT rely on resolve_technical_query alone for table data — it uses cosine search.

Explicit canvas request ("add this to canvas", "turn this into a table on canvas"):
  prefer resolve_technical_query() / compare_documents() first.
  Use low-level canvas tools only to restructure or edit existing nodes.

If an active document is selected, treat generic terms ("the material", "the part", "the specs",
"the document", "technical data") as referring to that document.

High-level tools (prefer these):
  resolve_technical_query(query, concept_title, concept_id, root_title, prefer_table, top_k)
      Search KB, populate canvas with concept/topic/fact-or-spec nodes, return grounded summary.
      concept_title = the subject (e.g. "A2UI"). root_title = the aspect (e.g. "Benefits").
      root_title should be a reusable aspect bucket, not the literal user question.
      Prefer: Overview, Technical Data, Operating Limits, Dimensions, Performance, Connections,
      Materials, Installation, or Motor.
      Returns concept_id — pass it to subsequent calls to reuse the same concept node.
      Creates up to 4 fact nodes, all evidence-linked.
      This is the default tool for technical KB questions.

      Organization rule:
        Avoid messy one-child chains. If a narrow answer would create a topic that only wraps
        one fact/spec and duplicates the query wording, reuse an existing broader aspect topic
        instead of creating a new skinny topic.

      For section/table intents:
        When the user's intent is "show me the operating data / technical data / specs" or
        a small bundle of related values, prefer ONE spec node with multiple rows. Do not
        decompose it into several separate facts or subtopics unless the user asked for analysis.

      Multi-variant data (e.g. motor options, model variants):
        When the source lists multiple distinct variants (IEC80/IEC90, LKH-5/LKH-10, etc.),
        call resolve_technical_query ONCE PER VARIANT with the same concept_id and a
        variant-specific root_title (e.g. "Motor — IEC80", "Motor — IEC90").
        Each call produces a separate spec node, making variants easy to compare.

  compare_documents(query, top_k)
      Compare two documents side by side, build comparison table on canvas.

  search_knowledge_base(query, filename, doc_ids, top_k)
      Raw retrieval — no canvas changes. Use only for explicit raw-search/debug requests.

  list_documents()
  get_active_document_context()
  check_canvas()  ← call this before resolve_technical_query to find existing concepts

Workspace awareness:
  The canvas state contains workspace_doc_ids — a list of document IDs the user has added
  to their current workspace. When workspace_doc_ids is non-empty, restrict all searches to
  those documents only. If you find a relevant document not in the workspace, suggest the user
  add it via the library drawer (say "I found [doc], would you like to add it to your workspace?").

FMU separation:
  FMU nodes are simulation objects, not knowledge-graph parents.
  When answering document or KB questions, do NOT connect concept/topic/fact/spec nodes to FMU nodes.
  Only create FMU→plot relations for simulation results, or user-requested manual parameter wiring.
""").strip()


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class KnowledgeCapability(AbstractCapability[Any]):
    """RAG/search tools and intent-routing instructions."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
