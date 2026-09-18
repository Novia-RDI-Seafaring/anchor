"""Validate table associations once, at the silver normalization boundary.

Extractor row numbers are hypotheses. A complete, ordered column supplies
independent physical row anchors; every eligible column must agree on one
assignment. Spans constrain that assignment and are never split or shifted.
Downstream consumers read certified pairs, not a freshly inferred grid.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any

TOPOLOGY_VERSION = 1
_ACCEPTED = {"valid", "reconciled"}
_STRUCTURE = (
    "row",
    "col",
    "row_span",
    "col_span",
    "row_end",
    "col_end",
    "column_header",
    "row_header",
    "row_section",
)


def normalize_table(table: dict[str, Any]) -> dict[str, Any]:
    """Return canonical cells and an auditable, content-bound topology verdict.

    Only this ingest operation may issue a verdict. Existing gold without a
    current verdict requires regeneration, not opportunistic read-time repair.
    """
    if topology_status(table)["status"] in _ACCEPTED:
        return deepcopy(table)
    cells = deepcopy(table.get("cells", []))
    out = {**table, "cells": cells}

    def finish(status: str, reason: str) -> dict[str, Any]:
        pairs = _pairs(cells) if status in _ACCEPTED else []
        out["table_topology"] = {
            "version": TOPOLOGY_VERSION,
            "status": status,
            "reason": reason,
            "pairs": pairs,
            "digest": _digest(cells, pairs),
        }
        return out

    if not isinstance(cells, list) or not cells:
        return finish("invalid", "No table cells")
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            return finish("invalid", "Non-object cell")
        cell["cell_id"] = f"c{index}"
        if "row_span" not in cell or "col_span" not in cell:
            return finish("ambiguous", "Missing cell span provenance; re-extract the table")
        for axis in ("row", "col"):
            start = cell.get(axis)
            span = cell.get(f"{axis}_span", 1)
            end = cell.get(
                f"{axis}_end", start + span if _integer(start) and _integer(span) else None
            )
            if not (
                _integer(start)
                and start >= 0
                and _integer(span)
                and span > 0
                and _integer(end)
                and end == start + span
            ):
                return finish("invalid", "Inconsistent cell offsets or spans")
            cell[f"{axis}_span"], cell[f"{axis}_end"] = span, end
        for flag in ("column_header", "row_header", "row_section"):
            cell.setdefault(flag, False)
            if not isinstance(cell[flag], bool):
                return finish("invalid", "Non-boolean structural flag")
        if not isinstance(cell.get("text"), str):
            return finish("invalid", "Non-text cell")
        cell["source_structure"] = {key: cell[key] for key in _STRUCTURE}
        # Empty placeholders cannot supply physical evidence or semantic pairs.
        if cell["text"].strip() and not _bbox(cell.get("bbox")):
            return finish("ambiguous", "Nonempty cell has no usable physical geometry")

    rows = table.get("num_rows", max(c["row_end"] for c in cells))
    cols = table.get("num_cols", max(c["col_end"] for c in cells))
    if not (_integer(rows) and _integer(cols) and 0 < rows <= 10000 and 0 < cols <= 1000):
        return finish("invalid", "Invalid table dimensions")
    out.update(num_rows=rows, num_cols=cols)
    if any(c["row_end"] > rows or c["col_end"] > cols for c in cells):
        return finish("invalid", "Cell extends outside declared table grid")
    if _collides(cells):
        return finish("invalid", "Overlapping logical cell spans")
    visible = [c for c in cells if c["text"].strip()]
    if not visible:
        return finish("ambiguous", "No physical row evidence")
    boundary = table.get("bbox")
    if not _bbox(boundary) or any(
        c["bbox"][0] < boundary[0]
        or c["bbox"][1] < boundary[1]
        or c["bbox"][2] > boundary[2]
        or c["bbox"][3] > boundary[3]
        for c in visible
    ):
        return finish("ambiguous", "Cell geometry is not contained by its table boundary")

    anchors = _anchor_columns(visible, rows, cols)
    if not anchors:
        return finish("ambiguous", "No complete, physically ordered row anchor column")
    assignments = []
    for rail in anchors:
        assignment = _assign_rows(visible, rail)
        if assignment is None:
            return finish("ambiguous", "Cell geometry does not identify exactly one physical row")
        assignments.append(assignment)
    if any(mapping != assignments[0] for mapping in assignments[1:]):
        return finish("ambiguous", "Physical anchor columns disagree")

    mapping = assignments[0]
    changed = any(mapping[c["cell_id"]] != c["row"] for c in visible)
    if changed and any(c["row_span"] > 1 or c["col_span"] > 1 for c in cells):
        return finish("ambiguous", "Reindexing a table with merged cells is not justified")
    for cell in visible:
        cell["row"] = mapping[cell["cell_id"]]
        cell["row_end"] = cell["row"] + cell["row_span"]
    if _collides(cells) or not _column_geometry_agrees(visible):
        # Retain extractor coordinates as evidence on a rejected repair.
        for cell in visible:
            cell.update(cell["source_structure"])
        return finish(
            "invalid", "Physical assignment conflicts with column order or grid occupancy"
        )
    if changed and not _moved_headers_supported(visible):
        for cell in visible:
            cell.update(cell["source_structure"])
        return finish("ambiguous", "Moved header annotation lacks structural corroboration")
    return finish(
        "reconciled" if changed else "valid",
        "Unique physical row assignment agrees across complete anchor columns",
    )


def topology_status(table: dict[str, Any]) -> dict[str, Any]:
    """Report validity without repairing old or subsequently edited artifacts."""
    verdict = table.get("table_topology")
    if not isinstance(verdict, dict) or verdict.get("version") != TOPOLOGY_VERSION:
        return {
            "version": TOPOLOGY_VERSION,
            "status": "unvalidated",
            "reason": "Table topology requires re-ingest with the current extractor",
        }
    if verdict.get("digest") != _digest(table.get("cells"), verdict.get("pairs")):
        return {
            "version": TOPOLOGY_VERSION,
            "status": "unvalidated",
            "reason": "Table cells changed since topology validation; regenerate derived artifacts",
        }
    return verdict


def validated_pairs(table: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Read only upstream-certified key/value relationships, including after a slice."""
    verdict = topology_status(table)
    if verdict["status"] not in _ACCEPTED:
        return []
    by_id = {c["cell_id"]: c for c in table["cells"]}
    return [(by_id[p["key"]], by_id[p["value"]]) for p in verdict["pairs"]]


def select_table_cells(table: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    """Project a validated table without inventing new associations in a slice."""
    verdict = deepcopy(topology_status(table))
    ids = {c.get("cell_id") for c in selected}
    pairs = [p for p in verdict.get("pairs", []) if p["key"] in ids and p["value"] in ids]
    verdict.update(pairs=pairs, digest=_digest(selected, pairs))
    return {"cells": deepcopy(selected), "table_topology": verdict}


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in value
        )
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _digest(cells: Any, pairs: Any) -> str:
    data = json.dumps([cells, pairs], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _collides(cells: list[dict[str, Any]]) -> bool:
    # Compare rectangles instead of expanding spans into potentially huge grids.
    for i, a in enumerate(cells):
        for b in cells[i + 1 :]:
            if max(a["row"], b["row"]) < min(a["row_end"], b["row_end"]) and max(
                a["col"], b["col"]
            ) < min(a["col_end"], b["col_end"]):
                return True
    return False


def _anchor_columns(
    cells: list[dict[str, Any]], rows: int, cols: int
) -> list[list[dict[str, Any]]]:
    rails = []
    for col in range(cols):
        rail = sorted(
            (
                c
                for c in cells
                if c["row_span"] == 1
                and (
                    c["col"] == col
                    and c["col_span"] == 1
                    or c["col"] == 0
                    and c["col_span"] == cols
                    and (c["column_header"] or c["row_section"])
                )
            ),
            key=lambda c: c["row"],
        )
        if [c["row"] for c in rail] == list(range(rows)) and all(
            a["bbox"][3] <= b["bbox"][1] for a, b in zip(rail, rail[1:], strict=False)
        ):
            rails.append(rail)
    return rails


def _assign_rows(cells: list[dict[str, Any]], rail: list[dict[str, Any]]) -> dict[str, int] | None:
    mapping = {}
    for cell in cells:
        top, bottom = cell["bbox"][1], cell["bbox"][3]
        if cell["row_span"] > 1:
            group = rail[cell["row"] : cell["row_end"]]
            # Text geometry need not fill a merged rectangle, but it must stay
            # inside its declared row group. Never infer a new span from text.
            if top < group[0]["bbox"][1] or bottom > group[-1]["bbox"][3]:
                return None
            mapping[cell["cell_id"]] = cell["row"]
            continue
        overlaps = []
        for anchor in rail:
            a, b = anchor["bbox"][1], anchor["bbox"][3]
            overlap = min(bottom, b) - max(top, a)
            if overlap > 0:
                overlaps.append((anchor["row"], overlap / min(bottom - top, b - a)))
        # A wrapped cell touching two physical rows is not a nearest-row vote.
        if len(overlaps) != 1 or overlaps[0][1] < 0.5:
            return None
        mapping[cell["cell_id"]] = overlaps[0][0]
    return mapping


def _column_geometry_agrees(cells: list[dict[str, Any]]) -> bool:
    for i, a in enumerate(cells):
        for b in cells[i + 1 :]:
            # Disjoint logical columns must also occupy disjoint x bands.
            if a["col_end"] <= b["col"] and a["bbox"][2] > b["bbox"][0]:
                return False
            if b["col_end"] <= a["col"] and b["bbox"][2] > a["bbox"][0]:
                return False
    return True


def _explicit_label_value(key: dict[str, Any], value: dict[str, Any]) -> bool:
    """A printed label delimiter corroborates a displaced header candidate.

    Preserve the extractor's header flag. The relationship is supported by
    explicit source syntax as well as the validated grid; a generic header
    such as ``Parameter | Model A`` supplies no such evidence.
    """
    return (
        key["text"].rstrip().endswith(":")
        and not key["column_header"]
        and not key["row_section"]
        and value["column_header"]
        and value["source_structure"]["row"] == 0 < value["row"]
    )


def _moved_headers_supported(cells: list[dict[str, Any]]) -> bool:
    for cell in cells:
        source = cell["source_structure"]
        if source["row"] == cell["row"]:
            continue
        if cell["row_section"] or cell["row_header"]:
            return False
        if not cell["column_header"]:
            continue
        # A lone displaced flag is not proof of a false header. Require a
        # printed key delimiter, an otherwise empty heading slot, and body
        # continuation. Keep the original header annotation even when this
        # explicit label/value relationship can be certified independently.
        heading = [c for c in cells if c["row"] == source["row"]]
        peers = [c for c in cells if c["row"] == cell["row"] and c is not cell]
        continuation = [c for c in cells if c["col"] == cell["col"] and c["row"] > cell["row"]]
        if not (
            source["row"] == 0 < cell["row"]
            and len(heading) == 1
            and heading[0]["col"] == 0
            and cell["col"] > 0
            and len(peers) == 1
            and continuation
            and _explicit_label_value(peers[0], cell)
            and not any(
                c["column_header"] or c["row_section"] for c in heading + peers + continuation
            )
        ):
            return False
    return True


def _pairs(cells: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        if cell["text"].strip():
            for row in range(cell["row"], cell["row_end"]):
                rows.setdefault(row, []).append(cell)
    pairs = []
    for row_cells in rows.values():
        ordered = sorted(row_cells, key=lambda c: c["col"])
        # A scalar shape has no column selector. Multiple value cells or a
        # label/value spanning multiple rows cannot be resolved by this API.
        if len(ordered) != 2 or any(c["row_span"] != 1 or c["row_section"] for c in ordered):
            continue
        key, value = ordered
        if key["col"] != 0 or key["col_end"] != value["col"] or value["row_header"]:
            continue
        explicit_label = _explicit_label_value(key, value)
        if (key["column_header"] or value["column_header"]) and not explicit_label:
            continue
        pairs.append(
            {
                "key": key["cell_id"],
                "value": value["cell_id"],
                "basis": "explicit_label_value" if explicit_label else "validated_row",
            }
        )
    return pairs
