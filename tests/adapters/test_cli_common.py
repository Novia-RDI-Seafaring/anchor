"""Shared CLI defaults resolve storage from the environment, not env vars."""

from __future__ import annotations

import pytest

from anchor.adapters.cli.common import default_data_dir
from anchor.infra import environment as env_mod
from anchor.infra.environment import init_environment


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / "_global_unused")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_default_data_dir_uses_environment_default_project(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_DATA_DIR", raising=False)
    root = tmp_path / "env"
    init_environment(root)
    monkeypatch.chdir(root)
    assert default_data_dir() == root / "projects" / "default"


def test_anchor_data_dir_env_var_is_ignored_for_default(tmp_path, monkeypatch):
    # Storage is config-driven: a stray ANCHOR_DATA_DIR does not move the
    # environment's default project.
    root = tmp_path / "env"
    init_environment(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(tmp_path / "elsewhere"))
    assert default_data_dir() == root / "projects" / "default"
