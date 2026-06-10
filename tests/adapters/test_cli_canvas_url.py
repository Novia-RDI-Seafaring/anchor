"""`anchor canvas url` + `--version` — discoverability fixes from an AX report.

A live AX session had to grep the JS bundle to find the canvas route, and
`anchor --version` errored while `anchor version` worked.
"""
from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from anchor.adapters.cli.main import app

runner = CliRunner()


def test_version_flag_matches_subcommand():
    flag = runner.invoke(app, ["--version"])
    sub = runner.invoke(app, ["version"])
    assert flag.exit_code == 0, flag.output
    assert flag.output.strip() == sub.output.strip() == version("anchor-kb")


def test_canvas_url_prints_route(monkeypatch):
    monkeypatch.delenv("ANCHOR_HTTP_PORT", raising=False)
    monkeypatch.delenv("ANCHOR_HTTP_HOST", raising=False)
    result = runner.invoke(app, ["canvas", "url", "pump-analysis"])
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8002/c/pump-analysis" in result.output


def test_canvas_url_honors_configured_port(monkeypatch):
    monkeypatch.setenv("ANCHOR_HTTP_PORT", "9000")
    result = runner.invoke(app, ["canvas", "url", "x"])
    assert "http://127.0.0.1:9000/c/x" in result.output
