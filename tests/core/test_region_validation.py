"""Shared region schema validation - pure core module."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.ingest.validation import (
    REGION_KINDS,
    bbox_error,
    validate_region,
    validate_regions,
)


def _region(**overrides):
    base = {
        "id": "r1",
        "kind": "spec_block",
        "title": "Technical data",
        "description": "Flow and head",
        "bbox": [10.0, 700.0, 500.0, 400.0],
        "tags": ["specs"],
        "entities": ["LKH-5"],
    }
    base.update(overrides)
    return base


def test_valid_region_has_no_errors():
    assert validate_region(_region()) == []


def test_every_documented_kind_is_accepted():
    for kind in REGION_KINDS:
        assert validate_region(_region(kind=kind)) == []


def test_unknown_kind_is_rejected():
    errors = validate_region(_region(kind="banner"))
    assert any(e["field"] == "kind" for e in errors)


def test_missing_title_is_rejected():
    errors = validate_region(_region(title="  "))
    assert any(e["field"] == "title" for e in errors)


def test_bbox_must_have_four_finite_numbers():
    assert bbox_error([1, 2, 3]) is not None
    assert bbox_error("nope") is not None
    assert bbox_error([1, 2, 3, float("nan")]) is not None
    assert bbox_error([0.0, 100.0, 50.0, 0.0]) is None


def test_bbox_accepts_either_y_order_but_rejects_bad_x_order():
    assert bbox_error([0, 50, 100, 60]) is None
    assert bbox_error([100, 60, 0, 50]) is not None  # left > right


def test_approximate_bbox_satisfies_the_bbox_requirement():
    region = _region()
    del region["bbox"]
    region["approximate_bbox"] = [0.0, 100.0, 50.0, 0.0]
    assert validate_region(region) == []


def test_tags_and_entities_must_be_string_lists():
    errors = validate_region(_region(tags="specs"))
    assert any(e["field"] == "tags" for e in errors)
    errors = validate_region(_region(entities=[1, 2]))
    assert any(e["field"] == "entities" for e in errors)


def test_non_dict_region_is_rejected():
    errors = validate_region("not a region", index=3)
    assert errors and errors[0]["region_index"] == 3


def test_validate_regions_splits_valid_from_invalid():
    valid, errors = validate_regions([
        _region(),
        _region(kind="banner"),
        "garbage",
    ])
    assert len(valid) == 1
    assert valid[0]["id"] == "r1"
    indexes = {e["region_index"] for e in errors}
    assert indexes == {1, 2}


def test_validate_regions_rejects_non_list_payload():
    valid, errors = validate_regions({"regions": []})
    assert valid == []
    assert errors
