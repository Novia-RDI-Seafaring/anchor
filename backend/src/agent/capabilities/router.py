# pyright: reportUnknownVariableType=false
"""Router capability — early-prompt tool filtering and dynamic per-query instructions."""
from dataclasses import dataclass
from typing import Any, cast

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai._run_context import RunContext
from pydantic_ai.tools import ToolDefinition

from ..deps import AgentDeps
from ..helpers import (
    _EARLY_CANVAS_EDIT_RE,
    _EARLY_DOCUMENT_LISTING_RE,
    _EARLY_RAW_SEARCH_RE,
    _EARLY_SOCIAL_OR_META_RE,
    _is_section_table_query,
    _early_prompt_to_text,
    _prompt_to_text,
    _query_requests_multiple_property_groups,
    _requires_canvas_update,
)
from .base import RoutingRegistry

import re
_COMPARISON_QUERY_RE = re.compile(
    r"\b(compare|comparison|different|difference|diff|vs\.?|versus)\b", re.IGNORECASE
)
# Simple single-value factual lookups — "what is X", "give me the Y for Z", "what's the warranty"
_SIMPLE_FACTUAL_RE = re.compile(
    r"(what(?:'s| is| are| was)[ \w]*?\b(max|min|maximum|minimum|range|limit|pressure|temperature|temp|flow|speed|"
    r"power|voltage|weight|dimension|size|width|height|length|diameter|capacity|rating|torque|frequency|"
    r"warranty|certif|approval|material|connection|port|inlet|outlet|noise|sound|viscosity|density|\bph\b|"
    r"efficiency|head|current|rpm|seal|bearing|ip\s*\d|npshr?|npsh)\b"
    r"|give( me)? (the |its )?(dimension|size|spec|measurement|rating|value|limit|range|max|min|warranty)"
    r"|how (hot|cold|fast|heavy|big|tall|wide|long|loud|much|many)"
    r")",
    re.IGNORECASE,
)
# Queries requesting exhaustive/comprehensive information in one go
_COMPREHENSIVE_RE = re.compile(
    r"\b("
    r"tell me (all|everything)|everything about|all (things|about|you know)|"
    r"full overview|deep dive|comprehensive|complete (guide|overview|summary|profile|picture)|"
    r"what (all|everything)|show me everything|all (facts|specs|info|information|details)|"
    r"give me everything|all aspects|full (profile|detail|breakdown|analysis)|"
    r"entire|whole (document|picture)|summarize (everything|all)|walk me through"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class RouterCapability(AbstractCapability[Any]):
    """Filters tools and injects per-query routing instructions based on early prompt analysis.

    Takes a RoutingRegistry so the tool-name sets are owned by the domain capabilities,
    not duplicated here.
    """

    registry: RoutingRegistry

    # ── Tool filtering ────────────────────────────────────────────────────────

    async def prepare_tools(
        self,
        ctx: RunContext[AgentDeps],
        tool_defs: list[ToolDefinition],
    ) -> list[ToolDefinition]:
        prompt_text = _early_prompt_to_text(getattr(ctx, "prompt", None)).strip().lower()
        if not prompt_text:
            return tool_defs
        if _EARLY_SOCIAL_OR_META_RE.search(prompt_text):
            return [td for td in tool_defs if td.name in self.registry.list_only_tools]
        if _EARLY_DOCUMENT_LISTING_RE.search(prompt_text):
            return [td for td in tool_defs if td.name in self.registry.list_only_tools]
        if _EARLY_RAW_SEARCH_RE.search(prompt_text):
            return [td for td in tool_defs if td.name in self.registry.raw_search_tools]
        if _EARLY_CANVAS_EDIT_RE.search(prompt_text):
            return [td for td in tool_defs if td.name in self.registry.canvas_edit_tools]
        return [td for td in tool_defs if td.name in self.registry.high_level_technical_tools]

    # ── Dynamic per-query instruction ─────────────────────────────────────────

    def get_instructions(self):
        def _instruction(ctx: RunContext[AgentDeps]) -> str | None:
            prompt_text = _prompt_to_text(cast(Any, ctx.prompt)).strip()
            if not prompt_text or not _requires_canvas_update(prompt_text):
                return None
            normalized = prompt_text.lower()
            if _EARLY_SOCIAL_OR_META_RE.search(normalized) or _EARLY_DOCUMENT_LISTING_RE.search(normalized):
                return None
            if _EARLY_RAW_SEARCH_RE.search(normalized):
                return (
                    "This is an explicit raw-retrieval request. Call "
                    f"search_knowledge_base(query={prompt_text!r}) and answer from the returned chunks only. "
                    "Do not change the canvas unless the user explicitly asks for canvas changes."
                )
            if _EARLY_CANVAS_EDIT_RE.search(normalized):
                return (
                    "This is an explicit canvas request. Prefer resolve_technical_query() or compare_documents() "
                    "when the user is asking to place technical findings on the canvas. Use low-level canvas tools "
                    "only to restructure, connect, update, or delete existing canvas nodes."
                )
            if _COMPARISON_QUERY_RE.search(normalized):
                return (
                    "This is a document-comparison query. Before any text answer, call "
                    f"compare_documents(query={prompt_text!r}). Use its returned summary as the basis for the reply. "
                    "Do not answer from raw retrieval only."
                )
            if _COMPREHENSIVE_RE.search(normalized):
                return (
                    "COMPREHENSIVE QUERY — the user wants ALL available information. "
                    "Execute the full sequence autonomously in ONE response. Do NOT ask for permission to continue.\n"
                    "\n"
                    "Mandatory sequence:\n"
                    "1. check_canvas() — find existing concept node IDs to reuse.\n"
                    "2. get_document_tree(document_id=<active doc>) — identify chapters and which pages "
                    "   have tables, charts, or figures.\n"
                    "3. get_document_full_text(document_id=<active doc>, include_pages=[<every page that "
                    "   has a table or figure per the tree>) — read the COMPLETE document text AND page "
                    "   images. This is essential: cosine search misses table rows and variant-specific data.\n"
                    "4. resolve_technical_query() for EACH major aspect (Overview, Operating Limits, "
                    "   Dimensions, Connections, Motor, Performance, Features) — pass SAME concept_id "
                    "   returned by the first call to ALL subsequent calls.\n"
                    "5. add_page_image_to_canvas() for every chart, data table, or diagram page found "
                    "   in step 2-3 — with highlights pointing to the relevant variant/model values.\n"
                    "\n"
                    "Rules:\n"
                    "- Do NOT stop after 1-2 tool calls.\n"
                    "- Do NOT say 'That's all I found' or 'Want me to continue?'.\n"
                    "- Call tools until the canvas fully represents the subject.\n"
                    f"- Subject of query: {prompt_text!r}"
                )
            if _is_section_table_query(normalized) or _query_requests_multiple_property_groups(normalized):
                root_title = "Operating Data" if "operating data" in normalized else "Technical Data"
                return (
                    "SECTION/TABLE QUERY — the user wants one grounded fact table.\n"
                    "Think like a human: find the document, understand its structure, read the right page, extract the table.\n"
                    "\n"
                    "Steps:\n"
                    "1. Call check_canvas() to find an existing concept node to reuse.\n"
                    "2. Identify the document — use get_active_document_context() or list_documents().\n"
                    "3. Assess the document:\n"
                    "   a. Call get_document_page_count() to check document size.\n"
                    "   b. Short document (≤6 pages): call get_document_full_text(include_pages=[1,2,...all]) "
                    "      to read the ENTIRE document with page screenshots. Then extract the answer from what you see.\n"
                    "   c. Longer document: call get_document_tree() to find which section/pages contain "
                    "      the relevant data (look for table flags, section headings matching the query). "
                    "      Then call read_document_page() or analyze_pdf_page() on those specific pages.\n"
                    "4. From the page text and/or screenshots, extract the relevant rows/values.\n"
                    "   You are looking at the ACTUAL document — trust what you see over vector search results.\n"
                    f"5. Call resolve_technical_query(query={prompt_text!r}, concept_title=<subject>, "
                    f"root_title={root_title!r}, prefer_table=True) to create the canvas spec table.\n"
                    "   If resolve_technical_query misses rows you found by reading, add them manually.\n"
                    "6. Answer from what you found.\n"
                    "\n"
                    "Rules:\n"
                    "- Create ONE spec table with the relevant rows — not multiple nodes.\n"
                    "- Do NOT split this into multiple aspect calls or chart/image nodes.\n"
                    "- If the user asks for multiple values together, keep them in the same table.\n"
                    "- Ignore FMU nodes when organizing knowledge. Do NOT connect the new knowledge nodes to any FMU.\n"
                    "- ALWAYS read the document pages before creating canvas nodes. Vector search alone misses table data."
                )
            if _SIMPLE_FACTUAL_RE.search(normalized) and not _is_section_table_query(normalized) and not _query_requests_multiple_property_groups(normalized):
                return (
                    "SIMPLE FACTUAL LOOKUP — read the document, find the answer, record it.\n"
                    "\n"
                    "Steps:\n"
                    "1. Identify the document — use get_active_document_context() or list_documents().\n"
                    "2. Assess the document size with get_document_page_count().\n"
                    "   - Short doc (≤6 pages): call get_document_full_text(include_pages=[all pages]) "
                    "     to read the ENTIRE document. Find the answer in the text/screenshots.\n"
                    "   - Longer doc: call get_document_tree() to find likely sections, then "
                    "     read_document_page() on the relevant pages.\n"
                    f"3. Call resolve_technical_query(query={prompt_text!r}, concept_title=<subject>, "
                    "   root_title=<aspect>, prefer_table=True) to record the answer on canvas.\n"
                    "4. Answer the user concisely.\n"
                    "\n"
                    "Read the document first — vector search misses data in tables. "
                    "Trust what you see in the document over search results."
                )
            return (
                "TECHNICAL QUERY — read the document, then build the canvas.\n"
                "\n"
                "Steps:\n"
                "1. Call check_canvas() to find existing concept node IDs.\n"
                "2. Identify the document and assess its size with get_document_page_count().\n"
                "   - Short doc (≤6 pages): call get_document_full_text(include_pages=[all pages]) "
                "     to read the ENTIRE document with page screenshots.\n"
                "   - Longer doc: call get_document_tree() to find relevant sections, then "
                "     read_document_page() on those pages.\n"
                "3. Based on what you read, call resolve_technical_query() to build canvas nodes.\n"
                f"   Query: {prompt_text!r}\n"
                    "4. If the query spans multiple aspects, call resolve_technical_query MULTIPLE TIMES "
                    "   with the SAME concept_id, once per aspect.\n"
                    "\n"
                    "Ignore FMU nodes when building the knowledge graph. Do NOT attach knowledge nodes to FMUs.\n"
                    "ALWAYS read the document before creating canvas nodes. "
                    "Vector search alone misses tables, variant-specific data, and document structure."
            )

        return _instruction
