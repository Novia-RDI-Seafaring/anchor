"""`data.role` — the part a card plays in an argument.

Same contract as `data.review`: a small closed vocabulary on any element,
never blocking a write, warned about when it is not one of the listed words.
"""
from __future__ import annotations

import pytest

from anchor.core.workspace.builtin_node_types import BUILTIN_NODE_TYPES
from anchor.core.workspace.roles import (
    ROLE_DESCRIPTIONS,
    ROLES,
    role_of,
    role_warning,
)


def test_every_role_is_described():
    assert set(ROLE_DESCRIPTIONS) == set(ROLES)
    assert all(ROLE_DESCRIPTIONS[r].strip() for r in ROLES)


def test_the_vocabulary_covers_a_decision():
    # IBIS asks the question and weighs options; Toulmin needs the rebuttal.
    for needed in ("question", "option", "decision", "rejected", "assumption", "open"):
        assert needed in ROLES


@pytest.mark.parametrize("role", ROLES)
def test_a_listed_role_reads_back(role):
    assert role_of({"role": role}) == role
    assert role_warning({"role": role}) is None


def test_an_unlisted_role_is_stored_but_warned():
    warning = role_warning({"role": "verdict"})
    assert warning is not None
    assert "verdict" in warning
    # The warning names the vocabulary so the next call can fix itself.
    assert "decision" in warning
    # Not recognised, so no badge.
    assert role_of({"role": "verdict"}) is None


def test_a_non_string_role_is_warned():
    warning = role_warning({"role": 3})
    assert warning is not None and "string" in warning
    assert role_of({"role": 3}) is None


def test_absent_role_is_silent():
    assert role_warning({}) is None
    assert role_warning(None) is None
    assert role_of({}) is None
    assert role_of(None) is None


def test_none_drops_the_key_on_a_merge_patch():
    # `data: {"role": None}` is the documented way to remove a key (#192).
    assert role_warning({"role": None}, partial=True) is None
    # On a full add-node payload an explicit null is still worth flagging.
    assert role_warning({"role": None}, partial=False) is not None


def test_role_is_carried_by_the_general_node_types():
    by_name = {t.name: t for t in BUILTIN_NODE_TYPES}
    for name in ("fact", "note", "markdown", "text", "concept", "area"):
        assert "role" in by_name[name].data_fields, name


def test_role_does_not_trip_the_unknown_data_key_warning():
    from anchor.core.workspace.node_types import NodeTypeRegistry

    registry = NodeTypeRegistry(BUILTIN_NODE_TYPES)
    assert registry.unknown_data_keys("fact", {"role": "decision"}) == []
