"""`anchor ingest-session` - shell surface of the harness protocol.

These stay off the heavy paths (no docling run): they exercise argument
handling, JSON output, and exit codes against an empty data dir.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.main import app

runner = CliRunner()


def test_status_unknown_session_exits_nonzero_with_json(tmp_path):
    result = runner.invoke(
        app, ["ingest-session", "status", "--slug", "nope", "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 1, result.output
    assert "no ingest session found" in json.loads(result.output)["error"]


def test_status_requires_session_id_or_slug(tmp_path):
    result = runner.invoke(
        app, ["ingest-session", "status", "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "SESSION_ID or --slug" in result.output


def test_submit_page_rejects_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = runner.invoke(
        app,
        ["ingest-session", "submit-page", "ing-x", "1",
         "--file", str(bad), "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_submit_page_unknown_session_prints_verdict_and_fails(tmp_path):
    sub = tmp_path / "page.json"
    sub.write_text("[]", encoding="utf-8")
    result = runner.invoke(
        app,
        ["ingest-session", "submit-page", "ing-missing", "1",
         "--file", str(sub), "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 1, result.output
    verdict = json.loads(result.output)
    assert verdict["accepted"] is False
    assert "unknown session" in verdict["errors"][0]["message"]


def test_begin_missing_pdf_exits_nonzero(tmp_path):
    result = runner.invoke(
        app,
        ["ingest-session", "begin", str(tmp_path / "missing.pdf"), "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "PDF not found" in result.output


def test_abort_unknown_session_exits_nonzero(tmp_path):
    result = runner.invoke(
        app, ["ingest-session", "abort", "ing-missing", "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["aborted"] is False
