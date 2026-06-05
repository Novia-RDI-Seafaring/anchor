"""`anchor init` — provider picker writes a non-secret project anchor.toml."""
from __future__ import annotations

from typer.testing import CliRunner

from anchor.adapters.cli.main import app

runner = CliRunner()


def test_local_provider_is_egress_free(tmp_path):
    result = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "local", "--data-dir", str(tmp_path / "d")]
    )
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'provider = "local"' in toml
    assert "openai_base_url" not in toml
    assert "polish_model" not in toml  # no vision stage at all
    assert "api_key =" not in toml.lower()
    assert "nothing leaves the network" in result.output


def test_data_dir_defaults_into_the_project(tmp_path):
    # No --data-dir: it should land in this folder, not global ~/anchor-data.
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    expected = str((tmp_path / "anchor-data").resolve())
    assert f'data_dir = "{expected}"' in toml


def test_ollama_defaults_to_local_endpoint(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "ollama"])
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'provider = "ollama"' in toml
    assert "http://localhost:11434/v1" in toml
    assert "polish_model" in toml
    assert "no internet egress" in result.output


def test_remote_embed_model_flag_is_recorded(tmp_path):
    result = runner.invoke(
        app,
        ["init", str(tmp_path), "--yes", "--provider", "openai",
         "--embed-model", "text-embedding-3-large", "--vision-model", "gpt-x"],
    )
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'embed_model = "text-embedding-3-large"' in toml
    assert "remote" in result.output  # readback flags the egress


def test_azure_requires_base_url(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "azure"])
    assert result.exit_code != 0
    assert "base-url" in result.output.lower()
    assert not (tmp_path / "anchor.toml").exists()


def test_azure_records_flagged_config(tmp_path):
    result = runner.invoke(
        app,
        [
            "init",
            str(tmp_path),
            "--yes",
            "--provider",
            "azure",
            "--base-url",
            "https://x.openai.azure.com/v1",
            "--vision-model",
            "gpt-deployment-a",
        ],
    )
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'provider = "azure"' in toml
    assert "https://x.openai.azure.com/v1" in toml
    assert "gpt-deployment-a" in toml
    assert "api_key =" not in toml.lower()
    # offered but flagged as not-yet-functional
    assert "#48" in result.output
    assert "your Azure tenant / region" in result.output


def test_custom_requires_base_url(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "custom"])
    assert result.exit_code != 0


def test_unknown_provider_errors(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "banana"])
    assert result.exit_code != 0
    assert "banana" in result.output


def test_refuses_overwrite_without_force(tmp_path):
    (tmp_path / "anchor.toml").write_text('provider = "local"\n')
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    assert result.exit_code == 1
    assert "force" in result.output.lower()


def test_force_overwrites(tmp_path):
    (tmp_path / "anchor.toml").write_text('provider = "local"\n')
    result = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "openai", "--force", "--vision-model", "gpt-x"]
    )
    assert result.exit_code == 0, result.output
    assert "gpt-x" in (tmp_path / "anchor.toml").read_text()
