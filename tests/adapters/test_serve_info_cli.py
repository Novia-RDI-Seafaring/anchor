"""`anchor serve-info` lists serve->project bindings; `canvas url` uses them.

Closes the #177 gap: a canvas URL reflects the actual serve port for this
project, not a hardcoded :8002.
"""
from __future__ import annotations

from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra import serve_registry as sr
from anchor.infra.environment import create_env, create_project

runner = CliRunner()


def _setup_project(monkeypatch, tmp_path, name="pumps", port=8003):
    for var in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_CONFIG",
                "ANCHOR_DATA_DIR", "ANCHOR_HTTP_PORT", "ANCHOR_HTTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / name
    create_project(env, name, root=folder)
    data_dir = folder / ".anchor_data"
    path = sr.register_serve(
        host="127.0.0.1", port=port, data_dir=data_dir, started_at="t"
    )
    return data_dir, path


def test_serve_info_lists_running_bindings(monkeypatch, tmp_path):
    data_dir, path = _setup_project(monkeypatch, tmp_path, port=8007)
    try:
        result = runner.invoke(app, ["serve-info"])
        assert result.exit_code == 0, result.output
        assert "http://127.0.0.1:8007" in result.output
        assert "project=pumps" in result.output
        assert "env=work" in result.output
    finally:
        sr.unregister_serve(path)


def test_serve_info_by_project_prints_base_url(monkeypatch, tmp_path):
    data_dir, path = _setup_project(monkeypatch, tmp_path, port=8008)
    try:
        result = runner.invoke(app, ["serve-info", "--project", "pumps", "--env", "work"])
        assert result.exit_code == 0, result.output
        assert result.output.strip().endswith("http://127.0.0.1:8008")
    finally:
        sr.unregister_serve(path)


def test_serve_info_empty(monkeypatch, tmp_path):
    for var in ("ANCHOR_ENV", "ANCHOR_PROJECT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    result = runner.invoke(app, ["serve-info"])
    assert result.exit_code == 0, result.output
    assert "no running anchor serve" in result.output


def test_canvas_url_reflects_running_serve_port(monkeypatch, tmp_path):
    data_dir, path = _setup_project(monkeypatch, tmp_path, port=8011)
    try:
        result = runner.invoke(
            app, ["canvas", "url", "agentic-engineering-map", "--data-dir", str(data_dir)]
        )
        assert result.exit_code == 0, result.output
        # The bumped port (#177): the URL points at THIS project's serve, not :8002.
        assert "http://127.0.0.1:8011/c/agentic-engineering-map" in result.output
        assert ":8002" not in result.output
    finally:
        sr.unregister_serve(path)


def test_canvas_url_warns_when_no_serve_for_project(monkeypatch, tmp_path):
    for var in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_HTTP_PORT", "ANCHOR_HTTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")
    data_dir = tmp_path / "lonely" / ".anchor_data"
    result = runner.invoke(app, ["canvas", "url", "x", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "no `anchor serve`" in result.output  # warned on stderr
