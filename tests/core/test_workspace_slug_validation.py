"""Coverage for the workspace slug + upload-name safety helpers.

These pure helpers gate everything that touches the filesystem from a
client-controlled identifier. The asserts below pin the policy so a
future "let's loosen the regex" PR shows up in the diff explicitly.
"""
from __future__ import annotations

import pytest

from anchor.core.ids import InvalidWorkspaceSlugError, validate_workspace_slug
from anchor.core.upload_safety import (
    UnsafeUploadError,
    assert_within,
    safe_upload_name,
)


# ── workspace slugs ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "slug",
    [
        "vasa",
        "Vasa",
        "Vasa-sub-4budqsic",
        "pump_analysis",
        "demo-2026.05.25",
        "a",
        "A" * 63,
    ],
)
def test_accepts_well_formed_slugs(slug):
    assert validate_workspace_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        "",
        ".",
        "..",
        "../escape",
        "..\\escape",
        "/abs/path",
        "C:\\Windows",
        "a/b",
        "a\\b",
        ".hidden",
        "spaces are bad",
        "A" * 64,  # one over the limit
        "name\x00null",
        "name\nnewline",
    ],
)
def test_rejects_traversal_and_separators(slug):
    with pytest.raises(InvalidWorkspaceSlugError):
        validate_workspace_slug(slug)


# ── upload filename ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename, exts, expected",
    [
        ("pump.pdf", {".pdf"}, "pump.pdf"),
        ("Alfa Laval LKH.pdf", {".pdf"}, "Alfa Laval LKH.pdf"),
        ("model_FMI2.fmu", {".fmu"}, "model_FMI2.fmu"),
        ("housing.STL", {".stl", ".obj"}, "housing.STL"),
    ],
)
def test_safe_upload_name_accepts(filename, exts, expected):
    assert safe_upload_name(filename, allowed_extensions=exts) == expected


@pytest.mark.parametrize(
    "filename",
    [
        None,
        "",
        "../../etc/passwd.pdf",
        "..\\..\\evil.fmu",
        "/abs/path.pdf",
        "C:\\Windows\\evil.pdf",
        "good.pdf\x00.exe",
        "good\nname.pdf",
        ".",
        "..",
    ],
)
def test_safe_upload_name_rejects_traversal(filename):
    with pytest.raises(UnsafeUploadError):
        safe_upload_name(filename, allowed_extensions={".pdf"})


def test_safe_upload_name_rejects_bad_extension():
    with pytest.raises(UnsafeUploadError):
        safe_upload_name("payload.exe", allowed_extensions={".pdf"})


# ── containment ────────────────────────────────────────────────────────


def test_assert_within_accepts_descendants(tmp_path):
    sub = tmp_path / "child" / "file.txt"
    sub.parent.mkdir()
    sub.write_text("ok")
    resolved = assert_within(sub, tmp_path)
    assert resolved == sub.resolve()


def test_assert_within_rejects_traversal(tmp_path):
    other = tmp_path.parent / "neighbour.txt"
    with pytest.raises(UnsafeUploadError):
        assert_within(other, tmp_path)
