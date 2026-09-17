"""The part a card plays in an argument (`data.role`).

A canvas that lays out a decision is made of cards playing known parts:
this is what was asked, this is an option, this is what we picked, this is
what we turned down, this is something we assumed rather than read. Those
parts are what the design-rationale literature has been naming for fifty
years -- IBIS calls them question / idea / argument, Toulmin calls them
claim / grounds / warrant / rebuttal -- and they are the difference between
a board a reader can follow and a pile of cards.

They are *roles*, not shapes. A decision and a rejected option are the same
card with different standing, so expressing them as eight node types would
bloat the vocabulary an agent has to learn and push the canvas toward being
a diagramming tool. One optional field on the elements that already exist
costs one concept and buys three things: the UI renders one visual language
a human learns once, an agent can ask what a canvas decided and get an
answer, and the board becomes readable as an argument rather than as boxes.

This mirrors ``data.review`` (#324) deliberately: a small closed vocabulary,
carried by any element, rendered as a badge, never blocking a write. An
unrecognised value is stored and warned about, not rejected -- the canvas is
a research instrument and should not refuse a word someone needs.
"""

from __future__ import annotations

from typing import Any

#: The parts a card can play. Ordered as a reader walks a decision.
ROLES: tuple[str, ...] = (
    "question",
    "criterion",
    "option",
    "evidence",
    "assumption",
    "decision",
    "rejected",
    "open",
)

#: One line each, surfaced through the node-types registry so an agent can
#: discover the vocabulary by asking rather than by reading documentation.
ROLE_DESCRIPTIONS: dict[str, str] = {
    "question": "What is being decided.",
    "criterion": "A requirement or constraint the answer has to satisfy.",
    "option": "A candidate answer under consideration.",
    "evidence": "A value or quote supporting or ruling out an option.",
    "assumption": "Something filled in rather than read from a source. The first thing a human should check.",
    "decision": "The answer. At most one per question.",
    "rejected": "An option considered and turned down, with the reason.",
    "open": "Still unresolved; someone has to confirm it.",
}


def role_of(data: dict[str, Any] | None) -> str | None:
    """The declared role, or None when absent or not a recognised value."""
    if not data:
        return None
    role = data.get("role")
    return role if isinstance(role, str) and role in ROLES else None


def role_warning(data: dict[str, Any] | None, *, partial: bool = False) -> str | None:
    """Non-blocking warning for a malformed or unknown ``data.role``.

    ``partial=True`` is the update-node case, where ``role: None`` is the
    documented way to drop the key (#192). Never blocks the write; adapters
    attach the message alongside the other non-fatal warnings.
    """
    if not data or "role" not in data:
        return None
    role = data["role"]
    if role is None and partial:
        return None
    if not isinstance(role, str):
        return (
            f"data.role should be a string, got {type(role).__name__}. "
            "Stored as-is, but it will not render as a role badge."
        )
    if role not in ROLES:
        return (
            f"data.role {role!r} is not one of {', '.join(ROLES)}. Stored "
            "as-is, but it will not render as a role badge. Use the listed "
            "vocabulary so a reader learns one visual language per canvas."
        )
    return None
