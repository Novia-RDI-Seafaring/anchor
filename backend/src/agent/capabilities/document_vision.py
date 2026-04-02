# pyright: reportUnknownVariableType=false
"""Document vision capability — full-text and PDF image tools, plus full-context mode instruction."""
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai._run_context import RunContext
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import vision as vision_tools
from ..tools import document as document_tools

# ── Tool names (used by RouterCapability) ────────────────────────────────────

HIGH_LEVEL_TOOLS: frozenset[str] = frozenset({
    "get_document_tree",
    "get_document_page_count",
    "read_document_page",
    "get_document_full_text",
    "analyze_pdf_page",
    "add_page_image_to_canvas",
    "analyze_image_content",
})

# ── Toolset ───────────────────────────────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(document_tools.get_document_tree)
_toolset.tool(document_tools.get_document_page_count)
_toolset.tool(document_tools.read_document_page)
_toolset.tool(document_tools.get_document_full_text)
_toolset.tool(document_tools.analyze_pdf_page)
_toolset.tool(document_tools.add_page_image_to_canvas)
_toolset.tool(vision_tools.analyze_image_content)

# ── Instructions ──────────────────────────────────────────────────────────────

_STATIC_INSTRUCTIONS = dedent("""
Document vision tools:
  get_document_tree(document_id, filename)
      Return the chapter/section hierarchy of a document with page numbers,
      table/figure flags, and LLM-generated summaries per chapter.
      Use this FIRST for large documents — it tells you which pages to load
      instead of loading the whole document blindly.
      The tree shows: heading > pages > has_table/has_figure > summary + questions answered.

  get_document_page_count(document_id, filename)
      Return the total page count.
      Use this before sequential reading when you need to walk a document page by page.

  read_document_page(document_id, filename, page_no, include_image)
      Read ONE specific page directly from the PDF, with optional rendered page image.
      Use this for page-by-page navigation: page 1, table of contents, front matter,
      appendices, or when the document tree is missing or too coarse.
      This is the best tool when you want to inspect how the document is organized
      before deciding whether to load large sections or the full document.

  get_document_full_text(document_id, filename, include_pages)
      Retrieve the COMPLETE text of a document (all chunks, page-ordered).
      Use when vector search gives incomplete answers, or when asked to summarise/read
      a full document, or when a query targets a specific variant/model code.
      include_pages: optional list of page numbers to also return as images — use this
      for pages containing tables, charts, or diagrams (e.g. [3, 4, 5]). Max 6 pages.
      Returns text followed by page images; you can read the images directly.

  analyze_pdf_page(filename, page_no, question, bbox, highlights)
      Return a rendered PDF page (or cropped region) as an image for you to read directly.
      Use for charts, diagrams, flow charts, and tables not well captured by text extraction.
      For pump performance charts or NPSH curves, you can use get_pump_curve_reference()
      first if you need help interpreting curve elements.
      bbox: optional [left, top, right, bottom] crop in PDF coordinates (BOTTOMLEFT).
      highlights: text phrases to underline on the rendered image (e.g. ["LKH-5", "600 kPa"]).
      Call this before add_page_image_to_canvas when you want to understand the content first.
      You can call it for multiple pages in sequence.

  add_page_image_to_canvas(filename, page_no, title, bbox, highlights, parent_node_id)
      Place a PDF page screenshot as an image node on the canvas.
      Always use for: performance charts, flow curves, dimension drawings, visual data tables.
      highlights: list of text phrases to underline on the image (e.g. ["LKH-5", "L = LKH-5"]).
                  Always pass the relevant variant code and key values so the engineer sees what matters.
      parent_node_id: ALWAYS connect to the relevant topic node.

Variant/model-specific queries (e.g. "facts about LKH-5", "specs for model X"):
  When the query targets a specific product variant or model code:
  1. Call get_document_full_text with include_pages covering all data table and chart pages.
     Read the full text and all page images to extract every relevant value for that variant.
  2. Build a complete knowledge graph:
     - One concept node for the variant (e.g. "Alfa Laval LKH-5")
     - Topic nodes: Overview, Operating Limits, Dimensions, Motor, Connections, Performance
     - Spec nodes under each topic with the variant's actual values extracted from tables
     - Image nodes for every chart/diagram/table page — with highlights pointing to the variant's row/curve
  3. Do NOT rely on resolve_technical_query alone — it uses cosine search and will miss table rows.

Sequential-reading rule:
  If you need to understand the document layout itself, start with read_document_page(page_no=1)
  or the page that likely contains the table of contents. Walk page by page as needed.
  Use get_document_full_text only after you know you need broad document context.
""").strip()


def _full_context_instruction(ctx: RunContext[AgentDeps]) -> str | None:
    from src.core.config import get_settings
    if not get_settings().is_full_context_mode:
        return None
    active_doc_id = ctx.deps.state.active_document_id
    if not active_doc_id:
        return None
    return (
        "FULL CONTEXT MODE is active. The model has a large context window — use it. "
        "If document structure is unclear, first use read_document_page on page 1 and any "
        "table-of-contents pages to orient yourself. "
        "For any document query, call get_document_full_text with include_pages covering all "
        "pages that contain tables, charts, or diagrams (e.g. include_pages=[1,2,3,4,5]). "
        "Do NOT rely on search_knowledge_base alone — it uses cosine similarity and will miss "
        "table rows and variant-specific data. Load the full document and read it directly. "
        "After loading, extract all relevant data and build a complete canvas representation."
    )


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class DocumentVisionCapability(AbstractCapability[Any]):
    """Full-text and PDF image tools, plus full-context mode dynamic instruction."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> list:
        return [_STATIC_INSTRUCTIONS, _full_context_instruction]
