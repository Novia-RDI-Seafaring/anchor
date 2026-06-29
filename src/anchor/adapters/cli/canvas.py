"""``anchor canvas`` subcommands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_real_services
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs

canvas_app = typer.Typer(help="Manage workspaces (canvases).")

reference_app = typer.Typer(help="Manage a canvas's references (bibliography).")
canvas_app.add_typer(reference_app, name="reference")


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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
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


def _parse_data(raw: str | None) -> dict:
    if raw is None or raw == "":
        return {}
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"--data is not valid JSON: {e}", err=True)
        raise typer.Exit(code=2) from e
    if not isinstance(out, dict):
        typer.echo("--data must be a JSON object", err=True)
        raise typer.Exit(code=2)
    return out


@canvas_app.command("state")
def canvas_state(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the full workspace state (nodes + edges + metadata)."""
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    if parent is not None and parent == node_id:
        typer.echo("node cannot be its own parent", err=True)
        raise typer.Exit(code=2)
    _, _, ws, _, doc_store = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)

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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)

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
    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, env = await ws.clear(slug)
        return {"event": env.model_dump(), "state": state.get_state()}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("organize")
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
    and the `canvas_organize_subtree` MCP tool — the adapter parity rule
    means the move list you get here is byte-equal to what the UI would
    produce for the same canvas.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

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


@canvas_app.command("align")
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
    MCP tool — the parity rule means the move list a UI would emit for
    this selection is byte-equal to what we print here.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

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


@canvas_app.command("distribute")
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
    _, _, ws, _, _ = _build_real_services(data_dir)

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


@canvas_app.command("create-sub")
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
    MCP tool — adapter parity rule.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

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


# ── References (canvas bibliography, #147 slice 1) ───────────────────────────
#
# `anchor canvas reference create|list|attach` — thin wrappers around the same
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

    _, _, ws, _, _ = _build_real_services(data_dir)
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
    _, _, ws, _, _ = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(ws.list_references(slug)), indent=2))


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

    _, _, ws, _, _ = _build_real_services(data_dir)

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


@canvas_app.command("snapshot")
def canvas_snapshot(
    slug: str,
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Where to write the snapshot. Default: data_dir/snapshots/<slug>/<ts>.png.",
    ),
    image_format: str = typer.Option("png", "--format", "-f", help="png (default) or svg."),
    viewport: str | None = typer.Option(
        None, "--viewport", help="WxH in CSS pixels, e.g. '1920x1080'."
    ),
    full_page: bool = typer.Option(
        True,
        "--full-page/--viewport-only",
        help="Capture the whole document (default) or just the viewport.",
    ),
    base_url: str = typer.Option(
        "http://localhost:8002", "--base-url", help="URL of a running `anchor serve`."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Render the named workspace canvas to an image.

    Requires a running `anchor serve` reachable at --base-url. The headless
    chromium navigates to {base_url}/c/{slug} so the same React Flow code
    the user sees in the browser does the rendering.
    """
    vp: tuple[int, int] | None = None
    if viewport is not None:
        try:
            w, h = viewport.lower().split("x")
            vp = (int(w), int(h))
        except (ValueError, IndexError) as e:
            typer.echo(f"--viewport: expected WxH (e.g. 1920x1080), got {viewport!r}", err=True)
            raise typer.Exit(code=2) from e

    _, _, ws, _, _ = _build_real_services(data_dir, base_url=base_url)

    async def run():
        return await ws.snapshot(slug, format=image_format, viewport=vp, full_page=full_page)

    try:
        result = asyncio.run(run())
    except NotImplementedError as e:
        typer.echo(f"snapshot failed: {e}", err=True)
        raise typer.Exit(code=2) from e
    except RuntimeError as e:
        typer.echo(f"snapshot failed: {e}", err=True)
        typer.echo(
            "Hint: ensure `anchor serve --port <p>` is running and pass --base-url http://localhost:<p>.",
            err=True,
        )
        raise typer.Exit(code=1) from e
    except ValueError as e:
        typer.echo(f"snapshot failed: {e}", err=True)
        raise typer.Exit(code=2) from e

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        if result.path is not None:
            out.write_bytes(result.path.read_bytes())
        else:
            assert result.bytes_ is not None
            out.write_bytes(result.bytes_)
        typer.echo(str(out))
        return

    # No --out: print the snapshotter's own path (the timeline file under
    # data_dir/snapshots/<slug>/<ts>.png). For inline-bytes snapshotters
    # there's nothing to print — write a tmp file and surface it.
    if result.path is not None:
        typer.echo(str(result.path))
    else:
        import tempfile

        ext = f".{result.format}"
        tmp = Path(tempfile.NamedTemporaryFile(suffix=ext, delete=False).name)
        assert result.bytes_ is not None
        tmp.write_bytes(result.bytes_)
        typer.echo(str(tmp))
