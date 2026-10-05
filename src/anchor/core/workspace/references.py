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

from pydantic import BaseModel


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

    # Optional on historical reads. Only current authoring assigns an origin;
    # model loading and event replay must never relabel ambiguous geometry.
    coord_origin: str | None = None

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


def stamp_authored_source_refs(payload: Any, previous: Any = None) -> Any:
    """Copy a current write payload and mark its page-source coordinate contract.

    Current page/bbox authoring uses top-left coordinates. An explicit origin
    is preserved, including bottom-left imports. This is not a read/replay
    normalizer or a coordinate conversion; non-page producer locators pass.
    Copies of existing locators retain their recorded (possibly absent)
    origin, including when a whole row list is reordered.
    """
    prior_refs: list[dict[str, Any]] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("source_ref"), dict):
                prior_refs.append(value["source_ref"])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(previous)

    def same_locator(ref: dict[str, Any], old: dict[str, Any]) -> bool:
        # Updates deep-merge dictionaries: omitted geometry is retained. A
        # quote-only patch is not evidence of a new coordinate convention.
        if any(ref[key] != old.get(key) for key in (
            "slug", "page", "bbox", "approx_bbox", "approximate_bbox",
        ) if key in ref):
            return False
        detail = ref.get("detail")
        old_detail = old.get("detail")
        return not (isinstance(detail, dict) and "cell_bbox" in detail) or (
            detail["cell_bbox"] == (old_detail.get("cell_bbox") if isinstance(old_detail, dict) else None)
        )

    def copy(value: Any, old_value: Any = None) -> Any:
        if isinstance(value, list):
            # Lists replace, unlike dictionary patches. A row's old index is
            # not identity; use the complete locator match below after reorder.
            return [copy(item) for item in value]
        if not isinstance(value, dict):
            return value
        old = old_value if isinstance(old_value, dict) else {}
        out = {key: copy(child, old.get(key)) for key, child in value.items()}
        ref = out.get("source_ref")
        if not isinstance(ref, dict):
            return out
        old_ref = old.get("source_ref")
        old_kind = old_ref.get("kind") if isinstance(old_ref, dict) else None
        if ref.get("kind", old_kind) not in (None, "pdf-page-bbox"):
            return out
        old_page = old_ref.get("page") if isinstance(old_ref, dict) else None
        if not (isinstance(ref.get("page", old_page), int) or ref.get("kind") == "pdf-page-bbox"):
            return out
        if "coord_origin" not in ref:
            if isinstance(old_ref, dict) and same_locator(ref, old_ref):
                matches = [old_ref]
            else:
                matches = [old for old in prior_refs if same_locator(ref, old)]
            if matches:
                # Conflicting history is ambiguous too; never choose an origin
                # from whichever equal locator happens to occur first.
                origin = matches[0].get("coord_origin")
                ref["coord_origin"] = origin if all(old.get("coord_origin") == origin for old in matches) else None
            else:
                ref["coord_origin"] = "top-left"
        if (ref.get("coord_origin") in ("top-left", "bottom-left") and isinstance(old_ref, dict)
                and old_ref.get("coord_origin") != ref["coord_origin"]
                and not same_locator(ref, old_ref)):
            # A partial origin change must not inherit other geometry from
            # the old coordinate space. Null deletes in dictionary updates;
            # supplied new geometry remains authoritative.
            for key in ("bbox", "approx_bbox", "approximate_bbox"):
                if key in old_ref and key not in ref:
                    ref[key] = None
            old_detail = old_ref.get("detail")
            if isinstance(old_detail, dict) and "cell_bbox" in old_detail:
                if "detail" not in ref:
                    ref["detail"] = {"cell_bbox": None}
                elif isinstance(ref["detail"], dict):
                    ref["detail"].setdefault("cell_bbox", None)
        return out

    return copy(payload, previous)
