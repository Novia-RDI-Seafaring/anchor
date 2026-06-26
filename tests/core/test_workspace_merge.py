"""deep_merge — node/edge data patch semantics (#192)."""
from __future__ import annotations

from anchor.core.workspace.merge import deep_merge


def test_merge_preserves_unmentioned_keys():
    base = {"body": "x", "source_ref": {"page": 1, "bbox": [0, 0, 1, 1]}, "doc": "d"}
    out = deep_merge(base, {"text": "hello"})
    assert out == {
        "body": "x",
        "source_ref": {"page": 1, "bbox": [0, 0, 1, 1]},
        "doc": "d",
        "text": "hello",
    }


def test_merge_recurses_into_nested_dicts():
    base = {"source_ref": {"page": 1, "slug": "d"}}
    out = deep_merge(base, {"source_ref": {"bbox": [1, 2, 3, 4]}})
    assert out == {"source_ref": {"page": 1, "slug": "d", "bbox": [1, 2, 3, 4]}}


def test_merge_overwrites_scalar():
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


def test_none_value_deletes_key():
    assert deep_merge({"a": 1, "b": 2}, {"a": None}) == {"b": 2}


def test_inputs_are_not_mutated():
    base = {"a": {"x": 1}}
    patch = {"a": {"y": 2}}
    deep_merge(base, patch)
    assert base == {"a": {"x": 1}}
    assert patch == {"a": {"y": 2}}
