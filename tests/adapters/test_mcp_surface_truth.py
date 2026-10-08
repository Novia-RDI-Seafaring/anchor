"""The advertised surface and its notes have to be true.

Two failures an agent hit in one session: the skill told it to finish a batch
with `canvas_propose_set`, which was gated and therefore unreachable; and
`anchor_list_capabilities` told it gated tools were "callable by name right
now", which no MCP host supports.
"""
from __future__ import annotations

import pytest

from anchor.adapters.mcp.tiering import (
    CAPABILITIES_TOOL_DEFINITION,
    CORE_NAMES,
    build_capabilities_payload,
)


def test_propose_set_is_advertised_because_the_skill_mandates_it():
    # The skill says to finish every multi-element write with this call. A
    # gated tool cannot satisfy a mandate: hosts dispatch only what is in
    # tools/list and this server sends no tools/list_changed.
    assert "canvas_propose_set" in CORE_NAMES


@pytest.mark.parametrize(
    "name",
    [
        "canvas_add_to_proposal_set",
        "canvas_list_proposal_sets",
        "canvas_review_proposal_set",
    ],
)
def test_the_rest_of_the_batch_surface_stays_gated(name):
    # Following the skill does not need these: a verdict is stamped onto each
    # member as data.review, which canvas_get_state already returns.
    assert name not in CORE_NAMES


def test_the_skill_does_not_send_agents_to_a_gated_tool():
    import re
    from pathlib import Path

    # Normalised: the skill is hard-wrapped prose, so raw substring matching
    # breaks on a reflow that changed nothing.
    skill = re.sub(
        r"\s+", " ", Path("src/anchor/skills/canvas.md").read_text(encoding="utf-8")
    )
    # The gated tools are named as unavailable by default, not as a step.
    assert "are not advertised by default" in skill
    # And the reachable way to read a verdict is spelled out.
    assert "`canvas_get_state` already returns both" in skill


def _note_texts() -> list[str]:
    payload = build_capabilities_payload([], active_extensions=set())
    return [payload["note"], CAPABILITIES_TOOL_DEFINITION["description"]]


def test_no_note_claims_a_gated_tool_is_simply_callable():
    for text in _note_texts():
        assert "callable by name right away" not in text
        assert "callable by name right now" not in text


def test_the_note_explains_why_a_gated_tool_may_not_work():
    note = build_capabilities_payload([], active_extensions=set())["note"]
    assert "advertised" in note
    assert "list_changed" in note


def test_active_extensions_are_still_described_as_reachable():
    # The one case where a non-core tool really is in the default list.
    note = build_capabilities_payload([], active_extensions=set())["note"]
    assert "DO appear in the default list" in note


def test_snapshot_connection_failure_is_recognised():
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        _is_connection_refused,
    )

    refused = Exception(
        "Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8031/c/x"
    )
    assert _is_connection_refused(refused)
    assert not _is_connection_refused(Exception("Timeout 30000ms exceeded"))
