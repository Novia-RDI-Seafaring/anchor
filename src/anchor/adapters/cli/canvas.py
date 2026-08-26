"""``anchor canvas`` subcommands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.canvas_data import parse_data as _parse_data
from anchor.adapters.cli.canvas_layout import register_layout_commands
from anchor.adapters.cli.canvas_references import reference_app
from anchor.adapters.cli.canvas_snapshot import register_snapshot_command
from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_canvas_runtime
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs

canvas_app = typer.Typer(help="Manage workspaces (canvases).")


def _canvas_url(slug: str, data_dir: Path | None = None) -> str:
    """The web URL a canvas is viewed at: ``http://<host>:<port>/c/<slug>``.

    When a ``data_dir`` is given and a running ``anchor serve`` is actually
    bound to it, use that server's real host:port -- so a serve that bumped to
    a free port (or a non-default project) yields a URL that resolves to *this*
    project, not a guessed ``:8002`` pointing at someone else's server
    (anchor#177). Falls back to the configured host/port when no serve for this
    data dir is up.
    """
    from anchor.infra.config import AnchorConfig

    if data_dir is not None:
        from anchor.infra.serve_registry import find_serve_for_data_dir

        record = find_serve_for_data_dir(data_dir)
        if record is not None:
            return f"{record.base_url()}/c/{slug}"

    cfg = AnchorConfig()
    host = cfg.http_host if cfg.http_host not in ("0.0.0.0", "::") else "127.0.0.1"
    return f"http://{host}:{cfg.http_port}/c/{slug}"


@canvas_app.command("list")
def canvas_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="'text' for one-per-line summary, 'json' for the full envelope.",
    ),
) -> None:
    """List all workspaces with counts + reference edges.

    ``--format text`` (default) prints one canvas per line as
    ``slug - N nodes / M edges / refs N / refd-by M``. ``--format json``
    prints the full envelope including the ``references`` /
    ``referenced_by`` slug lists; this is the same shape returned by the HTTP
    ``GET /api/workspaces`` and the ``canvas_list_workspaces`` MCP tool.
    """
    ws = _build_canvas_runtime(data_dir).workspace
    items = asyncio.run(ws.list_workspaces())
    if format == "json":
        typer.echo(json.dumps(items, indent=2))
        return
    if format != "text":
        typer.echo(f"unknown --format {format!r} (use 'text' or 'json')", err=True)
        raise typer.Exit(code=2)
    if not items:
        typer.echo("(no canvases)")
        return
    for it in items:
        typer.echo(
            f"{it['slug']} - {it['node_count']} nodes / "
            f"{it['edge_count']} edges / refs {len(it['references'])} / "
            f"refd-by {len(it['referenced_by'])}",
        )


@canvas_app.command("placeholders")
def canvas_placeholders(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    format: str = typer.Option(
        "text",
        "--format",
        "-f",
        help="'text' (one per line) or 'json' (the full list).",
    ),
) -> None:
    """List the workspace's placeholder nodes (``data.placeholder == true``).

    Mirrors the ``canvas_list_placeholders`` MCP tool + the HTTP
    ``GET /api/workspaces/{slug}/placeholders`` route. Each entry carries
    ``{id, node_type, label, hint, x, y, data}``; the ``hint`` is the
    optional ``data.placeholder_hint`` so callers can spot which one is
    the "Max inlet pressure" slot at a glance.
    """
    ws = _build_canvas_runtime(data_dir).workspace
    items = asyncio.run(ws.list_placeholders(slug))
    if format == "json":
        typer.echo(json.dumps(items, indent=2))
        return
    if format != "text":
        typer.echo(f"unknown --format {format!r} (use 'text' or 'json')", err=True)
        raise typer.Exit(code=2)
    if not items:
        typer.echo("(no placeholders)")
        return
    for it in items:
        hint = f" / {it['hint']}" if it.get("hint") else ""
        typer.echo(f"{it['id']}  [{it['node_type']}] {it['label']!r}{hint}")


@canvas_app.command("create")
def canvas_create(
    slug: str,
    title: str = typer.Option("", "--title"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Create a new workspace folder."""
    ws = _build_canvas_runtime(data_dir).workspace
    typer.echo(json.dumps(asyncio.run(ws.create_workspace(slug, title=title)), indent=2))
    # Tell the user where to view it (stderr keeps stdout pure JSON for agents).
    typer.echo(
        f"View this canvas at {_canvas_url(slug, data_dir)}  (run `anchor serve`)", err=True
    )


@canvas_app.command("url")
def canvas_url(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the web URL for a canvas (``http://<host>:<port>/c/<slug>``).

    Resolves the URL against a running ``anchor serve`` actually bound to this
    project's data dir, so the printed port is the real one (not a guessed
    ``:8002``). When no serve for this project is up, prints the default-target
    URL and warns on stderr that nothing is serving it yet.
    """
    from anchor.infra.serve_registry import find_serve_for_data_dir

    record = find_serve_for_data_dir(data_dir)
    if record is None:
        typer.echo(
            "Warning: no `anchor serve` is bound to this project's data dir "
            f"({data_dir}); the URL below uses the default target and may not "
            "resolve. Start one with `anchor serve` or check `anchor serve-info`.",
            err=True,
        )
    typer.echo(_canvas_url(slug, data_dir))


@canvas_app.command("delete")
def canvas_delete(
    slug: str,
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Confirm deletion of the workspace folder.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Delete a workspace folder and its saved canvas state."""
    if not yes:
        typer.echo("Refusing to delete without --yes; pass -y to confirm.", err=True)
        raise typer.Exit(code=2)
    ws = _build_canvas_runtime(data_dir).workspace
    try:
        typer.echo(json.dumps(asyncio.run(ws.delete_workspace(slug)), indent=2))
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e


# ── Canvas mutations ────────────────────────────────────────────────────────
#
# Every command below is a thin wrapper around the same `WorkspaceService`
# method that the HTTP router and MCP handler call. The work happens in
# CORE; this file only translates flags into kwargs. Keeping all three
# adapters in lockstep is the architecture's standing rule
# (see `docs/concepts/interfaces.md`).
#
# `--data` accepts a JSON string. Shells are awkward at JSON quoting; for
# multi-field nodes use a here-doc or pipe through a file:
#   anchor canvas add-node my-canvas concept Foo --x 0 --y 0 \
#     --data "$(cat <<'JSON'
#   {"subtitle": "hello", "metadata": {"tag": "demo"}}
#   JSON
#   )"


def _validate_layer(layer: str | None) -> str | None:
    if layer is None:
        return None
    if layer not in {"background", "content", "annotation"}:
        typer.echo("--layer must be background, content, or annotation", err=True)
        raise typer.Exit(code=2)
    return layer


@canvas_app.command("state")
def canvas_state(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the full workspace state (nodes + edges + metadata)."""
    ws = _build_canvas_runtime(data_dir).workspace
    typer.echo(json.dumps(asyncio.run(ws.get_state(slug)), indent=2))


@canvas_app.command("add-node")
def canvas_add_node(
    slug: str,
    node_type: str,
    label: str = typer.Option("", "--label", "-l"),
    x: float | None = typer.Option(
        None, "--x", help="X position. Omit (with --y) to auto-place a non-overlapping spot."
    ),
    y: float | None = typer.Option(
        None, "--y", help="Y position. Omit (with --x) to auto-place a non-overlapping spot."
    ),
    place: str | None = typer.Option(
        None,
        "--place",
        help="'auto' forces server-side non-overlapping placement even if --x/--y are given; 'exact' forces the given coordinates.",
    ),
    width: float | None = typer.Option(None, "--width"),
    height: float | None = typer.Option(None, "--height"),
    parent: str | None = typer.Option(None, "--parent"),
    locked: bool = typer.Option(False, "--locked"),
    hidden: bool = typer.Option(False, "--hidden"),
    layer: str | None = typer.Option(None, "--layer"),
    opacity: float | None = typer.Option(None, "--opacity"),
    data: str | None = typer.Option(
        None, "--data", help="JSON object passed as the node's `data` field"
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Add a node to a workspace. Prints the resulting `{event, state, position}`.

    Omit --x/--y (or pass --place auto) and the server assigns a
    non-overlapping position, echoed back under `position` so you can track
    the layout (#189). Unknown `data` keys for a known node_type surface a
    non-blocking `warning` (run `anchor canvas node-types` for the contract).
    """
    ws = _build_canvas_runtime(data_dir).workspace
    parsed = _parse_data(data)
    kwargs: dict = {
        "node_type": node_type,
        "label": label,
        "data": parsed,
    }
    if x is not None:
        kwargs["x"] = x
    if y is not None:
        kwargs["y"] = y
    if width is not None:
        kwargs["width"] = width
    if height is not None:
        kwargs["height"] = height
    if parent is not None:
        kwargs["parent"] = parent
    if locked:
        kwargs["locked"] = True
    if hidden:
        kwargs["visible"] = False
    layer = _validate_layer(layer)
    if layer is not None:
        kwargs["layer"] = layer
    if opacity is not None:
        kwargs["opacity"] = opacity

    async def run():
        state, env = await ws.add_node(slug, place=place, **kwargs)
        out: dict = {
            "event": env.model_dump(),
            "state": state.get_state(),
            "position": {"x": env.payload.get("x"), "y": env.payload.get("y")},
        }
        unknown = ws.unknown_data_keys(node_type, parsed)
        if unknown:
            out["warning"] = (
                f"node_type {node_type!r} does not render these data keys: "
                f"{', '.join(unknown)}. Run `anchor canvas node-types {node_type}`."
            )
        return out

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("node-types")
def canvas_node_types(
    node_type: str | None = typer.Argument(
        None, help="Narrow to one node type; omit for all."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the per-node-type data-field contract (#191).

    Shows which `data` keys each built-in node type renders and which key is
    its visible body. Same envelope as the `canvas_node_types` MCP tool and
    the `GET /api/node-types` HTTP route (adapter parity).
    """
    ws = _build_canvas_runtime(data_dir).workspace
    schema = ws.node_types_schema(node_type)
    if node_type is not None and not schema:
        typer.echo(f"unknown node_type {node_type!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(schema, indent=2))


@canvas_app.command("update-node")
def canvas_update_node(
    slug: str,
    node_id: str,
    label: str | None = typer.Option(None, "--label", "-l"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    width: float | None = typer.Option(None, "--width"),
    height: float | None = typer.Option(None, "--height"),
    lock: bool = typer.Option(False, "--locked"),
    unlock: bool = typer.Option(False, "--unlocked"),
    visible: bool = typer.Option(False, "--visible"),
    hidden: bool = typer.Option(False, "--hidden"),
    layer: str | None = typer.Option(None, "--layer"),
    opacity: float | None = typer.Option(None, "--opacity"),
    parent: str | None = typer.Option(
        None,
        "--parent",
        help=(
            "Reparent the node onto another node (typically an Area "
            "container's id). Triggers a `NodeReparented` event."
        ),
    ),
    unparent: bool = typer.Option(
        False,
        "--unparent",
        help=("Detach the node from its current parent. Mutually exclusive with --parent."),
    ),
    data: str | None = typer.Option(
        None,
        "--data",
        help=(
            "JSON object deep-MERGED into the node's existing data: "
            "unmentioned keys (e.g. source_ref) are kept; a key set to null "
            "is deleted. Patch one field without read-modify-write."
        ),
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Update fields on an existing node. Move-only when only --x and --y given.

    `--data` deep-merges into existing data (it no longer replaces the whole
    dict): unmentioned keys survive, nested dicts merge, a null value deletes
    a key (#192).
    """
    if parent is not None and unparent:
        typer.echo("--parent and --unparent are mutually exclusive", err=True)
        raise typer.Exit(code=2)
    if lock and unlock:
        typer.echo("--locked and --unlocked are mutually exclusive", err=True)
        raise typer.Exit(code=2)
    if visible and hidden:
        typer.echo("--visible and --hidden are mutually exclusive", err=True)
        raise typer.Exit(code=2)
    if parent is not None and parent == node_id:
        typer.echo("node cannot be its own parent", err=True)
        raise typer.Exit(code=2)
    runtime = _build_canvas_runtime(data_dir)
    ws = runtime.workspace
    doc_store = runtime.doc_store
    fields: dict = {}
    if label is not None:
        fields["label"] = label
    if x is not None:
        fields["x"] = x
    if y is not None:
        fields["y"] = y
    if width is not None:
        fields["width"] = width
    if height is not None:
        fields["height"] = height
    if lock:
        fields["locked"] = True
    if unlock:
        fields["locked"] = False
    if visible:
        fields["visible"] = True
    if hidden:
        fields["visible"] = False
    layer = _validate_layer(layer)
    if layer is not None:
        fields["layer"] = layer
    if opacity is not None:
        fields["opacity"] = opacity
    if data is not None:
        fields["data"] = _parse_data(data)
    parent_op = parent is not None or unparent
    parent_val = parent if parent is not None else (None if unparent else None)
    if not fields and not parent_op:
        typer.echo("nothing to update - pass at least one field", err=True)
        raise typer.Exit(code=2)

    async def run():
        # Same dispatch rules as the HTTP PATCH route; keeps HTTP / MCP /
        # CLI behaviour identical (per the v2 adapter-parity rule).
        env = None
        state = None
        if set(fields.keys()) == {"x", "y"} and not parent_op:
            state, env = await ws.move_node(slug, node_id, fields["x"], fields["y"])
        elif parent_op and not fields:
            state, env = await ws.reparent_node(slug, node_id, parent_val)
        else:
            if fields:
                if "data" in fields:
                    fields["data"] = await enrich_spec_row_source_refs(fields["data"], doc_store)
                state, env = await ws.update_node(slug, node_id, fields)
            if parent_op:
                state, env = await ws.reparent_node(slug, node_id, parent_val)
        assert env is not None and state is not None  # for type narrowing
        out: dict = {"event": env.model_dump(), "state": state.get_state()}
        if data is not None:
            node = state.nodes.get(node_id)
            unknown = (
                ws.unknown_data_keys(node.node_type, fields.get("data"))
                if node is not None else []
            )
            if unknown:
                out["warning"] = (
                    f"node_type {node.node_type!r} does not render these data "
                    f"keys: {', '.join(unknown)}. Run `anchor canvas node-types "
                    f"{node.node_type}`."
                )
        return out

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("remove-node")
def canvas_remove_node(
    slug: str,
    node_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Remove a node and any edges that touched it (cascade is in CORE)."""
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, envelopes = await ws.remove_node(slug, node_id)
        return {"events": [e.model_dump() for e in envelopes], "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("add-edge")
def canvas_add_edge(
    slug: str,
    source: str,
    target: str,
    edge_type: str = typer.Option("floating", "--type", "-t", help="`floating` or `anchored`"),
    label: str = typer.Option("", "--label", "-l"),
    source_handle: str | None = typer.Option(None, "--source-handle"),
    target_handle: str | None = typer.Option(None, "--target-handle"),
    data: str | None = typer.Option(None, "--data"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Add an edge between two nodes."""
    ws = _build_canvas_runtime(data_dir).workspace
    payload = _parse_data(data)
    kwargs: dict = {
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "label": label,
        "data": payload,
    }
    if source_handle:
        kwargs["source_handle"] = source_handle
    if target_handle:
        kwargs["target_handle"] = target_handle

    async def run():
        state, env = await ws.add_edge(slug, **kwargs)
        return {"event": env.model_dump(), "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("remove-edge")
def canvas_remove_edge(
    slug: str,
    edge_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Remove a single edge by id."""
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, env = await ws.remove_edge(slug, edge_id)
        return {"event": env.model_dump(), "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("update-edge")
def canvas_update_edge(
    slug: str,
    edge_id: str,
    label: str | None = typer.Option(None, "--label", "-l"),
    edge_type: str | None = typer.Option(None, "--type", "-t", help="`floating` or `anchored`"),
    source_handle: str | None = typer.Option(None, "--source-handle"),
    target_handle: str | None = typer.Option(None, "--target-handle"),
    data: str | None = typer.Option(
        None, "--data", help="JSON object deep-MERGED into the edge's `data` field (null deletes a key)"
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Patch an edge's fields (label, type, handles, data). `--data` deep-merges (#192)."""
    ws = _build_canvas_runtime(data_dir).workspace
    fields: dict = {}
    if label is not None:
        fields["label"] = label
    if edge_type is not None:
        fields["edge_type"] = edge_type
    if source_handle is not None:
        fields["sourceHandle"] = source_handle
    if target_handle is not None:
        fields["targetHandle"] = target_handle
    if data is not None:
        fields["data"] = _parse_data(data)
    if not fields:
        typer.echo(
            "nothing to update - pass at least one of --label / --type / --source-handle / --target-handle / --data",
            err=True,
        )
        raise typer.Exit(code=1)

    async def run():
        state, env = await ws.update_edge(slug, edge_id, fields)
        return {"event": env.model_dump(), "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("clear")
def canvas_clear(
    slug: str,
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Confirm - clear removes EVERY node and edge on the workspace."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Remove every node and edge from a workspace (workspace itself stays)."""
    if not yes:
        typer.echo("Refusing to clear without --yes; pass -y to confirm.", err=True)
        raise typer.Exit(code=2)
    ws = _build_canvas_runtime(data_dir).workspace

    async def run():
        state, env = await ws.clear(slug)
        return {"event": env.model_dump(), "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))

register_layout_commands(canvas_app)
canvas_app.add_typer(reference_app, name="reference")
register_snapshot_command(canvas_app)
