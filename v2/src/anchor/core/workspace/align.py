"""Pure align / distribute math — no I/O, no async.

Mirror of `web/src/canvas/align.ts`. Both implementations are kept tiny on
purpose so the parity is verifiable by reading them side by side.

``align_nodes(nodes, anchor)`` snaps every node in the input to the anchor
line computed from the bounding box of the input set. ``"top"`` /
``"bottom"`` / ``"left"`` / ``"right"`` align by edge; ``"center-h"`` (centre
the y) and ``"center-v"`` (centre the x) align by midline.

``distribute_nodes(nodes, axis)`` spreads the nodes evenly between the
leftmost and rightmost (or topmost / bottommost) of the input set. The end
nodes don't move; the middle ones are spaced so their *centres* are
equidistant along the chosen axis. Needs at least three nodes.

Both functions return ``{node_id: (x, y)}`` containing only the nodes whose
position actually changes. That keeps the event flurry tight — no NodeMoved
for a node that's already on the line.

Node width / height default to 100 when missing, matching the v2 React Flow
defaults and the spec note ("Make sure to use node width/height (default to
100 if undefined)"). Position semantics match React Flow: ``x``/``y`` is the
top-left of the node's bounding box.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

Anchor = Literal["top", "bottom", "left", "right", "center-h", "center-v"]
Axis = Literal["horizontal", "vertical"]

DEFAULT_DIM = 100.0


@dataclass(frozen=True)
class SelectedNode:
    """Just the fields align / distribute actually need."""
    id: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None

    @property
    def w(self) -> float:
        return self.width if self.width is not None else DEFAULT_DIM

    @property
    def h(self) -> float:
        return self.height if self.height is not None else DEFAULT_DIM


def align_nodes(
    nodes: Iterable[SelectedNode], anchor: Anchor,
) -> dict[str, tuple[float, float]]:
    """Return {node_id: (x, y)} for nodes whose position changes.

    With fewer than two nodes there's nothing to align against — return an
    empty dict so the service emits no events."""
    items = list(nodes)
    if len(items) < 2:
        return {}

    if anchor == "top":
        target_y = min(n.y for n in items)
        return _diff(items, lambda n: (n.x, target_y))
    if anchor == "bottom":
        target_bottom = max(n.y + n.h for n in items)
        return _diff(items, lambda n: (n.x, target_bottom - n.h))
    if anchor == "left":
        target_x = min(n.x for n in items)
        return _diff(items, lambda n: (target_x, n.y))
    if anchor == "right":
        target_right = max(n.x + n.w for n in items)
        return _diff(items, lambda n: (target_right - n.w, n.y))
    if anchor == "center-h":
        # "Center horizontally" = align vertical midlines (same y centre).
        # The y centre lands halfway between the topmost top and bottommost
        # bottom of the selection — visually the line is the selection's
        # mid-y.
        top = min(n.y for n in items)
        bottom = max(n.y + n.h for n in items)
        mid_y = (top + bottom) / 2.0
        return _diff(items, lambda n: (n.x, mid_y - n.h / 2.0))
    if anchor == "center-v":
        # "Center vertically" = align horizontal midlines (same x centre).
        left = min(n.x for n in items)
        right = max(n.x + n.w for n in items)
        mid_x = (left + right) / 2.0
        return _diff(items, lambda n: (mid_x - n.w / 2.0, n.y))
    raise ValueError(
        f"unsupported anchor: {anchor!r} "
        "(use 'top', 'bottom', 'left', 'right', 'center-h', 'center-v')",
    )


def distribute_nodes(
    nodes: Iterable[SelectedNode], axis: Axis,
) -> dict[str, tuple[float, float]]:
    """Spread node centres evenly along ``axis`` between the extreme nodes.

    The endpoints (smallest and largest centre on the chosen axis) stay
    put. Middle nodes are slotted so their centres lie on equally-spaced
    points along the line. Requires at least three nodes."""
    items = list(nodes)
    if len(items) < 3:
        return {}

    if axis == "horizontal":
        sorted_items = sorted(items, key=lambda n: n.x + n.w / 2.0)
        first_centre = sorted_items[0].x + sorted_items[0].w / 2.0
        last_centre = sorted_items[-1].x + sorted_items[-1].w / 2.0
        step = (last_centre - first_centre) / (len(sorted_items) - 1)
        moves: dict[str, tuple[float, float]] = {}
        for i, n in enumerate(sorted_items):
            target_centre = first_centre + i * step
            new_x = target_centre - n.w / 2.0
            if new_x != n.x:
                moves[n.id] = (new_x, n.y)
        return moves

    if axis == "vertical":
        sorted_items = sorted(items, key=lambda n: n.y + n.h / 2.0)
        first_centre = sorted_items[0].y + sorted_items[0].h / 2.0
        last_centre = sorted_items[-1].y + sorted_items[-1].h / 2.0
        step = (last_centre - first_centre) / (len(sorted_items) - 1)
        moves = {}
        for i, n in enumerate(sorted_items):
            target_centre = first_centre + i * step
            new_y = target_centre - n.h / 2.0
            if new_y != n.y:
                moves[n.id] = (n.x, new_y)
        return moves

    raise ValueError(
        f"unsupported axis: {axis!r} (use 'horizontal' or 'vertical')",
    )


def _diff(
    items: list[SelectedNode],
    target: "callable[[SelectedNode], tuple[float, float]]",  # noqa: F821
) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for n in items:
        nx, ny = target(n)
        if nx != n.x or ny != n.y:
            out[n.id] = (nx, ny)
    return out
