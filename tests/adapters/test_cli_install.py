"""`anchor install` — config + skill writes, idempotent."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.install import install_app


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

    cfg = json.loads((home / ".claude" / "mcp.json").read_text())
    assert "anchor" in cfg["mcpServers"]
    assert cfg["mcpServers"]["anchor"]["args"] == ["--data-dir", str(data_dir.resolve())]

    skill = (home / ".claude" / "skills" / "anchor" / "SKILL.md").read_text()
    assert "name: anchor" in skill
    assert "ingest_pdf" in skill
    assert "canvas_add_node" in skill
    assert data_dir.is_dir()


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
    cfg = json.loads((home / ".claude" / "mcp.json").read_text())
    assert list(cfg["mcpServers"].keys()) == ["anchor"]


def test_install_preserves_other_mcp_servers(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # windows-safe

    config_path = home / ".claude" / "mcp.json"
    config_path.parent.mkdir(parents=True)
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
    assert not (home / ".claude" / "mcp.json").exists()
    assert not (home / ".claude" / "skills" / "anchor").exists()


def test_install_print_target_emits_plans(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(install_app, ["print", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "cursor" in result.output


def test_install_print_uses_anchor_data_dir_when_flag_is_omitted(tmp_path, monkeypatch):
    data_dir = tmp_path / "env-data"
    monkeypatch.setenv("ANCHOR_DATA_DIR", str(data_dir))

    result = CliRunner().invoke(install_app, ["print"])

    assert result.exit_code == 0, result.output
    assert str(data_dir.resolve()) in result.output
