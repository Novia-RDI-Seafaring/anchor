"""Pure align / distribute math — synthetic fixtures.

These tests pin the geometry. The end-to-end behaviour (event emission,
causation grouping, error surfaces) is covered separately in
test_workspace_align.py against WorkspaceService.
"""
from __future__ import annotations

import pytest

from anchor.core.workspace.align import (
    SelectedNode,
    align_nodes,
    distribute_nodes,
)


def _n(nid: str, x: float, y: float, w: float | None = None, h: float | None = None) -> SelectedNode:
    return SelectedNode(id=nid, x=x, y=y, width=w, height=h)


# ── align ──────────────────────────────────────────────────────────────────


def test_align_too_few_returns_empty():
    assert align_nodes([_n("a", 0, 0)], "top") == {}


def test_align_top_uses_min_y():
    out = align_nodes(
        [_n("a", 0, 10, 100, 100), _n("b", 20, 30, 100, 100), _n("c", 40, 5, 100, 100)],
        "top",
    )
    # Both a (y=10) and b (y=30) move to y=5; c stays.
    assert out == {"a": (0.0, 5.0), "b": (20.0, 5.0)}


def test_align_bottom_uses_max_bottom():
    # Default size 100×100 if w/h missing.
    out = align_nodes(
        [_n("a", 0, 0), _n("b", 0, 50)],
        "bottom",
    )
    # max bottom = 50 + 100 = 150. 'a' must end at y = 150 - 100 = 50; 'b' stays.
    assert out == {"a": (0.0, 50.0)}


def test_align_left_uses_min_x():
    out = align_nodes(
        [_n("a", 10, 0), _n("b", 50, 0), _n("c", 100, 0)],
        "left",
    )
    assert out == {"b": (10.0, 0.0), "c": (10.0, 0.0)}


def test_align_right_uses_max_right():
    # Sizes matter for right.
    out = align_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 200, 0, 50, 50)],
        "right",
    )
    # max right = max(100, 250) = 250. 'a' new x = 250 - 100 = 150.
    assert out == {"a": (150.0, 0.0)}


def test_align_center_horizontal_centres_y():
    # center-h = same y centre. Two nodes at y=0 (centre 50) and y=100
    # (centre 150). Mid-y = 100. New y for a = 50, new y for b = 50.
    out = align_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 0, 100, 100, 100)],
        "center-h",
    )
    assert out == {"a": (0.0, 50.0), "b": (0.0, 50.0)}


def test_align_center_vertical_centres_x():
    out = align_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 200, 0, 100, 100)],
        "center-v",
    )
    # left=0, right=300, mid_x=150; both new_x = 150 - 50 = 100.
    assert out == {"a": (100.0, 0.0), "b": (100.0, 0.0)}


def test_align_unknown_anchor_raises():
    with pytest.raises(ValueError):
        align_nodes([_n("a", 0, 0), _n("b", 10, 10)], "diagonal")  # type: ignore[arg-type]


def test_align_omits_unchanged_nodes():
    # If a node is already on the target line, it must not appear in the diff.
    out = align_nodes(
        [_n("a", 0, 5), _n("b", 10, 5)],
        "top",
    )
    assert out == {}


# ── distribute ─────────────────────────────────────────────────────────────


def test_distribute_too_few_returns_empty():
    assert distribute_nodes([_n("a", 0, 0), _n("b", 10, 0)], "horizontal") == {}


def test_distribute_horizontal_three_nodes_centres_mid():
    # Three 100-wide nodes, centres at 50, 200, 350. Span = 300, step = 150.
    # Middle should land at centre 200 → already there. Test with off-centre:
    # a=0 (c=50), b=120 (c=170), c=300 (c=350). Step = 150 → b target centre
    # = 200 → new_x = 150.
    out = distribute_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 120, 0, 100, 100), _n("c", 300, 0, 100, 100)],
        "horizontal",
    )
    assert out == {"b": (150.0, 0.0)}


def test_distribute_vertical_three_nodes_centres_mid():
    out = distribute_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 0, 120, 100, 100), _n("c", 0, 300, 100, 100)],
        "vertical",
    )
    assert out == {"b": (0.0, 150.0)}


def test_distribute_endpoints_do_not_move():
    out = distribute_nodes(
        [_n("a", 0, 0, 100, 100), _n("b", 200, 0, 100, 100), _n("c", 300, 0, 100, 100)],
        "horizontal",
    )
    # Endpoints by centre: a (c=50), c (c=350). Step = (350-50)/2 = 150.
    # b target centre = 200 → new_x = 150.
    assert "a" not in out
    assert "c" not in out


def test_distribute_unsorted_input_handled_by_sort():
    # Passing nodes out of order shouldn't change the result.
    out = distribute_nodes(
        [_n("c", 300, 0, 100, 100), _n("a", 0, 0, 100, 100), _n("b", 120, 0, 100, 100)],
        "horizontal",
    )
    assert out == {"b": (150.0, 0.0)}


def test_distribute_unknown_axis_raises():
    with pytest.raises(ValueError):
        distribute_nodes(
            [_n("a", 0, 0), _n("b", 1, 0), _n("c", 2, 0)], "diagonal",  # type: ignore[arg-type]
        )


def test_default_width_height_is_100():
    n = SelectedNode(id="x", x=0, y=0)
    assert n.w == 100.0
    assert n.h == 100.0
