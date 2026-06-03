"""Shared CLI defaults stay aligned with environment-based configuration."""

from __future__ import annotations

from anchor.adapters.cli.common import default_data_dir


def test_default_data_dir_honors_anchor_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "configured-data"
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(data_dir))

    assert default_data_dir() == data_dir
