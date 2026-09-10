"""MCP + CLI presence surfaces — both read the running serve's roster."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import anchor.infra.presence as presence_mod
from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.mcp import handlers_canvas
from tests.fixtures.services import make_in_memory_services

runner = CliRunner()

_ROSTER = {
    "workspace": "w1",
    "present": [
        {
            "client_id": "abc",
            "kind": "human",
            "label": "browser",
            "connected_at": 1000.0,
            "via": "sse",
        },
        {
            "kind": "agent",
            "id": None,
            "label": "claude-code",
            "connected_at": 1010.0,
            "last_write_at": 1020.0,
            "via": "writes",
        },
    ],
    "serve": "http://127.0.0.1:8002",
}


async def test_mcp_canvas_presence_fetches_from_serve(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_fetch(data_dir: Path, slug: str, **_kw):
        seen["data_dir"] = data_dir
        seen["slug"] = slug
        return _ROSTER

    monkeypatch.setattr(presence_mod, "fetch_presence", fake_fetch)
    s = make_in_memory_services()
    out = json.loads(
        await handlers_canvas.call_tool(
            s.workspace, "canvas_presence", {"workspace_slug": "w1"},
            data_dir=tmp_path,
        )
    )
    assert out == _ROSTER
    assert seen == {"data_dir": tmp_path, "slug": "w1"}


async def test_mcp_canvas_presence_without_data_dir_is_an_error():
    s = make_in_memory_services()
    out = json.loads(
        await handlers_canvas.call_tool(
            s.workspace, "canvas_presence", {"workspace_slug": "w1"},
        )
    )
    assert "error" in out


def test_cli_canvas_presence_text_output(monkeypatch, tmp_path):
    monkeypatch.setattr(presence_mod, "fetch_presence", lambda *_a, **_k: _ROSTER)
    result = runner.invoke(
        cli_app, ["canvas", "presence", "w1", "--data-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert 'human "browser" - watching since' in result.output
    assert 'agent "claude-code" - writing since' in result.output


def test_cli_canvas_presence_json_output(monkeypatch, tmp_path):
    monkeypatch.setattr(presence_mod, "fetch_presence", lambda *_a, **_k: _ROSTER)
    result = runner.invoke(
        cli_app,
        ["canvas", "presence", "w1", "--data-dir", str(tmp_path), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == _ROSTER


def test_cli_canvas_presence_no_serve_notes_empty_roster(monkeypatch, tmp_path):
    # An isolated data dir means no registered serve: the roster is empty by
    # construction and the note explains why (exit 0 - not an error).
    import anchor.infra.serve_registry as serve_registry

    monkeypatch.setattr(serve_registry, "find_serve_for_data_dir", lambda _d: None)
    result = runner.invoke(
        cli_app, ["canvas", "presence", "w1", "--data-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "(nobody on this canvas)" in result.output
