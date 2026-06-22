"""Shared CLI defaults resolve storage from the environment's project."""

from __future__ import annotations

import pytest

from anchor.adapters.cli.common import default_data_dir
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project, set_use


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_default_is_default_env_default_project(tmp_path):
    create_env("local")
    expected = tmp_path / ".anchor" / "envs" / "local" / "projects" / "default" / ".anchor_data"
    assert default_data_dir() == expected


def test_honors_anchor_env_and_project(tmp_path, monkeypatch):
    env = create_env("work")
    create_project(env, "pumps")
    monkeypatch.setenv("ANCHOR_ENV", "work")
    monkeypatch.setenv("ANCHOR_PROJECT", "pumps")
    assert default_data_dir() == env.project_dir("pumps")


def test_honors_use_selection(tmp_path):
    env = create_env("work")
    create_project(env, "pumps")
    set_use("work", "pumps")
    assert default_data_dir() == env.project_dir("pumps")


def test_anchor_data_dir_env_var_is_ignored(tmp_path, monkeypatch):
    create_env("local")
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(tmp_path / "elsewhere"))
    expected = tmp_path / ".anchor" / "envs" / "local" / "projects" / "default" / ".anchor_data"
    assert default_data_dir() == expected
