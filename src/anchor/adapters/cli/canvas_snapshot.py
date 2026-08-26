"""Snapshot command for ``anchor canvas``."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_canvas_runtime


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

    ws = _build_canvas_runtime(data_dir, base_url=base_url).workspace

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
    # there's nothing to print - write a tmp file and surface it.
    if result.path is not None:
        typer.echo(str(result.path))
    else:
        import tempfile

        ext = f".{result.format}"
        tmp = Path(tempfile.NamedTemporaryFile(suffix=ext, delete=False).name)
        assert result.bytes_ is not None
        tmp.write_bytes(result.bytes_)
        typer.echo(str(tmp))

def register_snapshot_command(app: typer.Typer) -> None:
    """Register snapshot capture on the existing canvas command group."""
    app.command("snapshot")(canvas_snapshot)
