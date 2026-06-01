"""Shared helpers for the ``anchor`` Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer

# Canonical data dir. ``~/anchor-data`` keeps fresh ``anchor serve`` and
# ``anchor ingest`` invocations aligned. Override with ``--data-dir``.
DEFAULT_DATA_DIR = Path.home() / "anchor-data"


def _emit_bytes(path: Path | None, *, copy_to: Path | None, out: str | None, label: str) -> None:
    if path is None:
        typer.echo(f"{label}: not found", err=True)
        raise typer.Exit(code=1)
    if str(path).startswith("memory://"):
        typer.echo(f"{label}: in-memory store has no real path", err=True)
        raise typer.Exit(code=1)
    if out == "-":
        # Binary safe: write raw bytes through the underlying stdout buffer.
        import sys

        sys.stdout.buffer.write(path.read_bytes())
        return
    if copy_to is not None:
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        copy_to.write_bytes(path.read_bytes())
        typer.echo(str(copy_to))
        return
    typer.echo(str(path))
