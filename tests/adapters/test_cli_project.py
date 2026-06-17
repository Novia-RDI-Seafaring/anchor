"""CLI peers for #120 projects + migration."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import init_environment, resolve_environment

runner = CliRunner()

_CLEAR = ("ANCHOR_ENV", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR")


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / "_global_unused")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_project_create_and_list(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    created = runner.invoke(
        app, ["project", "create", "pumps", "--env", str(root), "--description", "LKH pumps"]
    )
    assert created.exit_code == 0, created.output
    assert (root / "projects" / "pumps" / "bronze").is_dir()

    listed = runner.invoke(app, ["project", "list", "--env", str(root)])
    assert listed.exit_code == 0, listed.output
    assert "pumps" in listed.output
    assert "LKH pumps" in listed.output


def test_project_create_rejects_bad_name(tmp_path):
    root = tmp_path / "env"
    init_environment(root)
    result = runner.invoke(app, ["project", "create", "../escape", "--env", str(root)])
    assert result.exit_code == 2


def test_project_create_requires_environment(tmp_path):
    bare = tmp_path / "bare"
    result = runner.invoke(app, ["project", "create", "pumps", "--env", str(bare)])
    assert result.exit_code == 1
    assert "No Anchor environment" in result.output


def test_project_set_description(tmp_path):
    root = tmp_path / "env"
    env = init_environment(root)
    runner.invoke(app, ["project", "create", "pumps", "--env", str(root)])
    result = runner.invoke(
        app, ["project", "set-description", "pumps", "new desc", "--env", str(root)]
    )
    assert result.exit_code == 0, result.output
    from anchor.infra.environment import project_meta

    assert project_meta(env, "pumps").description == "new desc"


def test_migrate_moves_legacy_data_dir(tmp_path):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    (legacy / "bronze" / "doc.pdf").write_text("x")
    target = tmp_path / ".anchor"

    result = runner.invoke(
        app, ["migrate", "--env", str(target), "--from", str(legacy), "--yes"]
    )
    assert result.exit_code == 0, result.output
    moved = target / "projects" / "default" / "bronze" / "doc.pdf"
    assert moved.is_file()
    assert not legacy.exists()
    env = resolve_environment(target)
    assert "default" in env.list_project_names()


def test_migrate_dry_run_changes_nothing(tmp_path):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    target = tmp_path / ".anchor"
    result = runner.invoke(
        app, ["migrate", "--env", str(target), "--from", str(legacy), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert not target.exists()
    assert legacy.exists()


def test_migrate_refuses_to_clobber_existing_default(tmp_path):
    legacy = tmp_path / "anchor-data"
    (legacy / "bronze").mkdir(parents=True)
    (legacy / "bronze" / "old.pdf").write_text("old")
    target = tmp_path / ".anchor"
    existing = target / "projects" / "default" / "bronze"
    existing.mkdir(parents=True)
    (existing / "keep.pdf").write_text("keep")

    result = runner.invoke(
        app, ["migrate", "--env", str(target), "--from", str(legacy), "--yes"]
    )
    assert result.exit_code == 0, result.output
    # both left in place; nothing overwritten
    assert (existing / "keep.pdf").is_file()
    assert (legacy / "bronze" / "old.pdf").is_file()
