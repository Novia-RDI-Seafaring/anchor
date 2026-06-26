"""OCR backend probe -- fail-fast in the docling extractor (issue #174).

No real model or network access. Monkeypatches the onnxruntime import so
tests are hermetic.
"""
from __future__ import annotations

import sys

import pytest

from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx


def test_assert_ocr_backend_passes_when_onnxruntime_importable(monkeypatch):
    """_assert_ocr_backend does not raise when onnxruntime is available."""
    import types

    fake = types.ModuleType("onnxruntime")
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    dx._assert_ocr_backend()  # must not raise


def test_assert_ocr_backend_raises_runtime_error_when_missing(monkeypatch):
    """_assert_ocr_backend raises RuntimeError with the remediation message."""
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    with pytest.raises(RuntimeError, match="uv tool install --force --editable"):
        dx._assert_ocr_backend()


def test_extract_sync_fails_fast_before_convert(monkeypatch):
    """_extract_sync raises early -- before _convert is called -- when onnxruntime absent."""
    monkeypatch.setitem(sys.modules, "onnxruntime", None)

    convert_called = []
    monkeypatch.setattr(dx, "_convert", lambda p, d: convert_called.append(d) or {"items": []})

    with pytest.raises(RuntimeError, match="OCR backend not importable"):
        dx._extract_sync("dummy.pdf")

    assert convert_called == [], "_convert must not be reached when OCR backend absent"


def test_extract_sync_proceeds_when_onnxruntime_available(monkeypatch):
    """_extract_sync continues normally when onnxruntime is importable."""
    import types

    monkeypatch.setitem(sys.modules, "onnxruntime", types.ModuleType("onnxruntime"))
    monkeypatch.setattr(dx, "_convert", lambda p, d: {"items": [], "tables": []})
    result = dx._extract_sync("dummy.pdf", device="cpu")
    assert "items" in result


def test_remediation_message_matches_check_command():
    """The ingest remediation message matches the one printed by anchor check."""
    # Verify the canonical remediation string is present in the extractor.
    assert "uv tool install --force --editable ." in dx._OCR_REMEDIATION
