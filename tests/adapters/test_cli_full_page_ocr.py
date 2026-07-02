"""CLI smoke: `anchor ingest --full-page-ocr` is exposed (issue #231)."""
from __future__ import annotations

from typer.testing import CliRunner

from anchor.adapters.cli.main import app

runner = CliRunner()


def test_ingest_help_shows_full_page_ocr():
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--full-page-ocr" in result.output
