"""``anchor check`` OCR backend probe -- OK / not-installed / failed-to-import.

The probe imports the real ``onnxruntime`` only when ``anchor check`` actually
runs. These tests never trigger that import: they either stub the probe or
mock the import boundary, so the suite stays deterministic (issue #195).
"""
from __future__ import annotations

import importlib

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import check as check_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _init_local(tmp_path):
    r = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    assert r.exit_code == 0, r.output


def _run_check(tmp_path):
    return runner.invoke(app, ["check", "--env", "local"])


def test_check_ocr_ok_when_onnxruntime_importable(tmp_path, monkeypatch):
    """When onnxruntime imports fine, check reports OK and exits 0."""
    _init_local(tmp_path)
    # Ensure the probe sees a working import.
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: (True, None))
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "onnxruntime" in result.output
    assert "importable" in result.output


def test_check_ocr_fail_when_onnxruntime_missing(tmp_path, monkeypatch):
    """When onnxruntime is not installed, check reports the reinstall hint, exits 1."""
    _init_local(tmp_path)
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: (False, "missing"))
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "NOT installed" in result.output
    assert "uv tool install --force --editable ." in result.output


def test_check_ocr_fail_when_import_error_does_not_suggest_reinstall(tmp_path, monkeypatch):
    """Backend present but failing to import -> report the error, NOT a reinstall.

    This is the #195 AX fix: a numpy double-load / ABI error must not be
    mislabelled as a stale editable install.
    """
    _init_local(tmp_path)
    detail = "cannot load module more than once per process"
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: (False, detail))
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "present but failed to import" in result.output
    assert detail in result.output
    # The wrong remediation must NOT appear for an import failure.
    assert "uv tool install --force --editable ." not in result.output
    assert "stale" not in result.output


def test_probe_ocr_backend_returns_true_when_importable(monkeypatch):
    """_probe_ocr_backend() returns (True, None) when onnxruntime imports.

    Patch ``importlib.import_module`` so the probe never loads the real wheel.
    """
    monkeypatch.setattr(importlib, "import_module", lambda name: object())
    assert check_mod._probe_ocr_backend() == (True, None)


def test_probe_ocr_backend_reports_missing_on_module_not_found(monkeypatch):
    """ModuleNotFoundError -> (False, 'missing'): genuinely not installed."""
    def _raise(name):
        raise ModuleNotFoundError(f"No module named {name!r}")

    monkeypatch.setattr(importlib, "import_module", _raise)
    assert check_mod._probe_ocr_backend() == (False, "missing")


def test_probe_ocr_backend_reports_error_on_import_error(monkeypatch):
    """A non-ModuleNotFoundError ImportError -> (False, <error string>)."""
    msg = "cannot load module more than once per process"

    def _raise(name):
        raise ImportError(msg)

    monkeypatch.setattr(importlib, "import_module", _raise)
    ok, detail = check_mod._probe_ocr_backend()
    assert ok is False
    assert detail == msg
