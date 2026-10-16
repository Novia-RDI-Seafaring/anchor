"""An agent's working folder is its project.

An agent opened in a folder (a Codex project, a repo) expects what it ingests
there to stay there, not in the environment's `default` project.
`create_project(folder=...)` finds or makes the folder's project and makes it
the session's default.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.http.routers.projects import router as projects_router
from anchor.adapters.mcp.router import ProjectRouter
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    FolderProjectError,
    ProjectEnvMismatchError,
    bind_folder_project,
    create_env,
    create_project,
    project_for_folder,
)

_CLEAR = ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR")


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _folder(tmp_path, name="pump work"):
    folder = tmp_path / name
    folder.mkdir()
    return folder


def test_a_folder_becomes_a_project_named_after_it(tmp_path):
    env = create_env("local")
    folder = _folder(tmp_path)
    bound = bind_folder_project(env, folder)
    assert bound == {"project": "pump-work", "folder": str(folder.resolve()), "created": True}
    assert (folder / "anchor.toml").is_file()
    assert (folder / ".anchor_data" / "bronze").is_dir()
    assert env.project_dir("pump-work") == folder.resolve() / ".anchor_data"


def test_binding_again_returns_the_same_project(tmp_path):
    env = create_env("local")
    folder = _folder(tmp_path)
    bind_folder_project(env, folder)
    again = bind_folder_project(env, folder)
    assert again["project"] == "pump-work" and again["created"] is False


def test_a_subfolder_is_inside_its_project(tmp_path):
    env = create_env("local")
    folder = _folder(tmp_path)
    bind_folder_project(env, folder, name="pumps")
    sub = folder / "drawings"
    sub.mkdir()
    assert project_for_folder(env, sub) == "pumps"
    assert bind_folder_project(env, sub)["project"] == "pumps"


def test_a_name_taken_elsewhere_is_refused_with_a_way_out(tmp_path):
    env = create_env("local")
    create_project(env, "pump-work")
    with pytest.raises(FolderProjectError, match="pass a different name"):
        bind_folder_project(env, _folder(tmp_path))


def test_a_relative_or_missing_folder_is_refused(tmp_path):
    env = create_env("local")
    with pytest.raises(FolderProjectError, match="absolute"):
        bind_folder_project(env, "pump-work")
    with pytest.raises(FolderProjectError, match="not an existing folder"):
        bind_folder_project(env, tmp_path / "nope")


def test_a_folder_marked_for_another_environment_is_refused(tmp_path):
    create_env("work")
    other = create_env("local")
    folder = _folder(tmp_path)
    bind_folder_project(env_mod.resolve_environment("work"), folder)
    env_mod.unregister_project(env_mod.resolve_environment("work"), "pump-work")
    with pytest.raises(ProjectEnvMismatchError):
        bind_folder_project(other, folder)


def test_mcp_create_project_with_folder_sets_the_session_project(tmp_path):
    create_env("local")
    router = ProjectRouter(env_arg="local")
    folder = _folder(tmp_path)
    out = router.create_project(None, folder=str(folder))
    assert out["project"] == "pump-work" and out["session_default"] == "pump-work"
    assert router.bundle_for(None).config.data_dir == folder.resolve() / ".anchor_data"
    listed = {p["name"]: p["folder"] for p in router.list_projects()["projects"]}
    assert listed["pump-work"] == str(folder.resolve())


def test_cli_project_create_folder(tmp_path):
    from anchor.adapters.cli.project import project_app

    create_env("local")
    folder = _folder(tmp_path)
    result = CliRunner().invoke(project_app, ["create", "--env", "local", "--folder", str(folder)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["project"] == "pump-work"


def test_http_refuses_a_folder_outside_home(tmp_path):
    create_env("local")
    app = FastAPI()
    app.include_router(projects_router)
    response = TestClient(app).post("/api/projects?env=local", json={"folder": "/etc"})
    assert response.status_code == 400
