"""MCP multiproject router + server wiring (anchor#120)."""
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
    create_project,
    init_environment,
)

_CLEAR = ("ANCHOR_ENV", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR")


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / "_global_unused")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _router(root):
    return ProjectRouter(env_arg=str(root))


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_named_project_resolves_and_caches(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    create_project(env, "pumps")
    router = _router(root)

    b1 = router.bundle_for("pumps")
    assert b1.config.data_dir == root / "projects" / "pumps"
    b2 = router.bundle_for("pumps")
    assert b1 is b2  # cached by project dir


def test_unknown_named_project_raises(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    with pytest.raises(NoProjectError):
        _router(root).bundle_for("ghost")


def test_named_env_requires_explicit_project(tmp_path):
    # A regular #120 environment has no phantom default: omitting project errors.
    root = tmp_path / "env"
    init_environment(root)
    with pytest.raises(NoProjectError):
        _router(root).bundle_for(None)


def test_global_env_implies_default_project(tmp_path, monkeypatch):
    root = tmp_path / ".anchor"
    init_environment(root)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", root)
    router = ProjectRouter(env_arg=str(root))
    bundle = router.bundle_for(None)  # implied 'default', auto-provisioned
    assert bundle.config.data_dir == root / "projects" / "default"
    assert (root / "projects" / "default" / "bronze").is_dir()


def test_uninitialized_env_raises_no_environment(tmp_path):
    with pytest.raises(NoEnvironmentError):
        _router(tmp_path / "bare").bundle_for("pumps")


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def test_router_lifecycle(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    router = _router(root)

    created = router.create_project("pumps", "LKH datasheets")
    assert created["created"] == "pumps"

    listing = router.list_projects()
    assert listing["environment"] == str(root)
    names = [p["name"] for p in listing["projects"]]
    assert "pumps" in names
    assert any(p["description"] == "LKH datasheets" for p in listing["projects"])

    opened = router.open_project("pumps")
    assert opened["session_default"] == "pumps"
    # now an omitted project resolves to the session default
    assert router.bundle_for(None).config.data_dir == root / "projects" / "pumps"


def test_router_open_unknown_project_raises(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    with pytest.raises(NoProjectError):
        _router(root).open_project("ghost")


def test_router_create_environment(tmp_path):
    target = tmp_path / "newenv"
    router = ProjectRouter(env_arg=None)
    result = router.create_environment(str(target), provider="local", description="test env")
    assert (target / "config.toml").is_file()
    assert result["environment"] == str(target)
    # router now points at the created environment
    router.create_project("pumps")
    assert "pumps" in [p["name"] for p in router.list_projects()["projects"]]


# --------------------------------------------------------------------------- #
# Multiplexing isolation
# --------------------------------------------------------------------------- #
async def test_two_projects_are_isolated(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    create_project(env, "alpha")
    create_project(env, "beta")
    router = _router(root)

    a = router.bundle_for("alpha")
    b = router.bundle_for("beta")
    await handlers_canvas.call_tool(a.workspace, "canvas_create_workspace", {"slug": "boarda"})
    await handlers_canvas.call_tool(b.workspace, "canvas_create_workspace", {"slug": "boardb"})

    assert (root / "projects" / "alpha" / "canvases" / "boarda").is_dir()
    assert (root / "projects" / "beta" / "canvases" / "boardb").is_dir()
    assert not (root / "projects" / "alpha" / "canvases" / "boardb").exists()


# --------------------------------------------------------------------------- #
# Server wiring helpers
# --------------------------------------------------------------------------- #
def test_with_project_arg_adds_optional_project():
    defs = [{
        "name": "x",
        "inputSchema": {"type": "object", "properties": {"slug": {"type": "string"}},
                        "required": ["slug"]},
    }]
    out = _with_project_arg(defs)
    assert "project" in out[0]["inputSchema"]["properties"]
    assert "project" not in out[0]["inputSchema"].get("required", [])
    # original untouched (deep copy)
    assert "project" not in defs[0]["inputSchema"]["properties"]


def test_resolution_error_shapes():
    np = _resolution_error(NoProjectError("ghost", ["a", "b"]))
    assert json.loads(np)["error"] == "no_project"
    assert json.loads(np)["available"] == ["a", "b"]
    from pathlib import Path

    ne = _resolution_error(NoEnvironmentError(Path("/x")))
    assert json.loads(ne)["error"] == "no_environment"


def test_build_mcp_server_requires_bundle_or_router():
    with pytest.raises(ValueError):
        build_mcp_server()


def test_build_mcp_server_router_mode_constructs(tmp_path):
    init_environment(tmp_path / "env")
    server = build_mcp_server(router=_router(tmp_path / "env"))
    assert server is not None


def test_lifecycle_tools_present():
    names = {d["name"] for d in LIFECYCLE_TOOL_DEFINITIONS}
    assert names == {"list_projects", "create_project", "create_environment", "open_project"}
