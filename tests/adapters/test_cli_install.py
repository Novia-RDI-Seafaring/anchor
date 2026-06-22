"""`anchor install` — env-pointer config + skill writes, idempotent."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.install import (
    _claude_code_paths,
    _install_env_pointer,
    _write_json,
    install_app,
)
from anchor.infra import environment as env_mod
from anchor.infra.environment import create_env

runner = CliRunner()


@pytest.fixture
def home(monkeypatch, tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))  # windows-safe
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", h / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    monkeypatch.delenv("ANCHOR_ENV", raising=False)
    return h


def test_claude_code_targets_dot_claude_json(home):
    mcp_path, skill_dir = _claude_code_paths()
    assert mcp_path == home / ".claude.json"
    assert skill_dir == home / ".claude" / "skills" / "anchor"


def test_env_pointer_merges_and_preserves_state(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}, "numStartups": 7}),
        encoding="utf-8",
    )
    _install_env_pointer(cfg, "local", dry_run=False)
    result = json.loads(cfg.read_text())
    assert result["numStartups"] == 7
    assert set(result["mcpServers"]) == {"other", "anchor"}
    assert result["mcpServers"]["anchor"]["args"] == ["--env", "local"]


def test_write_json_is_atomic_and_backs_up(tmp_path):
    target = tmp_path / ".claude.json"
    target.write_text('{"keep": 1}\n', encoding="utf-8")
    _write_json(target, {"keep": 1, "added": 2})
    assert json.loads(target.read_text())["added"] == 2
    backup = tmp_path / ".claude.json.anchorbak"
    assert backup.exists() and json.loads(backup.read_text()) == {"keep": 1}
    assert not (tmp_path / ".claude.json.tmp").exists()


def test_install_help_distinguishes_registration_from_tool_install():
    result = CliRunner().invoke(install_app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Register Anchor with an AI harness" in result.output
    assert "uv tool install anchor-kb" in " ".join(result.output.split())


def test_install_claude_code_writes_env_pointer_and_skill(home):
    create_env("local")
    result = runner.invoke(install_app, ["claude-code", "--env", "local"])
    assert result.exit_code == 0, result.output
    cfg = json.loads((home / ".claude.json").read_text())
    assert cfg["mcpServers"]["anchor"]["args"] == ["--env", "local"]
    skill = (home / ".claude" / "skills" / "anchor" / "SKILL.md").read_text()
    assert "name: anchor" in skill
    assert "ingest_pdf" in skill
    assert "canvas_add_node" in skill


def test_install_claude_code_defaults_to_default_env(home):
    create_env("local")  # default env name resolves to "local"
    result = runner.invoke(install_app, ["claude-code"])
    assert result.exit_code == 0, result.output
    cfg = json.loads((home / ".claude.json").read_text())
    assert cfg["mcpServers"]["anchor"]["args"] == ["--env", "local"]


def test_install_idempotent(home):
    create_env("local")
    runner.invoke(install_app, ["claude-code", "--env", "local"])
    result2 = runner.invoke(install_app, ["claude-code", "--env", "local"])
    assert result2.exit_code == 0
    cfg = json.loads((home / ".claude.json").read_text())
    assert list(cfg["mcpServers"].keys()) == ["anchor"]


def test_install_preserves_other_mcp_servers(home):
    create_env("local")
    config_path = home / ".claude.json"
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/x"}}}))
    runner.invoke(install_app, ["claude-code", "--env", "local"])
    cfg = json.loads(config_path.read_text())
    assert "other" in cfg["mcpServers"]
    assert "anchor" in cfg["mcpServers"]


def test_dry_run_makes_no_writes(home):
    create_env("local")
    result = runner.invoke(install_app, ["claude-code", "--env", "local", "--dry-run"])
    assert result.exit_code == 0
    assert "[dry-run]" in result.output
    assert not (home / ".claude.json").exists()
    assert not (home / ".claude" / "skills" / "anchor").exists()


def test_install_print_emits_plans(home):
    create_env("local")
    result = runner.invoke(install_app, ["print"])
    assert result.exit_code == 0, result.output
    assert "claude-code" in result.output
    assert "cursor" in result.output
    assert "--env" in result.output
