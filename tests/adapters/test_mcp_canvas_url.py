"""MCP `canvas_url`: what an agent opens when the user asks to see Anchor."""
from __future__ import annotations

import pytest

from anchor.adapters.mcp.server import _build_canvas_url
from anchor.adapters.mcp.tiering import CORE_NAMES
from anchor.core.ids import InvalidWorkspaceSlugError
from anchor.infra import environment as env_mod
from anchor.infra import serve_registry as sr
from anchor.infra.environment import create_env, create_project


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.setattr(sr, "_pid_alive", lambda pid: True)


@pytest.fixture
def data_dir(tmp_path):
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    return folder / ".anchor_data"


def test_canvas_url_is_advertised_on_every_connection():
    assert "canvas_url" in CORE_NAMES


def test_canvas_url_names_the_start_page_or_one_canvas(data_dir):
    path = sr.register_serve(host="127.0.0.1", port=8009, data_dir=data_dir, started_at="t")
    try:
        start = _build_canvas_url(data_dir, None)
        assert start["url"] == "http://127.0.0.1:8009/"
        assert start["project"] == "pumps"
        assert _build_canvas_url(data_dir, "lkh")["url"] == "http://127.0.0.1:8009/c/lkh"
    finally:
        sr.unregister_serve(path)


def test_canvas_url_without_a_serve_gives_the_command_not_a_guess(data_dir):
    out = _build_canvas_url(data_dir, "lkh")
    assert out["running"] is False
    assert "url" not in out
    assert out["start"] == "anchor serve --env work --project pumps"


def test_canvas_url_rejects_a_bad_slug(data_dir):
    with pytest.raises(InvalidWorkspaceSlugError):
        _build_canvas_url(data_dir, "../x")


def _two_projects(tmp_path):
    from anchor.adapters.mcp.router import ProjectRouter

    env = create_env("work", settings={"provider": "local"})
    dirs = {}
    for name in ("pumps", "valves"):
        create_project(env, name, root=tmp_path / name)
        dirs[name] = tmp_path / name / ".anchor_data"
    return ProjectRouter(env_arg="work"), dirs


def test_unnamed_project_takes_the_one_being_served(tmp_path):
    from anchor.adapters.mcp.server import _canvas_url_unnamed

    router, dirs = _two_projects(tmp_path)
    path = sr.register_serve(host="127.0.0.1", port=8009, data_dir=dirs["valves"], started_at="t")
    try:
        assert _canvas_url_unnamed(router, None) == {"session_default": "valves"}
        assert router.session_default == "valves"
    finally:
        sr.unregister_serve(path)


def test_unnamed_project_with_several_served_asks(monkeypatch, tmp_path):
    from anchor.adapters.mcp.server import _canvas_url_unnamed

    router, dirs = _two_projects(tmp_path)
    paths = []
    for port, name in ((8009, "pumps"), (8010, "valves")):
        # A record is filed under its process id; two serves are two processes.
        monkeypatch.setattr(sr.os, "getpid", lambda port=port: port)
        paths.append(sr.register_serve(
            host="127.0.0.1", port=port, data_dir=dirs[name], started_at="t",
        ))
    try:
        out = _canvas_url_unnamed(router, None)
        assert {p["project"] for p in out["choose"]} == {"pumps", "valves"}
        assert router.session_default is None
    finally:
        for path in paths:
            sr.unregister_serve(path)


def test_unnamed_project_with_nothing_served_falls_back(tmp_path):
    from anchor.adapters.mcp.server import _canvas_url_unnamed

    router, _ = _two_projects(tmp_path)
    assert _canvas_url_unnamed(router, None) is None
