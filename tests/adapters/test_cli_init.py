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


def test_shows_next_steps(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    assert "Next steps" in result.output
    assert "anchor ingest" in result.output
    assert "anchor serve" in result.output


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
    # init self-corrects a bare resource/v1 URL to the Azure /openai/v1/ surface.
    assert 'openai_base_url = "https://x.openai.azure.com/openai/v1/"' in toml
    assert "gpt-deployment-a" in toml
    assert "api_key =" not in toml.lower()
    # Azure works via its OpenAI-compatible v1 surface — no "not implemented" flag.
    assert "#48" not in result.output
    assert "not implemented" not in result.output.lower()
    assert "your Azure tenant / region" in result.output


def test_azure_endpoint_normalized_from_bare_resource_url(tmp_path):
    # The common case: user pastes the portal resource URL with no API path.
    result = runner.invoke(
        app,
        ["init", str(tmp_path), "--yes", "--provider", "azure",
         "--base-url", "https://x.openai.azure.com/", "--vision-model", "gpt-deployment-a"],
    )
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'openai_base_url = "https://x.openai.azure.com/openai/v1/"' in toml
    assert "Adjusted endpoint" in result.output


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


def test_replaces_unreadable_toml_without_force(tmp_path):
    # A corrupt config (stray ANSI escape) should be replaced, not protected.
    (tmp_path / "anchor.toml").write_bytes(b'embed_model = "bad\x1bval"\n')
    result = runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    assert result.exit_code == 0, result.output
    assert "unreadable" in result.output.lower()
    import tomllib

    tomllib.loads((tmp_path / "anchor.toml").read_text())  # rewritten clean


def test_setup_api_key_writes_gitignored_env(tmp_path, monkeypatch):
    # Interactive key capture can't run through CliRunner (its stdin is not a tty,
    # so init's interactive gate is False). Drive the helper directly: a pasted
    # key lands in a gitignored .env and never in the toml.
    from anchor.adapters.cli import init as init_mod
    from anchor.infra.providers import get_provider

    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(init_mod.typer, "prompt", lambda *a, **k: "az-secret-key")

    (tmp_path / "anchor.toml").write_text('provider = "azure"\n')  # a project exists
    init_mod._setup_api_key(tmp_path, get_provider("azure"), interactive=True)

    assert "ANCHOR_OPENAI_API_KEY=az-secret-key" in (tmp_path / ".env").read_text()
    assert ".env" in (tmp_path / ".gitignore").read_text()
    assert "az-secret-key" not in (tmp_path / "anchor.toml").read_text()


def test_setup_api_key_skips_when_key_left_blank(tmp_path, monkeypatch):
    from anchor.adapters.cli import init as init_mod
    from anchor.infra.providers import get_provider

    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(init_mod.typer, "prompt", lambda *a, **k: "")  # user skips
    init_mod._setup_api_key(tmp_path, get_provider("azure"), interactive=True)
    assert not (tmp_path / ".env").exists()


def test_azure_init_warns_when_only_personal_key_present(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-personal")
    result = runner.invoke(
        app,
        ["init", str(tmp_path), "--yes", "--provider", "azure",
         "--base-url", "https://x.openai.azure.com/", "--vision-model", "gpt-dep"],
    )
    assert result.exit_code == 0, result.output
    assert "not the right credential" in result.output.lower()


def test_force_overwrites(tmp_path):
    (tmp_path / "anchor.toml").write_text('provider = "local"\n')
    result = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "openai", "--force", "--vision-model", "gpt-x"]
    )
    assert result.exit_code == 0, result.output
    assert "gpt-x" in (tmp_path / "anchor.toml").read_text()


def test_harness_provider_needs_no_key_and_no_endpoint(tmp_path):
    result = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "harness",
              "--data-dir", str(tmp_path / "d")],
    )
    assert result.exit_code == 0, result.output
    toml = (tmp_path / "anchor.toml").read_text()
    assert 'provider = "harness"' in toml
    assert "openai_base_url" not in toml
    assert "api_key =" not in toml.lower()
    # The readback is honest: ingestion happens through the agent, no key.
    assert "not needed" in result.output
    assert "agent" in result.output
    assert "ingest-session" in result.output
