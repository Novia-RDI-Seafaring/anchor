"""Review states on canvas nodes — convention over schema (#324).

A node may carry ``data.review``:

    {"state": "proposed" | "accepted" | "rejected",
     "by": {"kind": "human" | "agent" | "system", "label": "..."}?,
     "at": <unix ts>?}

This mirrors the placeholder pattern: the keys are documented convention,
not schema — ``node_type`` data stays open, nothing here is enforced at
write time. What core provides:

- The writer default: in a workspace whose ``metadata.review_mode`` is
  true, ``WorkspaceService.add_node`` stamps ``{state: "proposed"}`` (with
  the acting agent in ``by``) on nodes created by an actor of kind
  ``agent`` — unless the caller supplied its own ``review`` object. With
  the flag off (the default) nothing anywhere changes.
- A non-blocking warning (:func:`review_warning`) that adapters attach to
  add-node / update-node results when a supplied ``review`` object doesn't
  match the convention — same channel as the #191 unknown-data-key
  warning; the write always succeeds.

Verdicts are plain ``update-node`` data patches (``data.review.state`` →
"accepted" / "rejected"), so every adapter and agent can read and write
them with no new operations.
"""
from __future__ import annotations

from typing import Any

from anchor.core.events.actor import Actor

REVIEW_STATES: tuple[str, ...] = ("proposed", "accepted", "rejected")

REVIEW_MODE_KEY = "review_mode"


def proposed_review(actor: Actor, at: float) -> dict[str, Any]:
    """The ``data.review`` object stamped on an agent-created node."""
    by: dict[str, Any] = {"kind": actor.kind}
    if actor.label:
        by["label"] = actor.label
    return {"state": "proposed", "by": by, "at": at}


def review_warning(
    data: dict[str, Any] | None, *, partial: bool = False,
) -> str | None:
    """Non-blocking warning for a malformed ``data.review`` object.

    ``partial=True`` is the update-node case: ``data`` is a merge patch, so
    a review object without a ``state`` key is fine (the existing state
    survives the merge) and ``review: None`` is the documented way to drop
    the whole object. With ``partial=False`` (add-node), ``data`` is the
    full stored payload and a review object must carry a valid ``state``.
    Extra keys are always fine — the convention is open. Never blocks the
    write; adapters attach the message alongside the #191 unknown-data-key
    warning.
    """
    if not data or "review" not in data:
        return None
    review = data["review"]
    if review is None and partial:
        return None  # merge semantics: None deletes the key (#192)
    if not isinstance(review, dict):
        return (
            "data.review should be an object like "
            '{"state": "proposed"|"accepted"|"rejected", "by"?, "at"?}; '
            f"got {type(review).__name__}. Stored as-is, but review "
            "tooling will ignore it."
        )
    if "state" not in review and partial:
        return None
    state = review.get("state")
    if state not in REVIEW_STATES:
        return (
            f"data.review.state should be one of {', '.join(REVIEW_STATES)}; "
            f"got {state!r}. Stored as-is, but review tooling will ignore it."
        )
    return None
