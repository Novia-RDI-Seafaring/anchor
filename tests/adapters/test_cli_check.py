"""`anchor check` — verify the data zone, repair the endpoint, gate on readiness."""
from __future__ import annotations

import tomllib

from typer.testing import CliRunner

from anchor.adapters.cli.main import app

runner = CliRunner()


def _init_azure(tmp_path, base_url="https://x.openai.azure.com/"):
    r = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "azure",
               "--base-url", base_url, "--vision-model", "gpt-dep"]
    )
    assert r.exit_code == 0, r.output


def _run_check(tmp_path, *args, env=None):
    # check resolves config from ANCHOR_CONFIG; pass an explicit, key-free env.
    base_env = {"ANCHOR_CONFIG": str(tmp_path / "anchor.toml")}
    if env:
        base_env.update(env)
    return runner.invoke(app, ["check", *args], env=base_env)


def test_check_reports_zone_and_flags_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _init_azure(tmp_path)
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output  # not ready: no key
    assert "Data zone" in result.output
    assert "Azure OpenAI" in result.output
    assert "NOT set" in result.output


def test_check_fix_repairs_endpoint_in_toml(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Write a config with a bare (wrong) Azure endpoint directly.
    (tmp_path / "anchor.toml").write_text(
        'provider = "azure"\n'
        f'data_dir = "{tmp_path / "d"}"\n'
        'embed_model = "BAAI/bge-small-en-v1.5"\n'
        'openai_base_url = "https://x.openai.azure.com/"\n'
        'polish_model = "gpt-dep"\nregion_model = "gpt-dep"\n'
    )
    result = _run_check(tmp_path, "--fix")
    assert "fixed." in result.output
    data = tomllib.loads((tmp_path / "anchor.toml").read_text())
    assert data["openai_base_url"] == "https://x.openai.azure.com/openai/v1/"


def test_check_ready_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_OPENAI_API_KEY", "az-secret")
    _init_azure(tmp_path)  # writes a normalized endpoint already
    result = _run_check(tmp_path, env={"ANCHOR_OPENAI_API_KEY": "az-secret"})
    assert result.exit_code == 0, result.output
    assert "Ready" in result.output


def test_check_local_provider_needs_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no egress" in result.output
