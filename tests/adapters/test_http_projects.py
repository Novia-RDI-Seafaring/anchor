"""HTTP adapter — project management (list / create / remove / rename).

The HTTP peer of the ``anchor project`` CLI group and the project lifecycle
MCP tools. Resolves the environment registry under a monkeypatched
``ANCHOR_HOME`` so it never touches the real ``~/.anchor``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project, resolve_environment
from tests.fixtures.services import make_in_memory_services


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _client():
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app)


def test_list_and_create_projects():
    create_env("local")
    client = _client()
    rsp = client.post(
        "/api/projects?env=local", json={"name": "pumps", "description": "LKH"}
    )
    assert rsp.status_code == 201, rsp.text
    assert rsp.json()["created"] == "pumps"

    listed = client.get("/api/projects?env=local")
    assert listed.status_code == 200
    body = listed.json()
    assert body["environment"] == "local"
    assert any(p["name"] == "pumps" and p["description"] == "LKH" for p in body["projects"])


def test_create_rejects_bad_name():
    create_env("local")
    rsp = _client().post("/api/projects?env=local", json={"name": "../escape"})
    assert rsp.status_code == 400


def test_list_unknown_env_is_404():
    rsp = _client().get("/api/projects?env=ghost")
    assert rsp.status_code == 404


def test_remove_empty_project():
    env = create_env("local")
    create_project(env, "day1")
    rsp = _client().delete("/api/projects/day1?env=local")
    assert rsp.status_code == 200, rsp.text
    assert rsp.json()["removed"] == "day1"
    assert not resolve_environment("local").project_exists("day1")


def test_remove_refuses_nonempty_with_409():
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")
    rsp = _client().delete("/api/projects/pumps?env=local")
    assert rsp.status_code == 409
    detail = rsp.json()["detail"]
    assert detail["documents"] == 1
    assert resolve_environment("local").project_exists("pumps")


def test_remove_force_delete_data():
    env = create_env("local")
    create_project(env, "pumps")
    (env.project_dir("pumps") / "bronze" / "d.pdf").write_text("x")
    rsp = _client().delete(
        "/api/projects/pumps?env=local&force=true&delete_data=true"
    )
    assert rsp.status_code == 200, rsp.text
    assert not resolve_environment("local").project_exists("pumps")


def test_remove_unknown_is_404():
    create_env("local")
    rsp = _client().delete("/api/projects/ghost?env=local")
    assert rsp.status_code == 404


def test_rename_project():
    env = create_env("local")
    create_project(env, "day1", description="throwaway")
    rsp = _client().patch("/api/projects/day1?env=local", json={"new": "agentic"})
    assert rsp.status_code == 200, rsp.text
    assert rsp.json()["to"] == "agentic"
    env = resolve_environment("local")
    assert env.project_exists("agentic")
    assert not env.project_exists("day1")


def test_rename_rejects_existing_target_with_409():
    env = create_env("local")
    create_project(env, "pumps")
    create_project(env, "paper")
    rsp = _client().patch("/api/projects/pumps?env=local", json={"new": "paper"})
    assert rsp.status_code == 409


def test_rename_rejects_bad_name_with_400():
    env = create_env("local")
    create_project(env, "pumps")
    rsp = _client().patch("/api/projects/pumps?env=local", json={"new": "../escape"})
    assert rsp.status_code == 400
