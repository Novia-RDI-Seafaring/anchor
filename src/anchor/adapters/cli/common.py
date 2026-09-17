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


def read_json_arg(value: str) -> str:
    """Return the raw JSON text for a CLI value, dereferencing ``@path``.

    A value starting with ``@`` names a local file whose contents stand in
    for the inline JSON (``--data @node.json`` reads ``node.json``); any
    other value is returned unchanged. The file is the user's own shell
    argument pointing at their own file — same trust as a shell redirect —
    so an unreadable path is a plain usage error (exit 2), not a traceback.
    """
    if not value.startswith("@"):
        return value
    path = Path(value[1:])
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        typer.echo(f"cannot read {str(path)!r}: {exc}", err=True)
        raise typer.Exit(code=2) from None


def resolve_serve_base_url(data_dir: Path) -> tuple[str, bool]:
    """Base URL of the ``anchor serve`` actually bound to ``data_dir``.

    Returns ``(base_url, found)``. When a running serve is registered for this
    project's data dir, its real ``http://host:port`` wins — so a serve that
    bumped to a free port (or a non-default project on :8003) is reached, not a
    guessed ``:8002`` pointing at someone else's server (anchor#177, #306).
    ``found`` is False when no serve is bound to the dir; the fallback is then
    the configured host/port, which may not resolve — callers should say so.
    """
    from anchor.infra.serve_registry import find_serve_for_data_dir

    record = find_serve_for_data_dir(data_dir)
    if record is not None:
        return record.base_url(), True

    from anchor.infra.config import AnchorConfig

    cfg = AnchorConfig()
    host = cfg.http_host if cfg.http_host not in ("0.0.0.0", "::") else "127.0.0.1"
    return f"http://{host}:{cfg.http_port}", False


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
