"""Shared JSON parsing for canvas CLI payloads."""

from __future__ import annotations

import json

import typer

from anchor.adapters.cli.common import read_json_arg


def parse_data(raw: str | None) -> dict:
    """Parse a ``--data`` value: inline JSON or ``@path`` to a JSON file (#288)."""
    if raw is None or raw == "":
        return {}
    raw = read_json_arg(raw)
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"--data is not valid JSON: {e}", err=True)
        raise typer.Exit(code=2) from e
    if not isinstance(out, dict):
        typer.echo("--data must be a JSON object", err=True)
        raise typer.Exit(code=2)
    return out
