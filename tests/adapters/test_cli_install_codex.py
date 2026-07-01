"""`anchor install codex` — named pointer entry in ~/.codex/config.toml."""
from __future__ import annotations

import tomllib

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import install as install_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env

runner = CliRunner()


@pytest.fixture(autouse=True)
def _paths(monkeypatch, tmp_path):
    config = tmp_path / ".codex" / "config.toml"
    monkeypatch.setattr(install_mod, "_codex_config_path", lambda: config)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    return config


def _servers(config):
    return tomllib.loads(config.read_text())["mcp_servers"]


def test_install_writes_named_pointer_entry(_paths):
    create_env("local")
    result = runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    assert result.exit_code == 0, result.output
    entry = _servers(_paths)["anchor-local"]
    assert entry["args"] == ["--env", "local"]
    assert entry["command"].endswith("anchor-mcp")


def test_config_is_valid_toml_and_reparses(_paths):
    create_env("local")
    runner.invoke(app, ["install", "codex", "--env", "local", "--name", "anchor", "--yes"])
    data = tomllib.loads(_paths.read_text())
    assert data["mcp_servers"]["anchor"]["command"].endswith("anchor-mcp")
    assert data["mcp_servers"]["anchor"]["args"] == ["--env", "local"]


def test_install_preserves_unrelated_content(_paths):
    _paths.parent.mkdir(parents=True, exist_ok=True)
    _paths.write_text(
        'model = "o3"\n'
        "\n"
        "[mcp_servers.other]\n"
        'command = "other-mcp"\n'
        'args = ["--foo"]\n'
    )
    create_env("local")
    result = runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    assert result.exit_code == 0, result.output
    data = tomllib.loads(_paths.read_text())
    # Top-level scalar preserved.
    assert data["model"] == "o3"
    # Unrelated server preserved.
    assert data["mcp_servers"]["other"]["command"] == "other-mcp"
    assert data["mcp_servers"]["other"]["args"] == ["--foo"]
    # New entry added.
    assert data["mcp_servers"]["anchor-local"]["args"] == ["--env", "local"]


def test_backup_written_before_overwrite(_paths):
    _paths.parent.mkdir(parents=True, exist_ok=True)
    original = 'model = "o3"\n'
    _paths.write_text(original)
    create_env("local")
    runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    backup = _paths.parent / (_paths.name + ".anchorbak")
    assert backup.read_text() == original


def test_collision_refused_without_force(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(app, ["install", "codex", "--env", "local", "--name", "anchor", "--yes"])
    clash = runner.invoke(
        app, ["install", "codex", "--env", "work", "--name", "anchor", "--yes"]
    )
    assert clash.exit_code == 1
    assert "already points at" in clash.output
    assert _servers(_paths)["anchor"]["args"] == ["--env", "local"]


def test_force_repoints(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(app, ["install", "codex", "--env", "local", "--name", "anchor", "--yes"])
    repoint = runner.invoke(
        app, ["install", "codex", "--env", "work", "--name", "anchor", "--force", "--yes"]
    )
    assert repoint.exit_code == 0, repoint.output
    assert _servers(_paths)["anchor"]["args"] == ["--env", "work"]


def test_dry_run_writes_nothing(_paths):
    create_env("local")
    result = runner.invoke(app, ["install", "codex", "--env", "local", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert not _paths.exists()


def test_name_override(_paths):
    create_env("local")
    runner.invoke(app, ["install", "codex", "--env", "local", "--name", "my-anchor", "--yes"])
    servers = _servers(_paths)
    assert "my-anchor" in servers
    assert servers["my-anchor"]["args"] == ["--env", "local"]


def test_idempotent_same_name_same_env(_paths):
    create_env("local")
    runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    again = runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    assert again.exit_code == 0, again.output


def test_create_initializes_environment(_paths, tmp_path):
    result = runner.invoke(app, ["install", "codex", "--env", "fresh", "--create", "--yes"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "fresh" / "env.toml").is_file()


def test_privacy_zone_is_echoed(_paths):
    create_env("local", settings={"provider": "local"})
    result = runner.invoke(app, ["install", "codex", "--env", "local", "--yes"])
    assert "Data zone" in result.output
