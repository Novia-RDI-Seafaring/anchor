"""Reference — a canvas-scoped citation into a source document.

A reference captures *where a fact came from*: a document slug + page, plus
an optional bbox / region id and a free-form ``detail`` (quote, cell bbox,
match info). References are the human-driven complement to agent-driven
grounding: a person selects source content, names it, and keeps it in a
per-canvas bibliography (the ``references`` list in ``Workspace.metadata``).

This module is pure domain. The ``source_ref`` shape deliberately mirrors
the per-row ``source_ref`` that spec nodes already carry (slug + page +
optional bbox/region_id/detail) so a reference can be attached to a node or
spec row and drive the existing value-level highlight without translation.

Scope note: references live in canvas meta for now. The shape and the
service API are written so the store can be promoted to project level later
(for cross-canvas reuse / paper compilation) without changing callers.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceRefDetail(BaseModel):
    """Fine-grained locator inside a source region (aligns with #145).

    Every field is optional; the detail is additive context layered on top
    of the page+bbox locator. ``quote`` is the exact selected text,
    ``cell_bbox`` pins a single table cell, ``match`` carries matcher
    metadata (e.g. which occurrence on the page).
    """

    quote: str | None = None
    cell_bbox: list[float] | None = None
    match: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class SourceRef(BaseModel):
    """Where a fact lives in a source document.

    ``slug`` (document) and ``page`` are required — they are the minimal
    locator. ``bbox`` / ``region_id`` / ``detail`` refine it. Extra keys are
    allowed so a producer can carry richer locators without a schema bump.
    """

    slug: str
    page: int
    bbox: list[float] | None = None
    region_id: str | None = None
    detail: SourceRefDetail | None = None

    model_config = {"extra": "allow"}


class Reference(BaseModel):
    """One entry in a canvas's bibliography.

    ``id`` is server-assigned (see ``WorkspaceService.create_reference``).
    ``created_at`` is set at the service boundary from the injected clock so
    tests can assert shape without a wall-clock value.
    """

    id: str
    label: str | None = None
    source_ref: SourceRef
    created_by: str = "human"
    created_at: float = 0.0

    model_config = {"extra": "forbid"}


class ReferenceError(ValueError):
    """Raised when a reference / source_ref / attach target is malformed."""


def validate_source_ref(raw: Any) -> SourceRef:
    """Coerce ``raw`` into a :class:`SourceRef` or raise :class:`ReferenceError`.

    Enforces the minimal contract (``slug`` + ``page`` required) and rejects a
    non-dict payload. Optional ``bbox`` / ``region_id`` / ``detail`` are passed
    through. This is the single validation point every adapter funnels through
    so HTTP / MCP / CLI reject the same malformed input identically.
    """
    if not isinstance(raw, dict):
        raise ReferenceError("source_ref must be an object with slug + page")
    slug = raw.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ReferenceError("source_ref.slug is required and must be a non-empty string")
    page = raw.get("page")
    # bool is an int subclass; reject it explicitly so True/False never passes.
    if isinstance(page, bool) or not isinstance(page, int):
        raise ReferenceError("source_ref.page is required and must be an integer")
    bbox = raw.get("bbox")
    if bbox is not None and not _is_bbox(bbox):
        raise ReferenceError("source_ref.bbox must be a list of four numbers")
    region_id = raw.get("region_id")
    if region_id is not None and not isinstance(region_id, str):
        raise ReferenceError("source_ref.region_id must be a string")
    try:
        return SourceRef.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — normalise to one error type
        raise ReferenceError(f"invalid source_ref: {exc}") from exc


def _is_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )
