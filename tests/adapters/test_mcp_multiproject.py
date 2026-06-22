"""MCP multiproject router + server wiring (env by name, managed projects)."""
from __future__ import annotations

import json

import pytest

from anchor.adapters.mcp import handlers_canvas
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import (
    LIFECYCLE_TOOL_DEFINITIONS,
    _resolution_error,
    _with_project_arg,
    build_mcp_server,
)
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    NoEnvironmentError,
    NoProjectError,
    create_env,
    create_project,
)

_CLEAR = ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR")


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _router(name="local"):
    return ProjectRouter(env_arg=name)


# -- resolution -------------------------------------------------------------- #
def test_named_project_resolves_and_caches(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    router = _router()
    b1 = router.bundle_for("pumps")
    assert b1.config.data_dir == env.project_dir("pumps")
    assert router.bundle_for("pumps") is b1  # cached


def test_unknown_named_project_raises(tmp_path):
    create_env("local")
    with pytest.raises(NoProjectError):
        _router().bundle_for("ghost")


def test_omitted_project_uses_default(tmp_path):
    env = create_env("local")
    bundle = _router().bundle_for(None)  # implied 'default', auto-provisioned
    assert bundle.config.data_dir == env.project_dir("default")
    assert (env.project_dir("default") / "bronze").is_dir()


def test_uninitialized_nondefault_env_raises(tmp_path):
    # A named env that is not set up cannot serve a default project.
    with pytest.raises(NoEnvironmentError):
        _router("work").bundle_for(None)


# -- lifecycle --------------------------------------------------------------- #
def test_router_lifecycle(tmp_path):
    create_env("local")
    router = _router()
    assert router.create_project("pumps", "LKH")["created"] == "pumps"
    listing = router.list_projects()
    assert listing["environment"] == "local"
    assert any(p["name"] == "pumps" and p["description"] == "LKH" for p in listing["projects"])
    assert router.open_project("pumps")["session_default"] == "pumps"
    assert router.bundle_for(None).config.data_dir.parent.name == "pumps"


def test_router_update_project(tmp_path):
    env = create_env("local")
    create_project(env, "pumps")
    assert _router().update_project("pumps", "new")["updated"] == "pumps"
    from anchor.infra.environment import project_meta

    assert project_meta(env, "pumps").description == "new"


def test_router_create_environment(tmp_path):
    router = ProjectRouter(env_arg=None)
    result = router.create_environment("work", provider="local", description="test")
    assert (tmp_path / ".anchor" / "envs" / "work" / "env.toml").is_file()
    assert result["environment"] == "work"
    router.create_project("pumps")
    assert "pumps" in [p["name"] for p in router.list_projects()["projects"]]


# -- multiplexing isolation -------------------------------------------------- #
async def test_two_projects_are_isolated(tmp_path):
    env = create_env("local")
    create_project(env, "alpha")
    create_project(env, "beta")
    router = _router()
    a = router.bundle_for("alpha")
    b = router.bundle_for("beta")
    await handlers_canvas.call_tool(a.workspace, "canvas_create_workspace", {"slug": "boarda"})
    await handlers_canvas.call_tool(b.workspace, "canvas_create_workspace", {"slug": "boardb"})
    assert (env.project_dir("alpha") / "canvases" / "boarda").is_dir()
    assert (env.project_dir("beta") / "canvases" / "boardb").is_dir()
    assert not (env.project_dir("alpha") / "canvases" / "boardb").exists()


# -- server wiring helpers --------------------------------------------------- #
def test_with_project_arg_adds_optional_project():
    defs = [{"name": "x", "inputSchema": {"type": "object",
            "properties": {"slug": {"type": "string"}}, "required": ["slug"]}}]
    out = _with_project_arg(defs)
    assert "project" in out[0]["inputSchema"]["properties"]
    assert "project" not in defs[0]["inputSchema"]["properties"]  # deep copy


def test_resolution_error_shapes():
    np = _resolution_error(NoProjectError("ghost", ["a", "b"]))
    assert json.loads(np)["error"] == "no_project"
    assert json.loads(np)["available"] == ["a", "b"]
    ne = _resolution_error(NoEnvironmentError("work"))
    assert json.loads(ne) == {"error": "no_environment", "message": json.loads(ne)["message"],
                              "environment": "work"}


def test_build_mcp_server_requires_bundle_or_router():
    with pytest.raises(ValueError):
        build_mcp_server()


def test_build_mcp_server_router_mode_constructs(tmp_path):
    create_env("local")
    assert build_mcp_server(router=_router()) is not None


def test_lifecycle_tools_present():
    names = {d["name"] for d in LIFECYCLE_TOOL_DEFINITIONS}
    assert names == {
        "list_projects", "create_project", "create_environment",
        "update_project", "open_project",
    }
