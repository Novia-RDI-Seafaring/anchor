"""`anchor install claude-desktop` — named pointer config (anchor#120)."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import install as install_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import init_environment

runner = CliRunner()


@pytest.fixture(autouse=True)
def _paths(monkeypatch, tmp_path):
    desktop = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(install_mod, "_claude_desktop_config_path", lambda: desktop)
    monkeypatch.setattr(env_mod, "GLOBAL_ENV_DIR", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    return desktop


def _servers(desktop):
    return json.loads(desktop.read_text())["mcpServers"]


def test_install_writes_named_pointer_entry(_paths, tmp_path):
    env_dir = tmp_path / "env"
    init_environment(env_dir)
    result = runner.invoke(
        app, ["install", "claude-desktop", "--env", str(env_dir), "--yes"]
    )
    assert result.exit_code == 0, result.output
    entry = _servers(_paths)["anchor"]
    assert entry["args"] == ["--env", str(env_dir)]
    assert entry["command"].endswith("anchor-mcp")


def test_install_is_additive(_paths, tmp_path):
    _paths.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    env_dir = tmp_path / "env"
    init_environment(env_dir)
    runner.invoke(app, ["install", "claude-desktop", "--env", str(env_dir), "--yes"])
    servers = _servers(_paths)
    assert "other" in servers  # preserved
    assert "anchor" in servers


def test_collision_refused_without_force(_paths, tmp_path):
    env_a = tmp_path / "a"
    env_b = tmp_path / "b"
    init_environment(env_a)
    init_environment(env_b)
    runner.invoke(app, ["install", "claude-desktop", "--env", str(env_a), "--yes"])
    clash = runner.invoke(app, ["install", "claude-desktop", "--env", str(env_b), "--yes"])
    assert clash.exit_code == 1
    assert "already points at" in clash.output
    # original entry untouched
    assert _servers(_paths)["anchor"]["args"] == ["--env", str(env_a)]


def test_force_repoints(_paths, tmp_path):
    env_a = tmp_path / "a"
    env_b = tmp_path / "b"
    init_environment(env_a)
    init_environment(env_b)
    runner.invoke(app, ["install", "claude-desktop", "--env", str(env_a), "--yes"])
    repoint = runner.invoke(
        app, ["install", "claude-desktop", "--env", str(env_b), "--force", "--yes"]
    )
    assert repoint.exit_code == 0, repoint.output
    assert _servers(_paths)["anchor"]["args"] == ["--env", str(env_b)]


def test_second_environment_with_distinct_name(_paths, tmp_path):
    env_a = tmp_path / "a"
    env_b = tmp_path / "work"
    init_environment(env_a)
    init_environment(env_b)
    runner.invoke(app, ["install", "claude-desktop", "--env", str(env_a), "--yes"])
    runner.invoke(
        app,
        ["install", "claude-desktop", "--env", str(env_b), "--name", "anchor-work", "--yes"],
    )
    servers = _servers(_paths)
    assert servers["anchor"]["args"] == ["--env", str(env_a)]
    assert servers["anchor-work"]["args"] == ["--env", str(env_b)]


def test_idempotent_same_name_same_env(_paths, tmp_path):
    env_dir = tmp_path / "env"
    init_environment(env_dir)
    runner.invoke(app, ["install", "claude-desktop", "--env", str(env_dir), "--yes"])
    again = runner.invoke(app, ["install", "claude-desktop", "--env", str(env_dir), "--yes"])
    assert again.exit_code == 0, again.output


def test_create_initializes_environment(_paths, tmp_path):
    env_dir = tmp_path / "fresh"
    result = runner.invoke(
        app, ["install", "claude-desktop", "--env", str(env_dir), "--create", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert (env_dir / "anchor.toml").is_file()


def test_privacy_zone_is_echoed(_paths, tmp_path):
    env_dir = tmp_path / "env"
    init_environment(env_dir, settings={"provider": "local"})
    result = runner.invoke(
        app, ["install", "claude-desktop", "--env", str(env_dir), "--yes"]
    )
    assert "Egress zone:" in result.output
