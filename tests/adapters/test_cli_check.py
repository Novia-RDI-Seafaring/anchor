"""`anchor check` — verify the data zone, repair the endpoint, gate on readiness."""
from __future__ import annotations

import shutil
import tomllib

import pytest
from typer.testing import CliRunner

from anchor.adapters.cli import check as check_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod

runner = CliRunner()


@pytest.fixture(autouse=True)
def _stub_ocr_probe(monkeypatch):
    """Never import the real onnxruntime (issue #195 numpy double-load).

    ``anchor check`` probes the OCR backend by importing ``onnxruntime``.
    Importing the real wheel from the test suite is what triggers the flaky
    'cannot load module more than once per process' failure, so stub the probe
    to report the backend as importable. Tests that assert on the probe's own
    branches live in ``test_cli_check_ocr.py`` and patch it explicitly.
    """
    monkeypatch.setattr(check_mod, "_probe_ocr_backend", lambda: (True, None))


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


def test_check_missing_key_prints_actionable_remedy(tmp_path):
    # A keyed provider with no ANCHOR_OPENAI_API_KEY: gold is silently skipped.
    # check must name the .env path, the exact key var, and the offline fallback.
    _init_azure(tmp_path)
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "silently skipped" in result.output
    assert "ANCHOR_OPENAI_API_KEY" in result.output
    assert "OPENAI_API_KEY in that .env is ignored" in result.output
    assert str(_env_dir(tmp_path) / ".env") in result.output
    assert "--provider harness" in result.output
    assert "ingest_begin" in result.output


def test_check_remote_embedding_without_key_prints_remedy(tmp_path):
    _write_env(
        tmp_path,
        'provider = "azure"\n'
        'openai_base_url = "https://x.openai.azure.com/openai/v1/"\n'
        'embed_model = "text-embedding-3-small"\n',
    )

    result = _run_check(tmp_path)

    assert result.exit_code == 1, result.output
    assert "ANCHOR_OPENAI_API_KEY" in result.output
    assert "Not ready" in result.output


def test_check_unset_provider_prints_remedy(tmp_path):
    # An env.toml with no provider set at all: gold would be silently skipped.
    _write_env(
        tmp_path,
        'embed_model = "BAAI/bge-small-en-v1.5"\n',
    )
    result = _run_check(tmp_path)
    assert result.exit_code == 1, result.output
    assert "provider" in result.output
    assert "silently skipped" in result.output
    assert "ANCHOR_OPENAI_API_KEY" in result.output
    assert "--provider harness" in result.output


def test_check_no_remedy_when_key_present(tmp_path):
    _init_azure(tmp_path)
    result = _run_check(tmp_path, env={"ANCHOR_OPENAI_API_KEY": "az-secret"})
    assert result.exit_code == 0, result.output
    assert "silently skipped" not in result.output
    assert "--provider harness" not in result.output


def test_check_no_remedy_for_harness_provider(tmp_path):
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "harness"])
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "silently skipped" not in result.output


def _provider_help(func) -> str:
    """The --provider option's help text from a typer command callback.

    Introspects the default value of the ``provider`` parameter (a
    ``typer.Option``) rather than rendering ``--help``, which is brittle under
    this environment's Click/Typer version.
    """
    import inspect

    default = inspect.signature(func).parameters["provider"].default
    return getattr(default, "help", "") or ""


def test_env_create_provider_help_lists_harness():
    from anchor.adapters.cli.envcmd import env_create

    assert "harness" in _provider_help(env_create)


def test_init_provider_help_lists_harness():
    from anchor.adapters.cli.init import create_environment, init

    assert "harness" in _provider_help(init)
    assert "harness" in _provider_help(create_environment)


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


# --------------------------------------------------------------------------- #
# #303 — check leads with cwd project resolution
# --------------------------------------------------------------------------- #
def _make_marker_project(tmp_path, name="pumps", env_name="local"):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "anchor.toml").write_text(
        f'env = "{env_name}"\nname = "{name}"\n', encoding="utf-8"
    )
    return folder


def test_check_leads_with_cwd_project(monkeypatch, tmp_path):
    # In a folder with an anchor.toml, bare `anchor check` reports THAT
    # project — its name, the marker it came from, and its data dir —
    # before anything else, so "where will my ingest land?" is answered.
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    folder = _make_marker_project(tmp_path)
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("Project"), result.output
    assert f"project        : pumps  (from {folder / 'anchor.toml'})" in result.output
    assert str(folder / ".anchor_data") in result.output
    assert "serve          : none running for this project" in result.output


def test_check_without_marker_names_env_default(monkeypatch, tmp_path):
    # In a folder with no anchor.toml, check must say so and name the
    # project commands will actually use, instead of printing "Ready"
    # against an unstated default.
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = _run_check(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no anchor.toml here" in result.output
    assert "project        : default" in result.output
    assert str(_default_dir(tmp_path)) in result.output


def test_check_project_flag_overrides_cwd_marker(monkeypatch, tmp_path):
    # Explicit --project wins over the cwd anchor.toml, and the report
    # names --project as the source rather than claiming the marker.
    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    folder = _make_marker_project(tmp_path)
    monkeypatch.chdir(folder)
    result = runner.invoke(app, ["check", "--env", "local", "--project", "other"])
    assert "project        : other  (from --project)" in result.output
    assert "pumps" not in result.output
    expected_dir = _env_dir(tmp_path) / "projects" / "other" / ".anchor_data"
    assert str(expected_dir) in result.output


def test_check_serve_report_scoped_to_resolved_project(monkeypatch, tmp_path):
    # The serve line must reflect the serve bound to the RESOLVED project's
    # data dir — a serve on :8003 for the cwd project was invisible while
    # check reported the env default's :8002 (#303).
    from anchor.infra import serve_registry as sr

    runner.invoke(app, ["env", "create", "local", "--yes", "--provider", "local"])
    folder = _make_marker_project(tmp_path)
    data_dir = folder / ".anchor_data"
    data_dir.mkdir()
    monkeypatch.chdir(folder)
    path = sr.register_serve(
        host="127.0.0.1", port=8009, data_dir=data_dir, started_at="t"
    )
    try:
        result = runner.invoke(app, ["check"])
        assert "serve          : running at http://127.0.0.1:8009" in result.output
    finally:
        sr.unregister_serve(path)
