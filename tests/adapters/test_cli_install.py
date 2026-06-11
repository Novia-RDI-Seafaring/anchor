"""`anchor install` — config + skill writes, idempotent."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from anchor.adapters.cli.install import (
    _claude_code_paths,
    _install_mcp,
    _write_json,
    install_app,
)


def test_claude_code_targets_dot_claude_json():
    # Claude Code reads MCP servers from ~/.claude.json, NOT ~/.claude/mcp.json.
    mcp_path, skill_dir = _claude_code_paths()
    assert mcp_path == Path.home() / ".claude.json"
    assert skill_dir == Path.home() / ".claude" / "skills" / "anchor"


def test_install_mcp_merges_and_preserves_state(tmp_path):
    # Writing the anchor entry must preserve the rest of ~/.claude.json
    # (other MCP servers and unrelated Claude Code state).
    cfg = tmp_path / ".claude.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}, "numStartups": 7}),
        encoding="utf-8",
    )
    _install_mcp(cfg, tmp_path / "data", pin=False, dry_run=False)
    result = json.loads(cfg.read_text())
    assert result["numStartups"] == 7  # unrelated state preserved
    assert set(result["mcpServers"]) == {"other", "anchor"}  # other server kept


def test_write_json_is_atomic_and_backs_up(tmp_path):
    target = tmp_path / ".claude.json"
    target.write_text('{"keep": 1}\n', encoding="utf-8")
    _write_json(target, {"keep": 1, "added": 2})
    assert json.loads(target.read_text())["added"] == 2
    backup = tmp_path / ".claude.json.anchorbak"
    assert backup.exists() and json.loads(backup.read_text()) == {"keep": 1}
    assert not (tmp_path / ".claude.json.tmp").exists()  # temp cleaned up


def test_install_help_distinguishes_registration_from_tool_install():
    result = CliRunner().invoke(install_app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Register Anchor with an AI harness" in result.output
    assert "uv tool install anchor-kb" in " ".join(result.output.split())


def test_install_claude_code_writes_mcp_entry_and_skill(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # windows-safe

    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    result = runner.invoke(install_app, ["claude-code", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output

    cfg = json.loads((home / ".claude.json").read_text())
    assert "anchor" in cfg["mcpServers"]
    assert cfg["mcpServers"]["anchor"]["args"] == ["--data-dir", str(data_dir.resolve())]

    skill = (home / ".claude" / "skills" / "anchor" / "SKILL.md").read_text()
    assert "name: anchor" in skill
    assert "ingest_pdf" in skill
    assert "canvas_add_node" in skill
    assert data_dir.is_dir()


def test_install_claude_code_default_is_folder_resolving(tmp_path, monkeypatch):
    # No --data-dir: register a folder-resolving entry (no baked path) so one
    # registration works for every `anchor init` project.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("ANCHOR_DATA_DIR", raising=False)

    result = CliRunner().invoke(install_app, ["claude-code"])
    assert result.exit_code == 0, result.output

    cfg = json.loads((home / ".claude.json").read_text())
    assert cfg["mcpServers"]["anchor"]["args"] == []  # no --data-dir baked in
    assert "resolved per project" in result.output
    # Skill still installed.
    assert (home / ".claude" / "skills" / "anchor" / "SKILL.md").exists()


def test_install_idempotent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # windows-safe

    data_dir = tmp_path / "anchor-data"
    runner = CliRunner()
    runner.invoke(install_app, ["claude-code", "--data-dir", str(data_dir)])
    # Second run shouldn't fail and shouldn't double the entry.
    result2 = runner.invoke(install_app, ["claude-code", "--data-dir", str(data_dir)])
    assert result2.exit_code == 0
    cfg = json.loads((home / ".claude.json").read_text())
    assert list(cfg["mcpServers"].keys()) == ["anchor"]


def test_install_preserves_other_mcp_servers(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # windows-safe

    config_path = home / ".claude.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/x"}}}))

    runner = CliRunner()
    runner.invoke(install_app, ["claude-code", "--data-dir", str(tmp_path / "data")])
    cfg = json.loads(config_path.read_text())
    assert "other" in cfg["mcpServers"]
    assert "anchor" in cfg["mcpServers"]


def test_dry_run_makes_no_writes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # windows-safe

    runner = CliRunner()
    result = runner.invoke(
        install_app,
        ["claude-code", "--data-dir", str(tmp_path / "data"), "--dry-run"],
    )
    assert result.exit_code == 0
    assert "[dry-run]" in result.output
    assert not (home / ".claude.json").exists()
    assert not (home / ".claude" / "skills" / "anchor").exists()


def test_install_print_target_emits_plans(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(install_app, ["print", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "cursor" in result.output


def test_install_print_default_is_folder_resolving(tmp_path, monkeypatch):
    # With no --data-dir, `print` shows the folder-resolving default (no baked
    # path) for each target — not a pinned dir.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("ANCHOR_DATA_DIR", raising=False)

    result = CliRunner().invoke(install_app, ["print"])

    assert result.exit_code == 0, result.output
    assert "resolved per project" in result.output
