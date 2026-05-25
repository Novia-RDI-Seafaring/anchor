"""Identifier helpers — pure, no I/O."""
from __future__ import annotations

import re
import uuid
from typing import NewType

DocId = NewType("DocId", str)
WorkspaceId = NewType("WorkspaceId", str)
NodeId = NewType("NodeId", str)
EdgeId = NewType("EdgeId", str)
EventId = NewType("EventId", str)


def slugify(name: str) -> str:
    """Lowercase, alphanumeric, hyphen-separated. Empty input → 'doc'."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "doc"


# Workspace slugs become directory names under ``data_dir/canvases/``. We
# want them broad enough for human-friendly titles ("Vasa-sub-4budqsic"),
# but strictly free of path separators, parent-directory tokens, leading
# dots, and shell-meta characters. The regex below admits letters, digits,
# underscore, hyphen, and dot — anywhere except as the leading character
# (no hidden ``.foo`` directories). Maximum length 63 matches the common
# filename-segment limit on most filesystems.
_WORKSPACE_SLUG_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,62}$")


class InvalidWorkspaceSlugError(ValueError):
    """Raised when a workspace slug fails the identifier policy."""


def validate_workspace_slug(slug: str) -> str:
    """Return ``slug`` unchanged or raise :class:`InvalidWorkspaceSlugError`.

    Enforced policy:

    - 1-63 characters
    - first character is a letter, digit, underscore, or hyphen
    - subsequent characters are letters, digits, ``_``, ``-``, or ``.``
    - traversal tokens (``.`` / ``..``) and path separators (``/`` / ``\\``)
      are rejected
    - NUL bytes and control characters are rejected

    Called at every public boundary (HTTP routes, MCP tools, CLI subcommands)
    so the filesystem layer never sees a client-controlled directory name.
    """
    if not isinstance(slug, str) or not slug:
        raise InvalidWorkspaceSlugError("workspace slug missing or not a string")
    if slug in {".", ".."}:
        raise InvalidWorkspaceSlugError("workspace slug must not be '.' or '..'")
    if not _WORKSPACE_SLUG_RE.fullmatch(slug):
        raise InvalidWorkspaceSlugError(
            f"workspace slug {slug!r} must match {_WORKSPACE_SLUG_RE.pattern}"
        )
    return slug


def new_id() -> str:
    """8-char uuid4 fragment, matches the existing canvas convention."""
    return str(uuid.uuid4())[:8]


def new_event_id() -> str:
    """Full uuid4 for events — used as the idempotency key."""
    return str(uuid.uuid4())
