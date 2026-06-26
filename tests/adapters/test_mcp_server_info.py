"""MCP `server_info` tool: which env/project + which serve hosts it (#177/#179)."""
from __future__ import annotations

import pytest

from anchor.adapters.mcp.server import SERVER_INFO_TOOL_DEFINITION, _build_server_info
from anchor.adapters.mcp.tiering import CORE_NAMES
from anchor.infra import environment as env_mod
from anchor.infra import serve_registry as sr
from anchor.infra.environment import create_env, create_project


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_server_info_is_a_core_advertised_tool():
    assert SERVER_INFO_TOOL_DEFINITION["name"] == "server_info"
    assert "server_info" in CORE_NAMES  # advertised on every connection


def test_server_info_resolves_project_and_running_serve(tmp_path):
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    data_dir = folder / ".anchor_data"
    path = sr.register_serve(
        host="127.0.0.1", port=8009, data_dir=data_dir, started_at="t"
    )
    try:
        info = _build_server_info(data_dir)
        assert info["env"] == "work"
        assert info["project"] == "pumps"
        assert info["serve"]["running"] is True
        assert info["serve"]["base_url"] == "http://127.0.0.1:8009"
        assert info["serve"]["canvas_url_prefix"] == "http://127.0.0.1:8009/c/"
    finally:
        sr.unregister_serve(path)


def test_server_info_reports_no_serve_when_none_running(tmp_path):
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    info = _build_server_info(folder / ".anchor_data")
    assert info["project"] == "pumps"
    assert info["serve"] == {"running": False}
