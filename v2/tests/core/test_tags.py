"""Tests for the generic tag-vocab mechanism (no domain assumptions)."""
from __future__ import annotations

from anchor.core.docs.tags import (
    EMPTY_VOCAB,
    ENTITY_PREFIX,
    TagVocab,
    entity_slug,
    entity_tag,
    is_entity_tag,
)


def test_empty_vocab_rejects_non_entity_tags():
    assert EMPTY_VOCAB.is_known("anything") is False
    assert EMPTY_VOCAB.is_known("mentions:foo") is True


def test_vocab_membership_per_category():
    vocab = TagVocab(
        structural=frozenset({"intro", "summary"}),
        content=frozenset({"narrative", "table"}),
        semantic=frozenset({"specs"}),
    )
    assert vocab.is_known("intro")
    assert vocab.is_known("narrative")
    assert vocab.is_known("specs")
    assert not vocab.is_known("unknown")


def test_known_property_unions_all_categories():
    vocab = TagVocab(
        structural=frozenset({"a"}),
        content=frozenset({"b"}),
        semantic=frozenset({"c"}),
    )
    assert vocab.known == frozenset({"a", "b", "c"})


def test_validate_returns_only_offenders():
    vocab = TagVocab(structural=frozenset({"intro"}))
    assert vocab.validate(["intro", "mentions:lkh-5"]) == []
    assert vocab.validate(["intro", "bogus"]) == ["bogus"]


def test_entity_tag_builds_lowercase_slug():
    assert entity_tag("LKH-5") == "mentions:lkh-5"
    assert entity_tag("  Heat Exchanger  ") == "mentions:heat exchanger"


def test_is_entity_tag_requires_non_empty_slug():
    assert is_entity_tag("mentions:foo")
    assert not is_entity_tag("mentions:")
    assert not is_entity_tag("foo")


def test_entity_slug_extracts_or_returns_none():
    assert entity_slug("mentions:abc") == "abc"
    assert entity_slug("mentions:") is None
    assert entity_slug("foo") is None


def test_entity_prefix_is_stable():
    assert ENTITY_PREFIX == "mentions:"
