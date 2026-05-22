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
    Workspace."""
    id: str
    x: float
    y: float


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
    *, level_gap: float = LEVEL_GAP_Y,
    sib_gap: float = SIB_GAP_X, node_w: float = NODE_W,
) -> dict[str, tuple[float, float]]:
    """Centred-tree placement, top-down."""
    out: dict[str, tuple[float, float]] = {root_id: (root_x, root_y)}
    width_cache: dict[str, int] = {}

    def recurse(node_id: str, x_center: float, y: float) -> None:
        kids = children.get(node_id, [])
        if not kids:
            return
        total_units = sum(_subtree_width(c, children, width_cache) for c in kids)
        slot_w = node_w + sib_gap
        total_width = total_units * slot_w
        cursor = x_center - total_width / 2.0
        next_y = y + level_gap
        for c in kids:
            cw = _subtree_width(c, children, width_cache)
            cx = cursor + (cw * slot_w) / 2.0
            out[c] = (cx, next_y)
            recurse(c, cx, next_y)
            cursor += cw * slot_w

    recurse(root_id, root_x, root_y)
    return out


def _place_horizontal(
    root_id: str, root_x: float, root_y: float,
    children: Mapping[str, list[str]],
    *, level_gap: float = LEVEL_GAP_X,
    sib_gap: float = SIB_GAP_Y, node_h: float = NODE_H,
) -> dict[str, tuple[float, float]]:
    """Swap roles of x/y: tree grows left-to-right."""
    # Reuse vertical placement on a swapped axis, then swap back.
    # Effectively: vertical with root_x ↔ root_y, then transpose.
    vert = _place_vertical(
        root_id, root_y, root_x, children,
        level_gap=level_gap, sib_gap=sib_gap, node_w=node_h,
    )
    return {nid: (y, x) for nid, (x, y) in vert.items()}


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
        placed = _place_vertical(root_id, root.x, root.y, children)
    else:
        placed = _place_horizontal(root_id, root.x, root.y, children)

    # Strip the root and filter to actually-existing nodes (the BFS may
    # have visited an edge whose endpoint was deleted out from under us).
    return {
        nid: xy for nid, xy in placed.items()
        if nid != root_id and nid in nodes_by_id
    }
