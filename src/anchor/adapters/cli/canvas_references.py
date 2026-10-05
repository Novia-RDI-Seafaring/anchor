"""Bibliography commands for ``anchor canvas reference``."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.canvas_data import parse_data as _parse_data
from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_canvas_runtime

reference_app = typer.Typer(help="Manage a canvas's references (bibliography).")

# -- References (canvas bibliography, #147 slice 1) ---------------------------
#
# `anchor canvas reference create|list|attach` - thin wrappers around the same
# WorkspaceService methods the HTTP routes and MCP tools call (adapter parity).


@reference_app.command("create")
def reference_create(
    slug: str,
    source_ref: str = typer.Option(
        ...,
        "--source-ref",
        "-s",
        help='JSON locator: {"slug": "doc", "page": 3, "bbox?": [..], "region_id?": "..", "detail?": {..}}. slug + page required.',
    ),
    label: str | None = typer.Option(None, "--label", "-l", help="Human caption."),
    created_by: str = typer.Option(
        "human", "--created-by", help="'human' (default) or 'agent'."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Author a reference and add it to the canvas bibliography.

    Prints the stored reference (with its server-assigned id). Same backend as
    the `POST /references` HTTP route and the `canvas_create_reference` MCP tool.
    """
    from anchor.core.workspace.workspace import CommandError as _CmdErr

    ws = _build_canvas_runtime(data_dir).workspace
    parsed = _parse_data(source_ref)

    async def run():
        return await ws.create_reference(
            slug, source_ref=parsed, label=label, created_by=created_by,
        )

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"create reference failed: {e}", err=True)
        raise typer.Exit(code=2) from e


@reference_app.command("list")
def reference_list(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List the canvas bibliography.

    Same envelope as `GET /references` and the `canvas_list_references` MCP tool.
    """
    ws = _build_canvas_runtime(data_dir).workspace
    typer.echo(json.dumps(asyncio.run(ws.list_references(slug)), indent=2))


@reference_app.command("remove")
def reference_remove(
    slug: str,
    reference_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Remove a reference from the canvas bibliography.

    Same backend as the `DELETE /references/{id}` HTTP route and the
    `canvas_remove_reference` MCP tool.
    """
    from anchor.core.workspace.workspace import CommandError as _CmdErr

    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, env = await ws.remove_reference(slug, reference_id)
        return {"event": env.model_dump(), "state": state.get_state()}

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"remove reference failed: {e}", err=True)
        raise typer.Exit(code=2) from e


@reference_app.command("update")
def reference_update(
    slug: str,
    reference_id: str,
    label: str | None = typer.Option(
        None, "--label", "-l", help="New human caption (omit to clear)."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Edit a reference's human caption (label).

    Only the label is editable; the source_ref locator is immutable. Same
    backend as the `PATCH /references/{id}` HTTP route and the
    `canvas_update_reference` MCP tool.
    """
    from anchor.core.workspace.workspace import CommandError as _CmdErr

    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, env = await ws.update_reference(slug, reference_id, label=label)
        return {"event": env.model_dump(), "state": state.get_state()}

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"update reference failed: {e}", err=True)
        raise typer.Exit(code=2) from e


@reference_app.command("attach")
def reference_attach(
    slug: str,
    reference_id: str,
    node_id: str = typer.Option(..., "--node", "-n", help="Target node id."),
    row_index: int | None = typer.Option(
        None, "--row", "-r", help="Optional: target one spec row by index."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Attach a stored reference to a node (and optionally a spec row).

    Same backend as the `POST /references/{id}/attach` HTTP route and the
    `canvas_attach_reference` MCP tool.
    """
    from anchor.core.workspace.workspace import CommandError as _CmdErr

    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, env = await ws.attach_reference(
            slug, reference_id, node_id=node_id, row_index=row_index,
        )
        return {"event": env.model_dump(), "state": state.get_state()}

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"attach reference failed: {e}", err=True)
        raise typer.Exit(code=2) from e
