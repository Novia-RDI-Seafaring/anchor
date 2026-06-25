"""`anchor check` — verify the data zone, repair the endpoint, gate on readiness."""
from __future__ import annotations

import shutil
import tomllib

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


def _env_dir(tmp_path, name="local"):
    return tmp_path / ".anchor" / "envs" / name


def _default_dir(tmp_path, name="local"):
    return _env_dir(tmp_path, name) / "projects" / "default" / ".anchor_data"


def _write_env(tmp_path, body, name="local"):
    d = _env_dir(tmp_path, name)
    (d / "projects").mkdir(parents=True, exist_ok=True)
    (d / "env.toml").write_text(body)


def _init_azure(tmp_path, base_url="https://x.openai.azure.com/"):
    r = runner.invoke(
        app, ["env", "create", "local", "--yes", "--provider", "azure",
               "--base-url", base_url, "--vision-model", "gpt-dep"]
    )
    assert r.exit_code == 0, r.output


def _run_check(tmp_path, *args, env=None):
    return runner.invoke(app, ["check", "--env", "local", *args], env=env or {})


def test_check_reports_zone_and_flags_missing_key(tmp_path):
    _init_azure(tmp_path)
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "Data zone" in result.output
    assert "Azure OpenAI" in result.output
    assert "NOT set" in result.output


def test_check_fix_repairs_endpoint(tmp_path):
    _write_env(
        tmp_path,
        'provider = "azure"\n'
        'embed_model = "BAAI/bge-small-en-v1.5"\n'
        'openai_base_url = "https://x.openai.azure.com/"\n'
        'polish_model = "gpt-dep"\nregion_model = "gpt-dep"\n',
    )
    result = _run_check(tmp_path, "--fix")
    assert "fixed." in result.output
    data = tomllib.loads((_env_dir(tmp_path) / "env.toml").read_text())
    assert data["openai_base_url"] == "https://x.openai.azure.com/openai/v1/"


def test_check_ready_when_key_present(tmp_path):
    _init_azure(tmp_path)
    result = _run_check(tmp_path, env={"ANCHOR_OPENAI_API_KEY": "az-secret"})
    assert result.exit_code == 0, result.output
    assert "Ready" in result.output


def test_check_local_provider_needs_no_key(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no egress" in result.output


def test_env_create_local_records_local_only(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    data = tomllib.loads((_env_dir(tmp_path) / "env.toml").read_text())
    assert data["local_only"] is True


def test_check_local_only_echoes_no_egress_posture(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    # The asserted no-egress line + the model set a prefetch would warm.
    assert "local-only" in result.output
    assert "offline models" in result.output
    assert "BAAI/bge-small-en-v1.5" in result.output


def test_check_flags_nonexistent_project_dir(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    shutil.rmtree(_default_dir(tmp_path))
    result = _run_check(tmp_path)
    assert str(_default_dir(tmp_path)) in result.output
    assert "created on first ingest" in result.output


def test_check_no_note_when_project_exists(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    result = _run_check(tmp_path)
    assert "created on first ingest" not in result.output


def test_check_harness_mode_is_ready_without_key(tmp_path):
    r = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "harness"])
    assert r.exit_code == 0, r.output
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "agent harness" in result.output
    assert "not needed" in result.output
    assert "Harness ingest sessions" in result.output
    assert "none open" in result.output
    assert "Ready" in result.output


def test_check_harness_mode_lists_open_sessions(tmp_path):
    import json

    r = runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "harness"])
    assert r.exit_code == 0, r.output
    session_dir = _default_dir(tmp_path) / "staging" / "ingest" / "ing-abc123"
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
