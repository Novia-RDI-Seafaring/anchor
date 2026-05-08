"""Hierarchy-aware layout for the SysML canvas batch.

The mapper emits nodes with placeholder coordinates and adds edges for
inheritance / subject / satisfy relations. This module reads those
edges and assigns final (x, y) coordinates so the rendered diagram
follows SysML/UML conventions:

- Inheritance flows upward — superclass at the top, subclasses below.
- Siblings at the same level lay out left-to-right.
- Requirements anchor adjacent to their subject block (one column to the
  right, vertically centred on the subject).
- Packages render as background containers; their position is the
  bounding box of their members.

Phase 1 stays simple: a single connected hierarchy renders cleanly. For
multiple disconnected hierarchies in the same batch we lay them side
by side. Layered orthogonal routing / Sugiyama is a Phase 2 win.
"""
from __future__ import annotations

from collections import defaultdict

from anchor.extensions.anchor_sysml.core.schemas import CanvasBatch


CELL_W = 280
CELL_H = 220
GUTTER_X = 60
GUTTER_Y = 80
REQ_OFFSET_X = CELL_W + GUTTER_X * 2  # column of space between blocks and reqs


def apply_layout(batch: CanvasBatch, *, x_offset: float = 0, y_offset: float = 0) -> None:
    """Mutate ``batch`` in place: assign (x, y) on every node spec."""

    nodes_by_id = {n.id: n for n in batch.nodes}

    # Inheritance: source = subclass, target = superclass.
    parents: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    for e in batch.edges:
        if e.data.get("marker") == "inheritance":
            parents[e.source].append(e.target)
            children[e.target].append(e.source)

    # Subject: source = requirement, target = block. Used to attach
    # requirements alongside their subject after blocks are placed.
    subject_of: dict[str, str] = {}
    for e in batch.edges:
        if e.data.get("marker") == "subject":
            subject_of[e.source] = e.target

    # 1. Compute level for each block via BFS from roots.
    block_ids = [n.id for n in batch.nodes if n.node_type == "sysml:block"]
    level: dict[str, int] = {}
    roots = [bid for bid in block_ids if not parents.get(bid)]
    queue = [(r, 0) for r in roots]
    while queue:
        nid, lvl = queue.pop(0)
        if nid in level and level[nid] >= lvl:
            continue
        level[nid] = lvl
        for child in children.get(nid, []):
            queue.append((child, lvl + 1))

    # Any blocks not reached (cycles / external supers) land at level 0.
    for bid in block_ids:
        level.setdefault(bid, 0)

    # 2. Group blocks by level and lay them out left-to-right per row.
    by_level: dict[int, list[str]] = defaultdict(list)
    for bid in block_ids:
        by_level[level[bid]].append(bid)

    for lvl, ids in by_level.items():
        # Stable order: keep the order they were emitted so the user gets
        # left-to-right what they wrote in the file.
        ids.sort(key=lambda i: batch.nodes.index(nodes_by_id[i]))
        for col, nid in enumerate(ids):
            n = nodes_by_id[nid]
            n.x = x_offset + col * (CELL_W + GUTTER_X)
            n.y = y_offset + lvl * (CELL_H + GUTTER_Y)

    # 3. Requirements: place at the same y as their subject, REQ_OFFSET_X
    # to the right. If a level/row already exists at that x, push down by
    # rows until clear.
    req_ids = [n.id for n in batch.nodes if n.node_type == "sysml:requirement"]
    block_xy = {bid: (nodes_by_id[bid].x, nodes_by_id[bid].y) for bid in block_ids}
    used_xy: set[tuple[float, float]] = set(block_xy.values())
    for rid in req_ids:
        target = subject_of.get(rid)
        if target and target in block_xy:
            sx, sy = block_xy[target]
            x = sx + REQ_OFFSET_X
            y = sy
        else:
            # No subject — stack to the right of everything else.
            max_x = max((n.x for n in batch.nodes if n.node_type == "sysml:block"), default=x_offset)
            x = max_x + REQ_OFFSET_X
            y = y_offset
        # Avoid stacking two requirements at the same point.
        while (x, y) in used_xy:
            y += CELL_H + GUTTER_Y
        used_xy.add((x, y))
        nodes_by_id[rid].x = x
        nodes_by_id[rid].y = y

    # 4. Packages render as background containers behind their members.
    # Compute bbox of each package's children (blocks + reqs) and size
    # the package to fit. We approximate by listing every block / req
    # that lives in the package's qualified-name prefix.
    pkg_ids = [n.id for n in batch.nodes if n.node_type == "sysml:package"]
    for pid in pkg_ids:
        pkg = nodes_by_id[pid]
        prefix = pkg.data.get("qualified_name") or pkg.label
        members = [
            n for n in batch.nodes
            if n.id != pid
            and isinstance(n.data.get("qualified_name"), str)
            and n.data["qualified_name"].startswith(f"{prefix}::")
        ]
        if not members:
            pkg.x = x_offset
            pkg.y = y_offset
            continue
        min_x = min(m.x for m in members) - 40
        min_y = min(m.y for m in members) - 60
        max_x = max(m.x + CELL_W for m in members) + 40
        max_y = max(m.y + CELL_H for m in members) + 40
        pkg.x = min_x
        pkg.y = min_y
        # The package primitive reads width/height from `data`. Stash both
        # there so the dashed container sizes to fit its members.
        pkg.data["width"] = max_x - min_x
        pkg.data["height"] = max_y - min_y


__all__ = ["apply_layout"]
