"""`anchor install opencode` named local MCP configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import install_named
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env

runner = CliRunner()


@pytest.fixture(autouse=True)
def _paths(monkeypatch, tmp_path):
    config = tmp_path / ".config" / "opencode" / "opencode.json"
    monkeypatch.setattr(install_named, "_opencode_config_path", lambda: config)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    return config


def _servers(config: Path) -> dict[str, object]:
    return json.loads(config.read_text(encoding="utf-8"))["mcp"]


def _is_anchor_mcp_command(command: list[str]) -> bool:
    return Path(command[0]).name.lower() in {"anchor-mcp", "anchor-mcp.exe"}


def test_install_writes_named_local_server(_paths):
    create_env("local")

    result = runner.invoke(app, ["install", "opencode", "--env", "local", "--yes"])

    assert result.exit_code == 0, result.output
    config = json.loads(_paths.read_text(encoding="utf-8"))
    assert config["$schema"] == "https://opencode.ai/config.json"
    entry = config["mcp"]["anchor-local"]
    assert entry["type"] == "local"
    assert entry["enabled"] is True
    assert entry["command"][1:] == ["--env", "local"]
    assert _is_anchor_mcp_command(entry["command"])


def test_install_preserves_unrelated_content_and_backs_up(_paths):
    _paths.parent.mkdir(parents=True)
    original = {
        "$schema": "https://opencode.ai/config.json",
        "model": "anthropic/claude-sonnet-4-5",
        "mcp": {"other": {"type": "remote", "url": "https://example.test/mcp"}},
    }
    _paths.write_text(json.dumps(original, indent=2), encoding="utf-8")
    create_env("local")

    result = runner.invoke(app, ["install", "opencode", "--env", "local", "--yes"])

    assert result.exit_code == 0, result.output
    updated = json.loads(_paths.read_text(encoding="utf-8"))
    assert updated["model"] == original["model"]
    assert updated["mcp"]["other"] == original["mcp"]["other"]
    backup = _paths.with_name(_paths.name + ".anchorbak")
    assert json.loads(backup.read_text(encoding="utf-8")) == original


def test_collision_requires_force(_paths):
    create_env("local")
    create_env("work")
    runner.invoke(
        app,
        ["install", "opencode", "--env", "local", "--name", "anchor", "--yes"],
    )

    clash = runner.invoke(
        app,
        ["install", "opencode", "--env", "work", "--name", "anchor", "--yes"],
    )
    assert clash.exit_code == 1
    assert "already points at" in clash.output
    assert _servers(_paths)["anchor"]["command"][2] == "local"

    repoint = runner.invoke(
        app,
        [
            "install",
            "opencode",
            "--env",
            "work",
            "--name",
            "anchor",
            "--force",
            "--yes",
        ],
    )
    assert repoint.exit_code == 0, repoint.output
    assert _servers(_paths)["anchor"]["command"][2] == "work"


def test_dry_run_does_not_write(_paths):
    create_env("local")

    result = runner.invoke(app, ["install", "opencode", "--env", "local", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not _paths.exists()
