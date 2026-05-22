"""Tests for the closed-vocab tag system."""
import pytest

from src.ingestion.tags import (
    KNOWN_TAGS,
    entity_tag,
    is_known_tag,
    validate_tags,
)


def test_known_tag_structural():
    assert is_known_tag("introduction")
    assert is_known_tag("warranty")


def test_known_tag_content():
    assert is_known_tag("table_2d")
    assert is_known_tag("chart")


def test_known_tag_semantic():
    assert is_known_tag("per_model_specs")
    assert is_known_tag("performance_curve")


def test_unknown_tag_rejected():
    assert not is_known_tag("per-model")
    assert not is_known_tag("randomthing")


def test_entity_tag_accepted_with_payload():
    assert is_known_tag("mentions:pump-5")
    assert is_known_tag("mentions:iec80")


def test_bare_entity_prefix_rejected():
    assert not is_known_tag("mentions:")


def test_validate_tags_returns_offending():
    bad = validate_tags(["introduction", "made-up", "mentions:pump-5", "also-bad"])
    assert bad == ["made-up", "also-bad"]


def test_validate_tags_all_valid():
    assert validate_tags(["introduction", "chart", "mentions:pump-90"]) == []


def test_entity_tag_helper():
    assert entity_tag("PUMP-5") == "mentions:pump-5"
    assert entity_tag("  IEC80  ") == "mentions:iec80"


def test_known_tags_set_nonempty():
    assert "introduction" in KNOWN_TAGS
    assert "performance_curve" in KNOWN_TAGS


def test_pydantic_region_rejects_unknown_tag():
    from src.ingestion.gold import Region, RegionCrop

    with pytest.raises(Exception):
        Region(
            id="x", page=1, bbox=[0, 0, 1, 1], kind="text",
            title="t", description="d",
            tags=["not-a-real-tag"],
            crops=RegionCrop(png="x.png"),
        )


def test_pydantic_region_accepts_known_tags():
    from src.ingestion.gold import Region, RegionCrop

    r = Region(
        id="x", page=1, bbox=[0, 0, 1, 1], kind="chart",
        title="t", description="d",
        tags=["chart", "performance_curve", "mentions:pump-5"],
        crops=RegionCrop(png="x.png"),
    )
    assert "chart" in r.tags
