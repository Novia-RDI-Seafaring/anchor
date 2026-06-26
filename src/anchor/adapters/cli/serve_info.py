"""``anchor serve-info`` -- which project does a running serve host?

In a multi-project setup an agent could not tell which ``anchor serve`` (port)
is bound to which project, so a ``localhost:8002`` URL was a guess that could
point at the wrong corpus (anchor#177, anchor#179). This command lists every
running serve and the env + project + data dir + actual host:port it is bound
to, reading the runtime records each serve writes under ``~/.anchor/serves/``.
With ``--project`` / ``--data-dir`` it prints just the matching serve's base
URL, which is the discovery primitive ``canvas url`` now uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer


def serve_info(
    data_dir: Path = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Show only the serve bound to this project data dir (prints its base URL).",
    ),
    project: str = typer.Option(
        None, "--project", help="Show only the serve bound to this project (by name)."
    ),
    env: str = typer.Option(
        None, "--env", help="Restrict --project lookup to this environment."
    ),
    format: str = typer.Option(
        "text", "--format", "-f", help="'text' (one per line) or 'json'."
    ),
) -> None:
    """List running ``anchor serve`` processes and the project each is bound to.

    Stale records (a serve that crashed without cleanup) are pruned on read, so
    every line is a server you can actually reach.
    """
    from anchor.infra.serve_registry import find_serve_for_data_dir, list_serves

    # Resolve a --project name to its data dir so we can match a serve to it.
    if project is not None and data_dir is None:
        from anchor.infra.environment import resolve_project

        try:
            data_dir = resolve_project(env, project).data_dir
        except Exception as exc:  # noqa: BLE001 -- surface a clean message
            typer.echo(f"serve-info: could not resolve project {project!r}: {exc}", err=True)
            raise typer.Exit(code=2) from exc

    if data_dir is not None:
        record = find_serve_for_data_dir(data_dir)
        if record is None:
            typer.echo(
                f"No running serve is bound to {data_dir}. "
                "Start one with `anchor serve`.",
                err=True,
            )
            raise typer.Exit(code=1)
        if format == "json":
            typer.echo(json.dumps(record.to_dict(), indent=2))
        else:
            typer.echo(record.base_url())
        return

    serves = list_serves()
    if format == "json":
        typer.echo(json.dumps([r.to_dict() for r in serves], indent=2))
        return
    if format != "text":
        typer.echo(f"unknown --format {format!r} (use 'text' or 'json')", err=True)
        raise typer.Exit(code=2)
    if not serves:
        typer.echo("(no running anchor serve found)")
        return
    for r in serves:
        env_name = r.env or "?"
        proj = r.project or "?"
        typer.echo(
            f"{r.base_url()}  env={env_name} project={proj} "
            f"data_dir={r.data_dir} pid={r.pid}"
        )
