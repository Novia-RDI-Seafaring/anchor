"""`anchor-mcp --project <folder>` resolves that folder's config."""
from __future__ import annotations

import os

import pytest

from anchor.adapters.mcp import stdio_main
from anchor.infra.config import AnchorConfig


@pytest.fixture(autouse=True)
def _restore_anchor_config():
    prev = os.environ.get("ANCHOR_CONFIG")
    yield
    if prev is None:
        os.environ.pop("ANCHOR_CONFIG", None)
    else:
        os.environ["ANCHOR_CONFIG"] = prev


def test_project_points_config_at_folder_toml(tmp_path):
    (tmp_path / "anchor.toml").write_text(
        'provider = "local"\ndata_dir = "/tmp/proj-kb"\nembed_model = "MARK"\n'
    )
    stdio_main._apply_project(tmp_path)
    assert os.environ["ANCHOR_CONFIG"] == str(tmp_path / "anchor.toml")
    # And the resolved config reflects that folder, even from an unrelated CWD.
    cfg = AnchorConfig()
    assert str(cfg.data_dir) == "/tmp/proj-kb"
    assert cfg.embed_model == "MARK"


def test_project_without_toml_warns_and_sets_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANCHOR_CONFIG", raising=False)
    stdio_main._apply_project(tmp_path)  # no anchor.toml here
    assert "ANCHOR_CONFIG" not in os.environ
    assert "no anchor.toml" in capsys.readouterr().err


def test_project_none_is_a_noop(monkeypatch):
    monkeypatch.delenv("ANCHOR_CONFIG", raising=False)
    stdio_main._apply_project(None)
    assert "ANCHOR_CONFIG" not in os.environ
