"""Layout and sub-canvas commands for ``anchor canvas``."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_canvas_runtime


def canvas_organize(
    slug: str,
    root_id: str,
    orientation: str = typer.Option(
        "vertical",
        "--orientation",
        "-o",
        help="`vertical` (default) or `horizontal`.",
    ),
    algo: str = typer.Option(
        "dagre",
        "--algo",
        "-a",
        help="Layout algorithm. Only `dagre` ships today.",
    ),
    direction: str = typer.Option(
        "any",
        "--direction",
        help=(
            "Edge-walk policy. `outgoing` (parent->child arrows), `incoming` "
            "(reports-to: subordinate->boss arrows), or `any` (undirected, "
            "the default - v1 behaviour). Pick `incoming` on a reports-to "
            "chart to scope strictly to subordinates of <root_id>."
        ),
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Re-lay-out the subtree under <root_id> into a tidy tree.

    Emits one NodeMoved per descendant whose position changes; the root
    itself stays put. Same backend code as the HTTP `POST /layout` route
    and the `canvas_organize_subtree` MCP tool - the adapter parity rule
    means the move list you get here is byte-equal to what the UI would
    produce for the same canvas.
    """
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, envelopes = await ws.organize_subtree(
            slug,
            root_id,
            orientation=orientation,
            algo=algo,
            direction=direction,
        )
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves,
            "event_count": len(envelopes),
            "state": state.get_state(),
        }

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except ValueError as e:
        typer.echo(f"organize failed: {e}", err=True)
        raise typer.Exit(code=2) from e


def canvas_align(
    slug: str,
    node_ids: list[str] = typer.Argument(..., help="Node ids to align (at least 2)."),
    anchor: str = typer.Option(
        "top",
        "--anchor",
        "-a",
        help="`top` | `bottom` | `left` | `right` | `center-h` | `center-v`.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Align the listed nodes to a shared edge or midline.

    Same backend as the HTTP `POST /align` route and the `canvas_align`
    MCP tool - the parity rule means the move list a UI would emit for
    this selection is byte-equal to what we print here.
    """
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, envelopes = await ws.align_nodes(slug, list(node_ids), anchor)  # type: ignore[arg-type]
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves,
            "event_count": len(envelopes),
            "state": state.get_state(),
        }

    from anchor.core.workspace.workspace import CommandError as _CmdErr

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"align failed: {e}", err=True)
        raise typer.Exit(code=2) from e
    except ValueError as e:
        typer.echo(f"align failed: {e}", err=True)
        raise typer.Exit(code=2) from e


def canvas_distribute(
    slug: str,
    node_ids: list[str] = typer.Argument(..., help="Node ids to distribute (at least 3)."),
    axis: str = typer.Option(
        "horizontal",
        "--axis",
        "-x",
        help="`horizontal` (default) or `vertical`.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Distribute the listed nodes' centres evenly along an axis.

    Endpoints stay put; intermediate nodes get equally-spaced centres.
    Same backend as the HTTP `POST /distribute` route and the
    `canvas_distribute` MCP tool.
    """
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, envelopes = await ws.distribute_nodes(slug, list(node_ids), axis)  # type: ignore[arg-type]
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves,
            "event_count": len(envelopes),
            "state": state.get_state(),
        }

    from anchor.core.workspace.workspace import CommandError as _CmdErr

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"distribute failed: {e}", err=True)
        raise typer.Exit(code=2) from e
    except ValueError as e:
        typer.echo(f"distribute failed: {e}", err=True)
        raise typer.Exit(code=2) from e


def canvas_create_sub(
    parent_slug: str,
    sub_slug: str,
    title: str = typer.Option("", "--title", "-t"),
    x: float = typer.Option(0.0, "--x"),
    y: float = typer.Option(0.0, "--y"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Create a child canvas <sub_slug> and link it from <parent_slug>.

    Composite of `canvas create` + a `node_type=canvas` linking node so
    the child workspace and the breadcrumb-able link land in one go.
    Same WorkspaceService.create_sub_canvas backing as the
    `POST /sub-canvas` HTTP route and the `canvas_create_sub_canvas`
    MCP tool - adapter parity rule.
    """
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        return await ws.create_sub_canvas(
            parent_slug,
            sub_slug,
            title=title,
            x=x,
            y=y,
        )

    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except Exception as e:  # noqa: BLE001
        typer.echo(f"create-sub failed: {e}", err=True)
        raise typer.Exit(code=2) from e

def register_layout_commands(app: typer.Typer) -> None:
    """Register layout commands on the existing canvas command group."""
    app.command("organize")(canvas_organize)
    app.command("align")(canvas_align)
    app.command("distribute")(canvas_distribute)
    app.command("create-sub")(canvas_create_sub)
