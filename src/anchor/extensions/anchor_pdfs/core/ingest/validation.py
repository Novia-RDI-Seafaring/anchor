"""Shared region schema validation - pure, dict-in / errors-out.

The gold layer is the trust boundary of the whole pipeline: regions carry
the provenance (page + bbox) every downstream consumer relies on. Until
now nothing validated what the extractor returned - any dict was
persisted as-is. This module is the single schema both pipelines apply
before persisting a region:

- the keyed pipeline (IngestService) validates extractor output after
  bbox snapping and drops invalid regions, reporting them in the ingest
  result instead of silently persisting garbage;
- the harness protocol (IngestSessionService) validates agent
  submissions with a closed schema and returns structured errors so the
  agent can repair and resubmit.

Bboxes are BOTTOMLEFT `[left, top, right, bottom]` with `top >= bottom`,
matching docling and the rest of the silver layer.
"""
from __future__ import annotations

import math
from typing import Any

#: The closed set of region kinds the gold layer accepts. Mirrors the
#: prompt in the OpenAI region extractor and the docs.
REGION_KINDS: tuple[str, ...] = (
    "chart",
    "spec_block",
    "table",
    "figure",
    "diagram",
    "text",
)

MAX_TITLE_LEN = 300
MAX_DESCRIPTION_LEN = 4000
MAX_LIST_FIELD_ITEMS = 50
MAX_LIST_ITEM_LEN = 200


def _err(index: int, field: str, message: str) -> dict[str, Any]:
    return {"region_index": index, "field": field, "message": message}


def bbox_error(bbox: Any) -> str | None:
    """Return a message when `bbox` is not a valid BOTTOMLEFT box, else None."""
    if not isinstance(bbox, list) or len(bbox) != 4:
        return "bbox must be a list of 4 numbers [left, top, right, bottom]"
    for v in bbox:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            return "bbox values must be finite numbers"
    left, top, right, bottom = (float(v) for v in bbox)
    if left > right:
        return f"bbox left ({left}) must be <= right ({right})"
    if bottom > top:
        return f"bbox is BOTTOMLEFT: top ({top}) must be >= bottom ({bottom})"
    return None


def _check_string_list(
    value: Any, *, index: int, field: str, errors: list[dict[str, Any]],
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(_err(index, field, f"{field} must be a list of strings"))
        return
    if len(value) > MAX_LIST_FIELD_ITEMS:
        errors.append(_err(index, field, f"{field} has too many items (max {MAX_LIST_FIELD_ITEMS})"))
        return
    for item in value:
        if not isinstance(item, str) or len(item) > MAX_LIST_ITEM_LEN:
            errors.append(_err(index, field, f"{field} items must be strings (max {MAX_LIST_ITEM_LEN} chars)"))
            return


def validate_region(region: Any, *, index: int = 0) -> list[dict[str, Any]]:
    """Validate one region dict against the shared gold schema.

    Returns a list of structured errors (empty when the region is valid):
    `{"region_index": int, "field": str, "message": str}`. Extra fields
    are tolerated here (the keyed pipeline persists crops and other
    annotations); harness submissions go through the stricter
    closed-schema check in the session service.
    """
    if not isinstance(region, dict):
        return [_err(index, "", "region must be an object")]

    errors: list[dict[str, Any]] = []

    kind = region.get("kind")
    if not isinstance(kind, str) or kind not in REGION_KINDS:
        errors.append(_err(
            index, "kind",
            f"kind must be one of {'|'.join(REGION_KINDS)} (got {kind!r})",
        ))

    title = region.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(_err(index, "title", "title is required and must be a non-empty string"))
    elif len(title) > MAX_TITLE_LEN:
        errors.append(_err(index, "title", f"title too long (max {MAX_TITLE_LEN} chars)"))

    description = region.get("description")
    if description is not None:
        if not isinstance(description, str):
            errors.append(_err(index, "description", "description must be a string"))
        elif len(description) > MAX_DESCRIPTION_LEN:
            errors.append(_err(
                index, "description", f"description too long (max {MAX_DESCRIPTION_LEN} chars)",
            ))

    bbox = region.get("bbox")
    if bbox is None:
        bbox = region.get("approximate_bbox")
    msg = bbox_error(bbox)
    if msg:
        errors.append(_err(index, "bbox", msg))

    region_id = region.get("id")
    if region_id is not None and (not isinstance(region_id, str) or not region_id.strip()):
        errors.append(_err(index, "id", "id must be a non-empty string when present"))

    _check_string_list(region.get("tags"), index=index, field="tags", errors=errors)
    _check_string_list(region.get("entities"), index=index, field="entities", errors=errors)

    return errors


def validate_regions(regions: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a raw extractor result into (valid_regions, errors).

    Tolerant entry point for the keyed pipeline: invalid regions are
    dropped (reported via the returned errors), valid ones pass through
    untouched.
    """
    if not isinstance(regions, list):
        return [], [_err(0, "", "regions must be a list")]
    valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for i, region in enumerate(regions):
        region_errors = validate_region(region, index=i)
        if region_errors:
            errors.extend(region_errors)
        else:
            valid.append(region)
    return valid, errors
