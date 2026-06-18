"""`anchor init` — create an environment (provider picker) + default project."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def _env_toml(tmp_path, name="local"):
    return (tmp_path / ".anchor" / "envs" / name / "env.toml").read_text()


def test_init_creates_default_env_and_project(tmp_path):
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "local"' in toml
    assert "data_dir" not in toml
    for sub in ("bronze", "silver", "gold", "canvases"):
        assert (tmp_path / ".anchor" / "envs" / "local" / "projects" / "default" / sub).is_dir()
    # first env becomes the default
    assert (tmp_path / ".anchor" / "default").read_text().strip() == "local"
    assert "nothing leaves the network" in result.output


def test_init_named_environment(tmp_path):
    result = runner.invoke(app, ["init", "work", "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "work" / "env.toml").is_file()


def test_init_local_has_no_vision(tmp_path):
    runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    toml = _env_toml(tmp_path)
    assert "openai_base_url" not in toml
    assert "polish_model" not in toml
    assert "api_key =" not in toml.lower()


def test_ollama_defaults_to_local_endpoint(tmp_path):
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "ollama"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "ollama"' in toml
    assert "http://localhost:11434/v1" in toml
    assert "polish_model" in toml


def test_azure_requires_base_url(tmp_path):
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "azure"])
    assert result.exit_code != 0
    assert "base-url" in result.output.lower()
    assert not (tmp_path / ".anchor" / "envs" / "local" / "env.toml").exists()


def test_azure_normalizes_endpoint(tmp_path):
    result = runner.invoke(
        app, ["init", "local", "--yes", "--provider", "azure",
               "--base-url", "https://x.openai.azure.com/", "--vision-model", "gpt-dep"]
    )
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'openai_base_url = "https://x.openai.azure.com/openai/v1/"' in toml
    assert "your Azure tenant / region" in result.output


def test_invalid_env_name_errors(tmp_path):
    result = runner.invoke(app, ["init", "../escape", "--yes", "--provider", "local"])
    assert result.exit_code == 2


def test_refuses_overwrite_without_force(tmp_path):
    runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    assert result.exit_code == 1
    assert "force" in result.output.lower()


def test_force_overwrites(tmp_path):
    runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    result = runner.invoke(
        app, ["init", "local", "--yes", "--provider", "openai", "--force", "--vision-model", "gpt-x"]
    )
    assert result.exit_code == 0, result.output
    assert "gpt-x" in _env_toml(tmp_path)


def test_harness_provider_needs_no_key(tmp_path):
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "harness"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "harness"' in toml
    assert "not needed" in result.output
    assert "agent" in result.output


def test_shows_next_steps(tmp_path):
    result = runner.invoke(app, ["init", "local", "--yes", "--provider", "local"])
    assert "Next steps" in result.output
    assert "anchor-mcp --env local" in result.output


def test_setup_api_key_writes_gitignored_env(tmp_path, monkeypatch):
    from anchor.adapters.cli import init as init_mod
    from anchor.infra.providers import get_provider

    monkeypatch.setattr(init_mod.typer, "prompt", lambda *a, **k: "az-secret-key")
    env_root = tmp_path / ".anchor" / "envs" / "work"
    env_root.mkdir(parents=True)
    init_mod._setup_api_key(env_root, get_provider("azure"), interactive=True)
    assert "ANCHOR_OPENAI_API_KEY=az-secret-key" in (env_root / ".env").read_text()
    assert "az-secret-key" not in (env_root / "env.toml").read_text() if (env_root / "env.toml").exists() else True


def test_init_requires_a_name(tmp_path):
    result = runner.invoke(app, ["init", "--yes", "--provider", "local"])
    assert result.exit_code == 2
    assert "Name the environment" in result.output


def test_init_accepts_env_flag(tmp_path):
    result = runner.invoke(app, ["init", "--env", "work", "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "work" / "env.toml").is_file()
