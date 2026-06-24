"""Shared bbox-alias and region-normalisation helpers.

Both FsDocStore and MemoryDocStore apply the same two-step normalisation when
reading or writing region lists:

1. ``_with_bbox_alias`` promotes ``approximate_bbox`` to ``bbox`` when the
   region has no ``bbox`` key yet (legacy field name emitted by early region
   extractors and by the harness protocol).
2. ``_normalise_regions`` applies the alias to every element of a region list,
   tolerating non-list input by returning it unchanged.

Keep the logic here; import from both stores to avoid drift.
"""
from __future__ import annotations

from typing import Any


def _with_bbox_alias(region: dict[str, Any]) -> dict[str, Any]:
    if "bbox" in region or "approximate_bbox" not in region:
        return region
    bbox = region.get("approximate_bbox")
    if not (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(isinstance(v, (int, float)) for v in bbox)
    ):
        return region
    return {**region, "bbox": [float(v) for v in bbox]}


def _normalise_regions(regions: Any) -> Any:
    if not isinstance(regions, list):
        return regions
    return [_with_bbox_alias(r) if isinstance(r, dict) else r for r in regions]
