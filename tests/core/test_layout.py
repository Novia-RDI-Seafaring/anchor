"""Pure-core layout — synthetic node/edge fixtures only."""
from __future__ import annotations

import pytest

from anchor.core.workspace.layout import (
    EdgeLike,
    NodeLike,
    organize_subtree,
)


def _node(
    nid: str, x: float = 0.0, y: float = 0.0,
    width: float | None = None, height: float | None = None,
) -> NodeLike:
    return NodeLike(id=nid, x=x, y=y, width=width, height=height)


# Default node footprint the layout falls back to when size is unknown.
# Mirrors the layout module constants so the overlap assertions below stay
# in sync if the constants are retuned.
from anchor.core.workspace.layout import NODE_H, NODE_W  # noqa: E402


def _overlaps(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> bool:
    """Axis-aligned bbox overlap test on React-Flow top-left coords."""
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _edge(a: str, b: str) -> EdgeLike:
    # Direction-agnostic on purpose — layout treats edges as undirected
    # under the default ``direction="any"``. The direction-aware tests
    # below assert the source/target choice explicitly.
    return EdgeLike(source=a, target=b)


def test_unknown_root_returns_empty():
    out = organize_subtree([_node("a")], [], "ghost")
    assert out == {}


def test_root_with_no_descendants_returns_empty():
    out = organize_subtree([_node("a"), _node("b")], [], "a")
    assert out == {}


def test_vertical_two_children_are_symmetric_about_root():
    out = organize_subtree(
        [_node("r", x=0, y=0), _node("a"), _node("b")],
        [_edge("a", "r"), _edge("b", "r")],
        "r",
        orientation="vertical",
    )
    assert set(out.keys()) == {"a", "b"}
    ax, ay = out["a"]
    bx, by = out["b"]
    # Same level
    assert ay == by
    # Symmetric about x=0 — child positions sort deterministically so the
    # children appear at +/- half a slot width either side of the root.
    assert abs(ax + bx) < 1e-9


def test_root_position_is_preserved_as_offset():
    out = organize_subtree(
        [_node("r", x=100, y=200), _node("a"), _node("b")],
        [_edge("a", "r"), _edge("b", "r")],
        "r",
    )
    # Children sit symmetrically about the root's x=100 and one level down.
    ax, _ = out["a"]
    bx, _ = out["b"]
    assert abs((ax + bx) / 2.0 - 100.0) < 1e-9


def test_three_level_tree_no_overlap():
    # r -> {a, b}; a -> {c, d}; b -> {e}
    nodes = [_node(n) for n in ("r", "a", "b", "c", "d", "e")]
    edges = [
        _edge("a", "r"), _edge("b", "r"),
        _edge("c", "a"), _edge("d", "a"),
        _edge("e", "b"),
    ]
    out = organize_subtree(nodes, edges, "r")
    assert {"a", "b", "c", "d", "e"}.issubset(out.keys())
    # No two distinct nodes at the same x,y (catastrophic overlap is the
    # one regression we want to guard against; finer collision checks are
    # noise given the constants tweak by feel).
    seen: set[tuple[float, float]] = set()
    for nid, xy in out.items():
        assert xy not in seen, f"overlap at {xy} for {nid}"
        seen.add(xy)


def test_horizontal_swaps_axes():
    nodes = [_node("r", x=0, y=0), _node("a"), _node("b")]
    edges = [_edge("a", "r"), _edge("b", "r")]
    vert = organize_subtree(nodes, edges, "r", orientation="vertical")
    horz = organize_subtree(nodes, edges, "r", orientation="horizontal")
    # In vertical, children spread along x and live below in y. In
    # horizontal, they spread along y and live to the right in x.
    ax_v, ay_v = vert["a"]
    bx_v, by_v = vert["b"]
    ax_h, ay_h = horz["a"]
    bx_h, by_h = horz["b"]
    assert ay_v == by_v
    assert ax_h == bx_h  # children share x in horizontal layout
    # In vertical, children are below root (y > 0); horizontal moves them
    # to the right (x > root.x = 0).
    assert ay_v > 0
    assert ax_h > 0


def test_cycle_does_not_loop_forever():
    # a <-> b <-> c, with root a. BFS visits each node once.
    nodes = [_node(n) for n in ("a", "b", "c")]
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "a")]
    out = organize_subtree(nodes, edges, "a")
    # Both other nodes get placed exactly once.
    assert set(out.keys()) == {"b", "c"}


def test_unreachable_nodes_are_not_moved():
    # r — a — b   (and a disconnected c)
    nodes = [_node(n) for n in ("r", "a", "b", "c")]
    edges = [_edge("r", "a"), _edge("a", "b")]
    out = organize_subtree(nodes, edges, "r")
    assert "c" not in out
    assert {"a", "b"}.issubset(out.keys())


# ── direction-aware BFS ────────────────────────────────────────────────
#
# A → B → C → D (a straight chain of edges, source → target).
# Organising from B:
#   - "outgoing": B follows arrows forward → {C, D}.
#   - "incoming": B follows arrows backward → {A}.
#   - "any": original undirected walk → {A, C, D}.

def _chain_abcd():
    nodes = [_node(n) for n in ("a", "b", "c", "d")]
    edges = [_edge("a", "b"), _edge("b", "c"), _edge("c", "d")]
    return nodes, edges


def test_direction_outgoing_only_walks_forward():
    nodes, edges = _chain_abcd()
    out = organize_subtree(nodes, edges, "b", direction="outgoing")
    assert set(out.keys()) == {"c", "d"}


def test_direction_incoming_only_walks_backward():
    nodes, edges = _chain_abcd()
    out = organize_subtree(nodes, edges, "b", direction="incoming")
    assert set(out.keys()) == {"a"}


def test_direction_any_preserves_undirected_behaviour():
    nodes, edges = _chain_abcd()
    out = organize_subtree(nodes, edges, "b", direction="any")
    # Same as the default — both endpoints reachable.
    assert set(out.keys()) == {"a", "c", "d"}


def test_default_direction_is_any():
    # Explicit guard: callers that omit `direction` get the v1 behaviour
    # (undirected). Don't silently regress this.
    nodes, edges = _chain_abcd()
    out = organize_subtree(nodes, edges, "b")
    assert set(out.keys()) == {"a", "c", "d"}


def test_outgoing_from_leaf_returns_empty():
    # Reports-to chain: a → b → c, organising "c" with outgoing has no
    # descendants. Sanity-check the "user picked the wrong direction" case.
    nodes = [_node(n) for n in ("a", "b", "c")]
    edges = [_edge("a", "b"), _edge("b", "c")]
    out = organize_subtree(nodes, edges, "c", direction="outgoing")
    assert out == {}


# ── source/anchor node is the fixed root (issue #194) ──────────────────
#
# Organising a source/doc node's children must place them CLEAR of the
# source node, never behind/under it. The source node is the fixed layout
# root: its position never changes and its measured size is honoured so a
# tall doc node (hundreds of px) doesn't swallow its children.

def test_children_clear_a_tall_source_node():
    # A 600px-tall source/doc node at the origin with two children.
    src = _node("src", x=0, y=0, width=320, height=600)
    out = organize_subtree(
        [src, _node("a"), _node("b")],
        [_edge("a", "src"), _edge("b", "src")],
        "src",
    )
    # Every child must sit fully below the source node's bottom edge
    # (y=600), i.e. its top is past the source's measured height.
    for nid in ("a", "b"):
        _, cy = out[nid]
        assert cy >= src.y + src.height, (
            f"{nid} at y={cy} lands inside the 600px source node"
        )


def test_no_child_overlaps_source_bbox():
    # The headline acceptance check: no child's bounding box intersects the
    # source node's bounding box, for a wide AND tall source node.
    src = _node("src", x=50, y=50, width=500, height=400)
    nodes = [src] + [_node(n) for n in ("a", "b", "c", "d")]
    edges = [_edge(n, "src") for n in ("a", "b", "c", "d")]
    out = organize_subtree(nodes, edges, "src")
    for nid in ("a", "b", "c", "d"):
        cx, cy = out[nid]
        assert not _overlaps(
            cx, cy, NODE_W, NODE_H,
            src.x, src.y, src.width, src.height,
        ), f"{nid} bbox at ({cx},{cy}) overlaps the source node"


def test_no_child_overlaps_source_bbox_horizontal():
    # Same guarantee for left-to-right layout: a wide source node must not
    # sit on top of its children.
    src = _node("src", x=50, y=50, width=500, height=400)
    nodes = [src] + [_node(n) for n in ("a", "b", "c")]
    edges = [_edge(n, "src") for n in ("a", "b", "c")]
    out = organize_subtree(nodes, edges, "src", orientation="horizontal")
    for nid in ("a", "b", "c"):
        cx, cy = out[nid]
        assert not _overlaps(
            cx, cy, NODE_W, NODE_H,
            src.x, src.y, src.width, src.height,
        ), f"{nid} bbox at ({cx},{cy}) overlaps the source node (horizontal)"


def test_source_node_is_excluded_from_moves():
    # The fixed root's position is never returned (it does not move).
    src = _node("src", x=123, y=456, width=400, height=300)
    out = organize_subtree(
        [src, _node("a"), _node("b")],
        [_edge("a", "src"), _edge("b", "src")],
        "src",
    )
    assert "src" not in out


def test_messy_subtree_is_de_overlapped():
    # Children seeded at junk overlapping coordinates (a freshly scaffolded
    # canvas) all land at distinct, non-overlapping positions after one
    # organize call.
    src = _node("src", x=0, y=0, width=300, height=500)
    junk = [
        _node("a", x=5, y=5), _node("b", x=6, y=4),
        _node("c", x=4, y=6), _node("d", x=5, y=5),
    ]
    edges = [_edge(n, "src") for n in ("a", "b", "c", "d")]
    out = organize_subtree([src, *junk], edges, "src")
    coords = list(out.values())
    # No two children share a position.
    assert len(set(coords)) == len(coords)
    # And none overlap each other's footprint.
    items = list(out.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (_, (ax, ay)), (_, (bx, by)) = items[i], items[j]
            assert not _overlaps(
                ax, ay, NODE_W, NODE_H, bx, by, NODE_W, NODE_H,
            ), "two organized children overlap each other"


def test_unsupported_direction_raises():
    with pytest.raises(ValueError):
        organize_subtree(
            [_node("r")], [], "r", direction="sideways",  # type: ignore[arg-type]
        )
