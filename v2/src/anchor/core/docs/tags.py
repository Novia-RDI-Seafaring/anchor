"""Closed-vocab tag mechanism — generic, no domain knowledge.

The *mechanism* is the contribution: closed-vocab tags fail fast when an LLM
or human emits a typo, instead of letting drift accumulate. The *vocabulary*
is application-specific and lives in application config or a domain plugin —
NOT in core. v1 of this module hard-coded a pump-leaning vocabulary
(`ordering`, `warranty`, `motor_specs`, `performance_curve`, …); v2 keeps the
generic structural categories (structural / content / semantic / entity) but
treats their contents as runtime-supplied data.

Application code builds a `TagVocab` once at startup and threads it through
wherever validation happens. Tests construct their own vocab inline.

The `mentions:<slug>` entity-tag prefix is generic and stays in core because
it's a structural pattern (cross-doc entity references), not a domain choice.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENTITY_PREFIX = "mentions:"


@dataclass(frozen=True)
class TagVocab:
    """Closed vocabulary the application accepts.

    Each category is a frozenset; membership is checked at runtime. Empty
    vocab = anything goes through `mentions:`-prefix path; everything else
    fails validation. Useful for tests that don't care about tag shape.
    """

    structural: frozenset[str] = field(default_factory=frozenset)
    content: frozenset[str] = field(default_factory=frozenset)
    semantic: frozenset[str] = field(default_factory=frozenset)

    @property
    def known(self) -> frozenset[str]:
        return self.structural | self.content | self.semantic

    def is_known(self, tag: str) -> bool:
        """Closed-vocab membership; entity tags use the `mentions:` prefix."""
        if tag.startswith(ENTITY_PREFIX):
            return len(tag) > len(ENTITY_PREFIX)
        return tag in self.known

    def validate(self, tags: list[str]) -> list[str]:
        """Return offending tags. Empty list = all tags are valid."""
        return [t for t in tags if not self.is_known(t)]


def entity_tag(slug: str) -> str:
    """Build a `mentions:<slug>` entity tag from a normalised slug."""
    return f"{ENTITY_PREFIX}{slug.strip().lower()}"


def is_entity_tag(tag: str) -> bool:
    return tag.startswith(ENTITY_PREFIX) and len(tag) > len(ENTITY_PREFIX)


def entity_slug(tag: str) -> str | None:
    """Extract the slug from `mentions:<slug>`. Returns None if not an entity tag."""
    return tag[len(ENTITY_PREFIX):] if is_entity_tag(tag) else None


# An EMPTY default — explicit. Application code overrides with its own vocab.
EMPTY_VOCAB = TagVocab()
