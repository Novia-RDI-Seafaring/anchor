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
    _early_prompt_to_text,
    _prompt_to_text,
    _requires_canvas_update,
)
from .base import RoutingRegistry

import re
_COMPARISON_QUERY_RE = re.compile(
    r"\b(compare|comparison|different|difference|diff|vs\.?|versus)\b", re.IGNORECASE
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
            return (
                "This is a technical knowledge-base query. Before any text answer:\n"
                "1. Call check_canvas() to find existing concept node IDs.\n"
                f"2. Call resolve_technical_query(query={prompt_text!r}, concept_title=<subject>, root_title=<aspect>).\n"
                "3. If the query spans multiple aspects (e.g. 'overview and specs'), call "
                "   resolve_technical_query MULTIPLE TIMES with the SAME concept_id, once per aspect.\n"
                "Use the returned summaries as the basis for the final reply. "
                "Do not use search_knowledge_base for the final answer unless the user explicitly asks."
            )

        return _instruction
