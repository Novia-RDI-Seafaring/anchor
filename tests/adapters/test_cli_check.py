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


def test_probe_sends_no_token_cap_param(tmp_path, monkeypatch):
    # gpt-5.x / o-series reject max_tokens; older endpoints reject
    # max_completion_tokens. The probe must send neither (matching ingestion).
    recorded: dict = {}

    class _Completions:
        def create(self, **kw):
            recorded.update(kw)
            return object()

    class _Chat:
        completions = _Completions()

    class _Fake:
        chat = _Chat()

    from anchor.extensions.anchor_pdfs.infra.llm import openai_client as oc

    monkeypatch.setattr(oc, "make_openai_client", lambda *a, **k: _Fake())
    (tmp_path / "anchor.toml").write_text(
        'provider = "openai"\n'
        f'data_dir = "{tmp_path / "d"}"\n'
        'region_model = "gpt-5.4"\nembed_model = "BAAI/bge-small-en-v1.5"\n'
    )
    result = _run_check(tmp_path, "--probe", env={"ANCHOR_OPENAI_API_KEY": "k"})
    assert result.exit_code == 0, result.output
    assert "max_tokens" not in recorded
    assert "max_completion_tokens" not in recorded
    assert recorded.get("model") == "gpt-5.4"


def test_check_local_provider_needs_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no egress" in result.output


def test_check_flags_nonexistent_data_dir(tmp_path, monkeypatch):
    # check must not imply a data dir exists when it does not (issue #90).
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    missing = tmp_path / "no-such-dir" / "anchor-data"
    result = _run_check(tmp_path, env={"ANCHOR_DATA_DIR": str(missing)})
    assert str(missing) in result.output
    assert "does not exist yet" in result.output


def test_check_no_note_when_data_dir_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    runner.invoke(app, ["init", str(tmp_path), "--yes", "--provider", "local"])
    present = tmp_path / "data"
    present.mkdir()
    result = _run_check(tmp_path, env={"ANCHOR_DATA_DIR": str(present)})
    assert "does not exist yet" not in result.output


def test_check_harness_mode_is_ready_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "harness",
              "--data-dir", str(tmp_path / "d")],
    )
    assert r.exit_code == 0, r.output
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "agent harness" in result.output
    assert "not needed" in result.output
    assert "Harness ingest sessions" in result.output
    assert "none open" in result.output
    assert "Ready" in result.output


def test_check_harness_mode_lists_open_sessions(tmp_path, monkeypatch):
    import json

    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    data_dir = tmp_path / "d"
    r = runner.invoke(
        app, ["init", str(tmp_path), "--yes", "--provider", "harness",
              "--data-dir", str(data_dir)],
    )
    assert r.exit_code == 0, r.output
    session_dir = data_dir / "staging" / "ingest" / "ing-abc123"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(json.dumps({
        "session_id": "ing-abc123", "slug": "demo", "state": "open",
        "page_count": 3,
        "pages": {"1": {"status": "submitted"}, "2": {"status": "pending"},
                  "3": {"status": "pending"}},
    }), encoding="utf-8")
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "ing-abc123" in result.output
    assert "1/3 pages submitted" in result.output
