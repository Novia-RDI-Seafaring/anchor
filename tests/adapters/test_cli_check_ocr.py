"""``anchor check`` OCR backend probe -- FAIL/OK with/without onnxruntime."""
from __future__ import annotations

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
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: True)
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "onnxruntime" in result.output
    assert "importable" in result.output


def test_check_ocr_fail_when_onnxruntime_missing(tmp_path, monkeypatch):
    """When onnxruntime is absent, check reports FAIL + remediation and exits 1."""
    _init_local(tmp_path)
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: False)
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "NOT importable" in result.output
    assert "uv tool install --force --editable ." in result.output


def test_probe_ocr_backend_returns_true_when_importable(monkeypatch):
    """_probe_ocr_backend() returns True when onnxruntime can be imported."""
    import importlib
    import types

    # Provide a stub so the test never depends on the real wheel.
    fake = types.ModuleType("onnxruntime")
    monkeypatch.setitem(importlib.import_module("sys").modules, "onnxruntime", fake)
    assert check_mod._probe_ocr_backend() is True


def test_probe_ocr_backend_returns_false_on_import_error(monkeypatch):
    """_probe_ocr_backend() returns False when onnxruntime raises ImportError."""
    import sys

    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    assert check_mod._probe_ocr_backend() is False
