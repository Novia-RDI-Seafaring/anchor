"""OCR backend probe -- fail-fast in the docling extractor (issues #174, #195).

No real model or network access, and no real ``onnxruntime`` import: tests
patch the import boundary so the suite stays deterministic (issue #195 numpy
double-load).
"""
from __future__ import annotations

import importlib

import pytest

from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx


def test_assert_ocr_backend_passes_when_onnxruntime_importable(monkeypatch):
    """_assert_ocr_backend does not raise when onnxruntime is available."""
    monkeypatch.setattr(importlib, "import_module", lambda name: object())
    dx._assert_ocr_backend()  # must not raise


def test_assert_ocr_backend_raises_reinstall_hint_when_missing(monkeypatch):
    """ModuleNotFoundError -> RuntimeError with the reinstall remediation."""
    def _raise(name):
        raise ModuleNotFoundError(f"No module named {name!r}")

    monkeypatch.setattr(importlib, "import_module", _raise)
    with pytest.raises(RuntimeError, match="uv tool install --force --editable"):
        dx._assert_ocr_backend()


def test_assert_ocr_backend_reports_import_error_without_reinstall(monkeypatch):
    """Backend present but failing to import -> report the error, NOT a reinstall.

    The #195 AX fix: a numpy double-load / ABI error is distinct from a stale
    install and must not get the reinstall hint.
    """
    msg = "cannot load module more than once per process"

    def _raise(name):
        raise ImportError(msg)

    monkeypatch.setattr(importlib, "import_module", _raise)
    with pytest.raises(RuntimeError) as excinfo:
        dx._assert_ocr_backend()
    text = str(excinfo.value)
    assert "present but failed to import" in text
    assert msg in text
    assert "uv tool install" not in text


def test_extract_sync_fails_fast_before_convert(monkeypatch):
    """_extract_sync raises early -- before _convert -- when onnxruntime absent."""
    def _raise(name):
        raise ModuleNotFoundError(f"No module named {name!r}")

    monkeypatch.setattr(importlib, "import_module", _raise)

    convert_called = []
    monkeypatch.setattr(dx, "_convert", lambda p, d, f=False: convert_called.append(d) or {"items": []})

    with pytest.raises(RuntimeError, match="OCR backend not installed"):
        dx._extract_sync("dummy.pdf")

    assert convert_called == [], "_convert must not be reached when OCR backend absent"


def test_extract_sync_proceeds_when_onnxruntime_available(monkeypatch):
    """_extract_sync continues normally when onnxruntime is importable."""
    monkeypatch.setattr(importlib, "import_module", lambda name: object())
    monkeypatch.setattr(dx, "_convert", lambda p, d, f=False: {"items": [], "tables": []})
    result = dx._extract_sync("dummy.pdf", device="cpu")
    assert "items" in result


def test_remediation_message_matches_check_command():
    """The ingest remediation string is the installed-reinstall hint."""
    assert "uv tool install --force --editable ." in dx._OCR_REMEDIATION
