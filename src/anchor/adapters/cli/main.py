"""Typer application assembly for the ``anchor`` CLI."""

from __future__ import annotations

import typer

from anchor.adapters.cli.cad import cad_app
from anchor.adapters.cli.canvas import canvas_app
from anchor.adapters.cli.check import check
from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.demo import _DEMO_PLACEHOLDER_HINTS, _find_sample_pdf, demo
from anchor.adapters.cli.documents import register_document_commands
from anchor.adapters.cli.extensions import extensions_app
from anchor.adapters.cli.fmu import fmu_app
from anchor.adapters.cli.ingest_session import ingest_session_app
from anchor.adapters.cli.init import init
from anchor.adapters.cli.install import install_app
from anchor.adapters.cli.serve import serve
from anchor.adapters.cli.services import _build_real_services
from anchor.adapters.cli.sysml import sysml_app

# pretty_exceptions_show_locals=False: rendering locals dumps the full
# pydantic-core validator repr for docling's input union (~tens of KB) on a
# ConversionError, burying the actionable cause. Keep tracebacks lean.
app = typer.Typer(
    help="Anchor - agent-first knowledge canvas.",
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        from anchor import __version__

        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """Anchor - agent-first knowledge canvas.

    Quiet noisy third-party output (HuggingFace, docling) on every command so
    output stays machine-readable; ANCHOR_LOG_LEVEL=DEBUG restores it.
    """
    from anchor.infra.quiet import quiet_dependency_logs

    quiet_dependency_logs()


app.command()(init)
app.command()(check)
app.command()(serve)
register_document_commands(app)
app.command()(demo)

app.add_typer(ingest_session_app, name="ingest-session")
app.add_typer(canvas_app, name="canvas")
app.add_typer(sysml_app, name="sysml")
app.add_typer(fmu_app, name="fmu")
app.add_typer(cad_app, name="cad")
app.add_typer(install_app, name="install")
app.add_typer(extensions_app, name="extensions")

__all__ = [
    "DEFAULT_DATA_DIR",
    "_DEMO_PLACEHOLDER_HINTS",
    "_build_real_services",
    "_find_sample_pdf",
    "app",
    "init",
]


@app.command()
def version() -> None:
    """Print the installed Anchor version."""
    from anchor import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
