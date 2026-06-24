"""`anchor env create` — provider picker; `anchor init` — folder-based project."""
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


# --------------------------------------------------------------------------- #
# `anchor env create` — the provider picker (the trust boundary)
# --------------------------------------------------------------------------- #
def test_env_create_makes_env_and_default_project(tmp_path):
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "local"' in toml
    assert "data_dir" not in toml
    base = tmp_path / ".anchor" / "envs" / "local" / "projects" / "default"
    for sub in ("bronze", "silver", "gold", "canvases"):
        assert (base / ".anchor_data" / sub).is_dir()
    # first env becomes the default
    assert (tmp_path / ".anchor" / "default").read_text().strip() == "local"
    assert "nothing leaves the network" in result.output


def test_env_create_named_environment(tmp_path):
    result = runner.invoke(app, ["env", "create", "work", "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "work" / "env.toml").is_file()


def test_local_has_no_vision(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    toml = _env_toml(tmp_path)
    assert "openai_base_url" not in toml
    assert "polish_model" not in toml
    assert "api_key =" not in toml.lower()


def test_ollama_defaults_to_local_endpoint(tmp_path):
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "ollama"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "ollama"' in toml
    assert "http://localhost:11434/v1" in toml
    assert "polish_model" in toml


def test_azure_requires_base_url(tmp_path):
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "azure"])
    assert result.exit_code != 0
    assert "base-url" in result.output.lower()
    assert not (tmp_path / ".anchor" / "envs" / "local" / "env.toml").exists()


def test_azure_normalizes_endpoint(tmp_path):
    result = runner.invoke(
        app, ["env", "create", "local", "--yes", "--provider", "azure",
               "--base-url", "https://x.openai.azure.com/", "--vision-model", "gpt-dep"]
    )
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'openai_base_url = "https://x.openai.azure.com/openai/v1/"' in toml
    assert "your Azure tenant / region" in result.output


def test_invalid_env_name_errors(tmp_path):
    result = runner.invoke(app, ["env", "create", "../escape", "--yes", "--provider", "local"])
    assert result.exit_code == 2


def test_refuses_overwrite_without_force(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    assert result.exit_code == 1
    assert "force" in result.output.lower()


def test_force_overwrites(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    result = runner.invoke(
        app,
        ["env", "create", "local", "--yes", "--provider", "openai", "--force", "--vision-model", "gpt-x"],
    )
    assert result.exit_code == 0, result.output
    assert "gpt-x" in _env_toml(tmp_path)


def test_harness_provider_needs_no_key(tmp_path):
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "harness"])
    assert result.exit_code == 0, result.output
    toml = _env_toml(tmp_path)
    assert 'provider = "harness"' in toml
    assert "not needed" in result.output
    assert "agent" in result.output


def test_shows_next_steps(tmp_path):
    result = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
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


# --------------------------------------------------------------------------- #
# `anchor init` — initialize a project in the current folder
# --------------------------------------------------------------------------- #
def _make_local_env():
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])


def test_init_project_in_folder(tmp_path, monkeypatch):
    _make_local_env()
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (folder / "anchor.toml").is_file()
    assert (folder / ".anchor_data" / "bronze").is_dir()
    # the project name defaults to the folder name and is registered in the env
    env = env_mod.resolve_environment("local")
    assert "pumps" in env.list_project_names()
    assert env.project_root("pumps") == folder


def test_init_without_env_errors_noninteractive(tmp_path, monkeypatch):
    """No env + no terminal + no --provider: refuse, never invent a trust boundary."""
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init"])  # CliRunner has no tty
    assert result.exit_code == 1
    assert "is not set up" in result.output
    assert "anchor env create local" in result.output
    assert not (folder / "anchor.toml").exists()
    assert not (tmp_path / ".anchor" / "envs" / "local" / "env.toml").exists()


def test_init_provider_flag_provisions_env(tmp_path, monkeypatch):
    """`anchor init --provider local` creates the env inline and binds the project."""
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init", "--provider", "local", "--yes"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "local" / "env.toml").is_file()
    assert (folder / "anchor.toml").is_file()
    assert 'provider = "local"' in (tmp_path / ".anchor" / "envs" / "local" / "env.toml").read_text()
    # the new env becomes the default (first one on the machine)
    assert (tmp_path / ".anchor" / "default").read_text().strip() == "local"


def test_init_provider_flag_provisions_named_env(tmp_path, monkeypatch):
    """`--provider` works for an explicit `--env` name too."""
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(
        app, ["init", "--env", "work", "--provider", "openai", "--vision-model", "gpt-x", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".anchor" / "envs" / "work" / "env.toml").is_file()
    assert 'env = "work"' in (folder / "anchor.toml").read_text()


def test_init_provider_ignored_when_env_exists(tmp_path, monkeypatch):
    _make_local_env()
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init", "--provider", "openai"])
    assert result.exit_code == 0, result.output
    assert "ignoring --provider" in result.output
    # bound to the existing local env, not reconfigured
    assert 'env = "local"' in (folder / "anchor.toml").read_text()


def test_init_explicit_project_name(tmp_path, monkeypatch):
    _make_local_env()
    folder = tmp_path / "somedir"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init", "pumps", "--description", "LKH pumps"])
    assert result.exit_code == 0, result.output
    env = env_mod.resolve_environment("local")
    assert env_mod.project_meta(env, "pumps").description == "LKH pumps"


def test_init_named_env_must_exist(tmp_path, monkeypatch):
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init", "--env", "openai"])
    assert result.exit_code == 1
    assert "anchor env create openai" in result.output


def test_init_binds_to_existing_named_env(tmp_path, monkeypatch):
    runner.invoke(app, ["env", "create", "openai", "--yes", "--provider", "openai",
                        "--vision-model", "gpt-x"])
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init", "--env", "openai"])
    assert result.exit_code == 0, result.output
    marker = (folder / "anchor.toml").read_text()
    assert 'env = "openai"' in marker


def test_init_refuses_existing_project_without_force(tmp_path, monkeypatch):
    _make_local_env()
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    runner.invoke(app, ["init"])
    again = runner.invoke(app, ["init"])
    assert again.exit_code == 1
    assert "already an Anchor project" in again.output


def test_init_shows_next_steps(tmp_path, monkeypatch):
    _make_local_env()
    folder = tmp_path / "pumps"
    folder.mkdir()
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["init"])
    assert "Next steps" in result.output
    assert "anchor ingest" in result.output
