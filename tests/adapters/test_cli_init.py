"""`anchor init` writes a non-secret project anchor.toml."""
from __future__ import annotations

from typer.testing import CliRunner

from anchor.adapters.cli.main import app


def test_init_local_only_writes_secret_free_toml(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", str(tmp_path), "--yes", "--local-only", "--data-dir", str(tmp_path / "data")],
    )
    assert result.exit_code == 0, result.output

    toml = (tmp_path / "anchor.toml").read_text()
    assert "data_dir" in toml
    assert "embed_model" in toml
    # local-only: no remote endpoint recorded, and never a secret assignment
    # (the env-var name may appear in the guidance comment, but never `= "..."`).
    assert "openai_base_url" not in toml
    assert "api_key =" not in toml.lower()
    assert "local-only" in result.output


def test_init_remote_records_endpoint_not_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "init",
            str(tmp_path),
            "--yes",
            "--openai-base-url",
            "https://example.openai.azure.com/v1",
            "--polish-model",
            "gpt-deployment-a",
            "--region-model",
            "gpt-deployment-a",
        ],
    )
    assert result.exit_code == 0, result.output

    toml = (tmp_path / "anchor.toml").read_text()
    assert "https://example.openai.azure.com/v1" in toml
    assert "gpt-deployment-a" in toml
    assert "api_key =" not in toml.lower()
    # readback warns the key is absent rather than inventing one.
    assert "example.openai.azure.com" in result.output
    assert "ANCHOR_OPENAI_API_KEY" in result.output


def test_init_refuses_overwrite_without_force(tmp_path):
    (tmp_path / "anchor.toml").write_text('data_dir = "x"\n')
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "force" in result.output.lower()


def test_init_force_overwrites(tmp_path):
    (tmp_path / "anchor.toml").write_text('data_dir = "old"\n')
    runner = CliRunner()
    result = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--local-only", "--force", "--embed-model", "new-embed"]
    )
    assert result.exit_code == 0, result.output
    assert "new-embed" in (tmp_path / "anchor.toml").read_text()
