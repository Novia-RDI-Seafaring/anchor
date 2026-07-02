"""CLI smoke: `anchor ingest --full-page-ocr` is exposed (issue #231).

Introspect the registered command's options rather than scraping rendered
`--help` text: under CI, Typer/rich styles and line-wraps the help table, so a
literal substring check for the flag is brittle (the flag can be split or padded
by ANSI formatting). Checking the Click option registration is deterministic.
"""
from __future__ import annotations

import typer

from anchor.adapters.cli.main import app


def test_ingest_exposes_full_page_ocr_option():
    ingest = typer.main.get_command(app).commands["ingest"]
    option_flags = {flag for param in ingest.params for flag in getattr(param, "opts", [])}
    assert "--full-page-ocr" in option_flags
