"""Browser folds retain the domain walk and ordinary node-update contract."""

import json
from pathlib import Path

from anchor.core.events.canvas import NodeAdded, NodeUpdated
from anchor.core.workspace.builtin_node_types import builtin_node_type_registry
from anchor.core.workspace.layout import EdgeLike, NodeLike, organize_subtree
from anchor.core.workspace.reducer import apply
from anchor.core.workspace.roles import role_warning
from anchor.core.workspace.workspace import Workspace


def test_browser_walk_fixtures_match_domain_organizer():
    fixtures = json.loads(
        (Path(__file__).parents[2] / "web/src/canvas/subtree-walk-fixtures.json")
        .read_text(encoding="utf-8")
    )
    for fixture in fixtures:
        nodes = [NodeLike(id=node_id, x=0, y=0) for node_id in fixture["nodes"]]
        edges = [EdgeLike(**edge) for edge in fixture["edges"]]
        for direction in ("outgoing", "incoming", "any"):
            result = organize_subtree(nodes, edges, fixture["root"], direction=direction)
            assert sorted(result) == fixture[direction]


def test_presentation_updates_preserve_sources_descendants_and_positions():
    state = Workspace(slug="w1")
    state = apply(state, NodeAdded(id="root", node_type="concept", data={"source_ref": {"slug": "manual", "page": 2}}))
    state = apply(state, NodeAdded(id="child", node_type="fact", x=500, y=600, data={"text": "Full claim"}))
    state = apply(state, NodeUpdated(id="root", fields={"data": {"collapsed": True, "collapse_direction": "outgoing", "role": "heading"}}))
    state = apply(state, NodeUpdated(id="child", fields={"data": {"display_mode": "full"}}))
    assert state.nodes["root"].data["source_ref"] == {"slug": "manual", "page": 2}
    assert state.nodes["child"].data["text"] == "Full claim"
    assert (state.nodes["child"].x, state.nodes["child"].y) == (500, 600)
    assert role_warning(state.nodes["root"].data) is None
    assert builtin_node_type_registry().unknown_data_keys("concept", {
        "collapsed": True, "collapse_direction": "outgoing", "role": "heading",
    }) == []
