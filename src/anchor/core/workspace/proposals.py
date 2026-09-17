"""Proposal sets — reviewing what an agent added in one go, as one thing.

Review states (#324) are per element: an agent's node lands ``proposed``
and a human accepts or rejects it one at a time. That works for a stray
node and falls apart for a batch. Thirty-five grounded nodes built from
one document are thirty-five verdicts, with nothing recording which of
them belong together or why they were added.

A thread suggestion (#343) already solves this inside a thread: several
ops reviewed together, applied all-or-nothing. A proposal set is the same
handle for elements an agent adds outside a thread.

    {"id": "...",
     "reason": "mindmap of the SoftwareX author guide",
     "by": {"kind": "agent", "label": "claude-code"},
     "at": <unix ts>,
     "members": [{"kind": "node" | "edge", "id": "..."}],
     "state": "open" | "accepted" | "rejected",
     "reviewed_by": {...}?, "reviewed_at": <ts>?, "discarded": bool?}

Sets live in ``Workspace.metadata['proposal_sets']``, next to the
bibliography, and membership is *not* stamped on the elements: one set
record names its members, so grouping costs one event instead of one
write per element, and an element's ``data`` stays about the element.

A verdict is the existing per-element review write, applied to every
member under one lock: accepting a set stamps ``data.review.state =
"accepted"`` on each member, rejecting stamps ``"rejected"`` (feedback
the agent can read, per the review convention). Rejecting with
``discard`` removes the members instead, which is the clean undo for a
batch nobody wants: removing a member node cascades its edges.
"""
from __future__ import annotations

from typing import Any

from anchor.core.events.actor import Actor
from anchor.core.workspace.workspace import CommandError

PROPOSAL_SETS_KEY = "proposal_sets"

#: Lifecycle of a set. ``open`` = waiting for a human verdict.
PROPOSAL_SET_STATES: tuple[str, ...] = ("open", "accepted", "rejected")

#: What a member can be.
MEMBER_KINDS: tuple[str, ...] = ("node", "edge")


class ProposalSetError(CommandError):
    """A proposal-set command that cannot be carried out.

    A ``CommandError`` so every adapter's existing handling applies: the CLI
    prints one line and exits 1, HTTP answers 400. ``message`` is authored
    text, safe to return to a caller (#347: never leak exception internals
    into a response body).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # Authored text, safe to return to a caller (see #347: never leak
        # exception internals into a response body).
        self.message = message


def actor_ref(actor: Actor | None) -> dict[str, Any]:
    """The ``by`` shape stored on a set: kind plus optional label."""
    if actor is None:
        return {"kind": "system"}
    by: dict[str, Any] = {"kind": actor.kind}
    if actor.label:
        by["label"] = actor.label
    return by


def validate_members(members: Any) -> list[dict[str, str]]:
    """Normalise a members list, rejecting anything malformed.

    Accepts ``{"kind": "node"|"edge", "id": "..."}`` entries, or a bare
    string id as shorthand for a node (the common case). Duplicates are
    dropped, order is preserved.
    """
    if members is None:
        return []
    if not isinstance(members, list):
        raise ProposalSetError("members must be a list")
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in members:
        if isinstance(entry, str):
            kind, ident = "node", entry
        elif isinstance(entry, dict):
            kind = str(entry.get("kind", "node"))
            ident = entry.get("id")
            if not isinstance(ident, str) or not ident:
                raise ProposalSetError("each member needs a non-empty id")
        else:
            raise ProposalSetError("each member must be an object or an id string")
        if kind not in MEMBER_KINDS:
            raise ProposalSetError(
                f"member kind must be one of {', '.join(MEMBER_KINDS)}, got {kind!r}",
            )
        key = (kind, ident)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "id": ident})
    return out


def find_set(metadata: dict[str, Any], set_id: str) -> dict[str, Any] | None:
    """The stored set record with this id, or None."""
    for entry in list_sets(metadata):
        if entry.get("id") == set_id:
            return entry
    return None


def list_sets(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Every stored set record, oldest first. Tolerates a canvas that has none."""
    stored = metadata.get(PROPOSAL_SETS_KEY)
    if not isinstance(stored, list):
        return []
    return [dict(item) for item in stored if isinstance(item, dict)]
