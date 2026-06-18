"""`anchor install claude-desktop` — named pointer config (env by name)."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import install as install_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env

runner = CliRunner()


@pytest.fixture(autouse=True)
def _paths(monkeypatch, tmp_path):
    desktop = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr(install_mod, "_claude_desktop_config_path", lambda: desktop)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    return desktop


def _servers(desktop):
    return json.loads(desktop.read_text())["mcpServers"]


def test_install_writes_named_pointer_entry(_paths):
    create_env("local")
    result = runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    assert result.exit_code == 0, result.output
    entry = _servers(_paths)["anchor"]
    assert entry["args"] == ["--env", "local"]
    assert entry["command"].endswith("anchor-mcp")


def test_install_is_additive(_paths):
    _paths.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    create_env("local")
    runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    servers = _servers(_paths)
    assert "other" in servers
    assert "anchor" in servers


def test_collision_refused_without_force(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    clash = runner.invoke(app, ["install", "claude-desktop", "--env", "work", "--yes"])
    assert clash.exit_code == 1
    assert "already points at" in clash.output
    assert _servers(_paths)["anchor"]["args"] == ["--env", "local"]


def test_force_repoints(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    repoint = runner.invoke(
        app, ["install", "claude-desktop", "--env", "work", "--force", "--yes"]
    )
    assert repoint.exit_code == 0, repoint.output
    assert _servers(_paths)["anchor"]["args"] == ["--env", "work"]


def test_second_environment_with_distinct_name(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    runner.invoke(
        app, ["install", "claude-desktop", "--env", "work", "--name", "anchor-work", "--yes"]
    )
    servers = _servers(_paths)
    assert servers["anchor"]["args"] == ["--env", "local"]
    assert servers["anchor-work"]["args"] == ["--env", "work"]


def test_idempotent_same_name_same_env(_paths):
    create_env("local")
    runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    again = runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    assert again.exit_code == 0, again.output


def test_create_initializes_environment(_paths, tmp_path):
    result = runner.invoke(
        app, ["install", "claude-desktop", "--env", "fresh", "--create", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "fresh" / "env.toml").is_file()


def test_privacy_zone_is_echoed(_paths):
    create_env("local", settings={"provider": "local"})
    result = runner.invoke(app, ["install", "claude-desktop", "--env", "local", "--yes"])
    assert "Egress zone:" in result.output
