"""Pure subtree-layout math — no I/O, no async.

`organize_subtree(nodes, edges, root_id, orientation, direction)` walks the
edge graph from `root_id` and returns the new (x, y) for every reachable
node. The root itself is anchored at its current position; everything
beneath is arranged into a tidy tree.

Edge direction is controlled by the `direction` argument:

  - ``"outgoing"``: only follow edges where ``edge.source == current`` —
    children are nodes the current node points TO. The right mode when the
    canvas convention is ``parent → child`` (flow charts, cause → effect).
  - ``"incoming"``: only follow edges where ``edge.target == current`` —
    children are nodes that point TO the current node. The right mode for
    ``reports to`` org charts where subordinates point at their boss
    (this is the acme-org convention).
  - ``"any"`` (default): undirected projection — follow edges either way.
    Preserves the original v1 behaviour and is the right fallback when the
    canvas mixes conventions or the user doesn't want to think about it.

Cycles are tolerated in every mode: each node is visited at most once and
first encounter wins.

Algorithm (vertical orientation):

1. BFS from root over the undirected projection of the edge set, but
   the *root* is treated as the parent in the resulting tree (Kahn-like —
   first encounter wins). This yields a `parent` map and `children` map.
2. Compute subtree widths bottom-up: `width(leaf) = 1`,
   `width(parent) = sum(width(child))` (clamped to 1).
3. Walk top-down: place the root at its current (x, y); each child gets
   centred under its parent according to its subtree width.

The root is the FIXED layout root: its position never moves and its
*measured* size is honoured so the first level of children is placed
fully clear of its bounding box. Positions are React-Flow top-left
coordinates (matching `align.py`), so children are centred on the root's
visual centre (`root_x + root_w/2`) rather than on its top-left corner,
and the first level drops past the root's actual bottom edge
(`root_y + root_h + gap`) instead of a fixed gap from the root's origin.
Without this, a tall source/doc node (hundreds of px tall) swallows its
children: a fixed `LEVEL_GAP_Y` of 200 leaves them behind/under the node.

Horizontal orientation swaps the role of x and y so the tree grows
left-to-right.

The constants below were chosen by eye for the org-chart shape Anchor
canvases tend to have. They're tunable: bump `LEVEL_GAP` for taller trees,
bump `SIB_GAP` for crowded ones.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping

Orientation = Literal["vertical", "horizontal"]
Direction = Literal["outgoing", "incoming", "any"]

# Visual spacing constants. Tweak by feel — these match what looks tidy on
# the acme-org canvas (~200px wide entity cards).
NODE_W = 200.0
NODE_H = 100.0
LEVEL_GAP_Y = 200.0
LEVEL_GAP_X = 260.0
SIB_GAP_X = 60.0
SIB_GAP_Y = 40.0


@dataclass(frozen=True)
class NodeLike:
    """Just the fields layout actually needs. Keep this narrow so tests
    can pass plain dicts wrapped in NodeLike without standing up a full
    Workspace.

    ``width`` / ``height`` are the node's *measured* size (React-Flow
    top-left coordinates). They default to ``None``; callers that don't
    know a node's size get the ``NODE_W`` / ``NODE_H`` fallback via the
    ``w`` / ``h`` properties. The root's measured size is what lets the
    layout place children clear of a tall source/doc node instead of
    behind it."""
    id: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None

    @property
    def w(self) -> float:
        return self.width if self.width is not None else NODE_W

    @property
    def h(self) -> float:
        return self.height if self.height is not None else NODE_H


@dataclass(frozen=True)
class EdgeLike:
    source: str
    target: str


def _build_adjacency(
    edges: Iterable[EdgeLike], direction: Direction = "any",
) -> dict[str, set[str]]:
    """Adjacency map honouring ``direction``.

    - ``"outgoing"``: ``adj[source]`` adds ``target`` only. Walk follows
      arrows in their natural direction (parent → child convention).
    - ``"incoming"``: ``adj[target]`` adds ``source`` only. Walk follows
      arrows in reverse (subordinate → boss convention, e.g. ``reports to``).
    - ``"any"``: undirected projection — both endpoints are neighbours.
      Preserves the original v1 behaviour.

    The BFS that consumes this map breaks cycles by visiting nodes at most
    once, so first-encounter wins regardless of direction mode."""
    adj: dict[str, set[str]] = {}
    for e in edges:
        if direction == "outgoing":
            adj.setdefault(e.source, set()).add(e.target)
        elif direction == "incoming":
            adj.setdefault(e.target, set()).add(e.source)
        else:  # "any"
            adj.setdefault(e.source, set()).add(e.target)
            adj.setdefault(e.target, set()).add(e.source)
    return adj


def _bfs_tree(
    root_id: str, adj: Mapping[str, set[str]],
) -> tuple[dict[str, str | None], dict[str, list[str]]]:
    """Return (parent, children) maps for the BFS tree rooted at root_id.

    First encounter wins; cycles are silently broken. Nodes unreachable
    from the root are omitted from both maps (callers shouldn't move them)."""
    parent: dict[str, str | None] = {root_id: None}
    children: dict[str, list[str]] = {root_id: []}
    q: deque[str] = deque([root_id])
    while q:
        cur = q.popleft()
        for nb in sorted(adj.get(cur, ())):  # sort for deterministic layout
            if nb in parent:
                continue
            parent[nb] = cur
            children.setdefault(nb, [])
            children[cur].append(nb)
            q.append(nb)
    return parent, children


def _subtree_width(
    node_id: str, children: Mapping[str, list[str]], cache: dict[str, int],
) -> int:
    if node_id in cache:
        return cache[node_id]
    kids = children.get(node_id, [])
    if not kids:
        cache[node_id] = 1
        return 1
    w = sum(_subtree_width(c, children, cache) for c in kids)
    cache[node_id] = max(w, 1)
    return cache[node_id]


def _place_vertical(
    root_id: str, root_x: float, root_y: float,
    children: Mapping[str, list[str]],
    *, root_w: float = NODE_W, root_h: float = NODE_H,
    level_gap: float = LEVEL_GAP_Y,
    sib_gap: float = SIB_GAP_X, node_w: float = NODE_W,
) -> dict[str, tuple[float, float]]:
    """Centred-tree placement, top-down.

    Positions are React-Flow top-left coordinates. Children are centred on
    the root's *visual* centre (``root_x + root_w/2``) and the first level
    is dropped past the root's actual bottom edge (``root_y + root_h``) so
    a tall root (a source/doc node) never sits on top of its children. The
    returned child positions are top-left, so each child's centre is
    converted back by subtracting ``node_w/2``."""
    out: dict[str, tuple[float, float]] = {root_id: (root_x, root_y)}
    width_cache: dict[str, int] = {}
    root_cx = root_x + root_w / 2.0
    # First level clears the root's measured bottom edge; deeper levels use
    # the plain centre-to-centre gap (children below the root all share the
    # default node size, so the fixed gap is fine once we're past the root).
    first_level_top = root_y + root_h + level_gap

    def place_children(node_id: str, x_center: float, kids_top: float) -> None:
        """Centre ``node_id``'s children at ``kids_top`` and recurse.

        ``x_center`` is the parent's visual centre; ``kids_top`` is the
        top-left ``y`` the children's row sits at. The first level is fed
        ``first_level_top`` (past the root's measured bottom edge); deeper
        levels advance by the plain centre-to-centre gap."""
        kids = children.get(node_id, [])
        if not kids:
            return
        total_units = sum(_subtree_width(c, children, width_cache) for c in kids)
        slot_w = node_w + sib_gap
        cursor = x_center - (total_units * slot_w) / 2.0
        next_top = kids_top + NODE_H + level_gap
        for c in kids:
            cw = _subtree_width(c, children, width_cache)
            cx = cursor + (cw * slot_w) / 2.0
            out[c] = (cx - node_w / 2.0, kids_top)
            place_children(c, cx, next_top)
            cursor += cw * slot_w

    place_children(root_id, root_cx, first_level_top)
    return out


def _place_horizontal(
    root_id: str, root_x: float, root_y: float,
    children: Mapping[str, list[str]],
    *, root_w: float = NODE_W, root_h: float = NODE_H,
    level_gap: float = LEVEL_GAP_X,
    sib_gap: float = SIB_GAP_Y, node_h: float = NODE_H,
) -> dict[str, tuple[float, float]]:
    """Swap roles of x/y: tree grows left-to-right.

    The transpose means the vertical placer's "down past the root's
    height" becomes "right past the root's width", so we feed the root's
    *width* in as the swapped-axis ``root_h`` and its *height* as the
    swapped-axis ``root_w``."""
    # Reuse vertical placement on a swapped axis, then swap back.
    # Effectively: vertical with root_x ↔ root_y, then transpose.
    vert = _place_vertical(
        root_id, root_y, root_x, children,
        root_w=root_h, root_h=root_w,
        level_gap=level_gap, sib_gap=sib_gap, node_w=node_h,
    )
    return {nid: (y, x) for nid, (x, y) in vert.items()}


# ── Server-side auto-placement ──────────────────────────────────────────────
#
# Issue #189: an agent adding nodes can't perceive the layout, so hand-picked
# (x, y) pile up on existing nodes. ``find_free_position`` scans a spiral of
# grid cells outward from an origin and returns the first slot whose bounding
# box doesn't overlap any existing node. The service calls this when add_node
# gets no x/y (or place="auto") and returns the resolved position so the agent
# can track the layout.

PLACE_GAP = 40.0  # breathing room kept between a placed node and its neighbours


def _overlaps(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
    gap: float,
) -> bool:
    """Axis-aligned box overlap test, inflated by ``gap`` on every side."""
    return (
        ax < bx + bw + gap
        and ax + aw + gap > bx
        and ay < by + bh + gap
        and ay + ah + gap > by
    )


def find_free_position(
    nodes: Iterable[NodeLike],
    *,
    width: float | None = None,
    height: float | None = None,
    origin: tuple[float, float] = (0.0, 0.0),
    gap: float = PLACE_GAP,
    max_ring: int = 60,
) -> tuple[float, float]:
    """Return an (x, y) for a new node of ``width`` x ``height`` that does not
    overlap any node in ``nodes``.

    The search walks grid cells in expanding square rings around ``origin``
    (ring 0 is the origin itself), stepping by the node's footprint plus
    ``gap`` so adjacent slots never touch. The first non-overlapping cell
    wins; positions are React-Flow top-left coordinates, matching the rest of
    the layout math. With an empty canvas the origin is returned unchanged.

    ``max_ring`` bounds the spiral so a pathologically dense canvas can't spin
    forever; if every scanned cell is occupied the last candidate is returned
    (it will still be far out past the cluster)."""
    placed = [n for n in nodes]
    w = width if width is not None else NODE_W
    h = height if height is not None else NODE_H
    ox, oy = origin
    step_x = w + gap
    step_y = h + gap

    def free_at(x: float, y: float) -> bool:
        for n in placed:
            if _overlaps(x, y, w, h, n.x, n.y, n.w, n.h, gap):
                return False
        return True

    if free_at(ox, oy):
        return (ox, oy)

    last = (ox, oy)
    for ring in range(1, max_ring + 1):
        # Walk the cells on the perimeter of the square ring at this radius.
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) != ring:
                    continue  # interior cells already scanned by smaller rings
                cx = ox + dx * step_x
                cy = oy + dy * step_y
                last = (cx, cy)
                if free_at(cx, cy):
                    return (cx, cy)
    return last


def organize_subtree(
    nodes: Iterable[NodeLike], edges: Iterable[EdgeLike],
    root_id: str, *, orientation: Orientation = "vertical",
    direction: Direction = "any",
) -> dict[str, tuple[float, float]]:
    """Compute new positions for every descendant of `root_id`.

    ``direction`` controls how the BFS walks the edge set — see the module
    docstring. Default ``"any"`` keeps v1 behaviour (undirected projection).

    Returns a {node_id: (x, y)} dict that EXCLUDES the root (its position
    is unchanged). Returns an empty dict if the root has no descendants
    in the chosen ``direction`` or doesn't appear in the node set."""
    if direction not in ("outgoing", "incoming", "any"):
        raise ValueError(
            f"unsupported direction: {direction!r} "
            "(use 'outgoing', 'incoming', or 'any')",
        )
    nodes_by_id = {n.id: n for n in nodes}
    if root_id not in nodes_by_id:
        return {}
    adj = _build_adjacency(edges, direction)
    _, children = _bfs_tree(root_id, adj)
    if not children.get(root_id):
        return {}

    root = nodes_by_id[root_id]
    if orientation == "vertical":
        placed = _place_vertical(
            root_id, root.x, root.y, children,
            root_w=root.w, root_h=root.h,
        )
    else:
        placed = _place_horizontal(
            root_id, root.x, root.y, children,
            root_w=root.w, root_h=root.h,
        )

    # Strip the root and filter to actually-existing nodes (the BFS may
    # have visited an edge whose endpoint was deleted out from under us).
    return {
        nid: xy for nid, xy in placed.items()
        if nid != root_id and nid in nodes_by_id
    }
