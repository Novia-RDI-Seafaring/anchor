"""Shared helpers for the ``anchor`` Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from anchor.infra.config import AnchorConfig


def default_data_dir() -> Path:
    """Resolve the default storage root, including ``ANCHOR_DATA_DIR``."""
    return AnchorConfig().data_dir


# Typer evaluates option defaults while importing the CLI. Resolve through
# AnchorConfig so every CLI subcommand honors ANCHOR_DATA_DIR unless the user
# passes an explicit --data-dir.
DEFAULT_DATA_DIR = default_data_dir()


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
