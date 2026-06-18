"""Shared helpers for the ``anchor`` Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer


def default_data_dir() -> Path:
    """Resolve the default storage root: the active project under its environment.

    Storage comes from the environment (the config), not an ``ANCHOR_DATA_DIR``.
    Honors the selectors — ``ANCHOR_ENV`` / ``ANCHOR_PROJECT`` and the
    ``anchor use`` session selection — and falls back to the default environment
    and its ``default`` project. Pass an explicit ``--data-dir`` to point a
    single command somewhere else.
    """
    from anchor.infra.environment import resolve_project

    return resolve_project().data_dir


# Typer evaluates option defaults while importing the CLI. Resolve through the
# environment so every CLI subcommand lands on the active environment's default
# project unless the user passes an explicit --data-dir.
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
