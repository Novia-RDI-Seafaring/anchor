"""CLI: anchor env / project / migrate in the named-environment model."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env, create_project, project_meta, resolve_environment

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


# -- env group --------------------------------------------------------------- #
def test_env_list_marks_default(tmp_path):
    create_env("local")
    create_env("work")
    from anchor.infra.environment import set_default_env

    set_default_env("local")
    result = runner.invoke(app, ["env", "list"])
    assert result.exit_code == 0, result.output
    assert "local" in result.output
    assert "work" in result.output
    assert "*" in result.output  # default marker


def test_env_default_switches(tmp_path):
    create_env("local")
    create_env("work")
    result = runner.invoke(app, ["env", "default", "work"])
    assert result.exit_code == 0, result.output
    from anchor.infra.environment import default_env_name

    assert default_env_name() == "work"


def test_use_sets_session_selection(tmp_path):
    env = create_env("work")
    create_project(env, "pumps")
    result = runner.invoke(app, ["use", "work", "pumps"])
    assert result.exit_code == 0, result.output
    assert resolve_environment().name == "work"


# -- project group ----------------------------------------------------------- #
def test_project_create_and_list(tmp_path):
    create_env("local")
    created = runner.invoke(
        app, ["project", "create", "pumps", "--env", "local", "--description", "LKH pumps"]
    )
    assert created.exit_code == 0, created.output
    assert (tmp_path / ".anchor" / "envs" / "local" / "projects" / "pumps" / ".anchor_data" / "bronze").is_dir()

    listed = runner.invoke(app, ["project", "list", "--env", "local"])
    assert "pumps" in listed.output
    assert "LKH pumps" in listed.output


def test_project_create_requires_env(tmp_path):
    result = runner.invoke(app, ["project", "create", "pumps", "--env", "ghost"])
    assert result.exit_code == 1
    assert "not set up" in result.output


def test_project_create_rejects_bad_name(tmp_path):
    create_env("local")
    result = runner.invoke(app, ["project", "create", "../escape", "--env", "local"])
    assert result.exit_code == 2


def test_project_set_description(tmp_path):
    env = create_env("local")
    runner.invoke(app, ["project", "create", "pumps", "--env", "local"])
    result = runner.invoke(
        app, ["project", "set-description", "pumps", "new desc", "--env", "local"]
    )
    assert result.exit_code == 0, result.output
    assert project_meta(env, "pumps").description == "new desc"


def test_project_move_same_zone_no_prompt(tmp_path):
    local = create_env("local", settings={"provider": "local"})
    create_env("local2", settings={"provider": "local"})
    create_project(local, "pumps")
    result = runner.invoke(
        app, ["project", "move", "pumps", "--to", "local2", "--env", "local"]
    )
    assert result.exit_code == 0, result.output
    assert resolve_environment("local2").project_exists("pumps")
    assert not resolve_environment("local").project_exists("pumps")


def test_project_move_zone_change_needs_confirm(tmp_path):
    local = create_env("local", settings={"provider": "local"})
    create_env("cloud", settings={"provider": "openai"})
    create_project(local, "pumps")
    # decline the zone-change confirmation
    declined = runner.invoke(
        app, ["project", "move", "pumps", "--to", "cloud", "--env", "local"], input="n\n"
    )
    assert declined.exit_code == 1
    assert resolve_environment("local").project_exists("pumps")  # not moved
    # accept with --yes
    ok = runner.invoke(
        app, ["project", "move", "pumps", "--to", "cloud", "--env", "local", "--yes"]
    )
    assert ok.exit_code == 0, ok.output
    assert resolve_environment("cloud").project_exists("pumps")


# -- migrate ----------------------------------------------------------------- #
def test_migrate_moves_legacy_data_dir(tmp_path, monkeypatch):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    (legacy / "bronze" / "doc.pdf").write_text("x")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", legacy)

    result = runner.invoke(app, ["migrate", "--yes"])
    assert result.exit_code == 0, result.output
    moved = tmp_path / ".anchor" / "envs" / "local" / "projects" / "default" / ".anchor_data" / "bronze" / "doc.pdf"
    assert moved.is_file()
    assert not legacy.exists()


def test_migrate_dry_run_changes_nothing(tmp_path, monkeypatch):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", legacy)
    result = runner.invoke(app, ["migrate", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".anchor" / "envs" / "local").exists()
    assert legacy.exists()
