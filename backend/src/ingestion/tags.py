"""Closed-vocab tag system for gold sections and regions.

Open-ended tags drift fast (`per_model` vs `per-model` vs `per_model_specs`).
This module pins the allowed values as a frozen set + a Pydantic-friendly
Literal so an LLM that emits an out-of-vocab tag fails validation and we
review the schema instead of letting drift accumulate.

Categories:
    structural — what *role* the block plays in the document
    content    — what *shape* the block has
    semantic   — what *topic* the block is about (domain-specific)
    entity     — `mentions:<slug>` references (open-ended, prefix-checked)
"""
from __future__ import annotations

from typing import Literal


# ── structural: role in the document ─────────────────────────────────────────
StructuralTag = Literal[
    "introduction",
    "benefits",
    "application",
    "ordering",
    "warranty",
    "options",
    "safety",
]

# ── content: shape of the block ──────────────────────────────────────────────
ContentTag = Literal[
    "narrative",
    "property_group",
    "table_2d",
    "figure",
    "chart",
    "diagram",
    "cross_ref",
]

# ── semantic: topic (domain-specific, pump-leaning today) ────────────────────
SemanticTag = Literal[
    "per_model_specs",
    "operating_limits",
    "materials",
    "dimensions",
    "connections",
    "motor_specs",
    "performance_curve",
    "flow_chart",
    "safety",
]

Tag = StructuralTag | ContentTag | SemanticTag

# Frozen sets for runtime membership checks (used by validators that need
# to inspect "is this string a known tag?" without hand-typing each Literal).
STRUCTURAL_TAGS: frozenset[str] = frozenset({
    "introduction", "benefits", "application", "ordering",
    "warranty", "options", "safety",
})
CONTENT_TAGS: frozenset[str] = frozenset({
    "narrative", "property_group", "table_2d", "figure",
    "chart", "diagram", "cross_ref",
})
SEMANTIC_TAGS: frozenset[str] = frozenset({
    "per_model_specs", "operating_limits", "materials", "dimensions",
    "connections", "motor_specs", "performance_curve", "flow_chart", "safety",
})
KNOWN_TAGS: frozenset[str] = STRUCTURAL_TAGS | CONTENT_TAGS | SEMANTIC_TAGS

ENTITY_PREFIX = "mentions:"


def is_known_tag(tag: str) -> bool:
    """Closed-vocab membership; entity tags must use the `mentions:` prefix."""
    if tag.startswith(ENTITY_PREFIX):
        return len(tag) > len(ENTITY_PREFIX)
    return tag in KNOWN_TAGS


def validate_tags(tags: list[str]) -> list[str]:
    """Return offending tags. Empty list = all tags are valid."""
    return [t for t in tags if not is_known_tag(t)]


def entity_tag(slug: str) -> str:
    """Build a `mentions:<slug>` entity tag from a normalized slug."""
    return f"{ENTITY_PREFIX}{slug.strip().lower()}"
