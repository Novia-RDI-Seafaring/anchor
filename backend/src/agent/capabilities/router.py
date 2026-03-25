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
            return (
                "This is a technical knowledge-base query. Before any text answer, call "
                f"resolve_technical_query(query={prompt_text!r}). Use its returned summary as the basis for the reply. "
                "Do not use search_knowledge_base for the final answer unless the user explicitly asks for raw retrieval only."
            )

        return _instruction
