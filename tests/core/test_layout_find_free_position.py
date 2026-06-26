"""find_free_position — server-side non-overlapping placement (#189)."""
from __future__ import annotations

from anchor.core.workspace.layout import NODE_H, NODE_W, NodeLike, find_free_position


def _overlap(a, b, gap=0.0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (
        ax < bx + bw + gap
        and ax + aw + gap > bx
        and ay < by + bh + gap
        and ay + ah + gap > by
    )


def test_empty_canvas_returns_origin():
    assert find_free_position([], origin=(10.0, 20.0)) == (10.0, 20.0)


def test_avoids_a_single_node_at_origin():
    occupied = [NodeLike(id="a", x=0.0, y=0.0, width=NODE_W, height=NODE_H)]
    x, y = find_free_position(occupied, width=NODE_W, height=NODE_H)
    assert not _overlap((x, y, NODE_W, NODE_H), (0.0, 0.0, NODE_W, NODE_H))


def test_packs_many_without_overlap():
    placed: list[NodeLike] = []
    for i in range(12):
        x, y = find_free_position(placed, width=120.0, height=80.0)
        # Must clear every already-placed node.
        for n in placed:
            assert not _overlap((x, y, 120.0, 80.0), (n.x, n.y, n.w, n.h))
        placed.append(NodeLike(id=str(i), x=x, y=y, width=120.0, height=80.0))
    assert len(placed) == 12


def test_uses_default_size_when_unset():
    occupied = [NodeLike(id="a", x=0.0, y=0.0)]
    x, y = find_free_position(occupied)
    assert (x, y) != (0.0, 0.0)
