"""Typer application assembly for the ``anchor`` CLI."""

from __future__ import annotations

import typer

from anchor.adapters.cli.cad import cad_app
from anchor.adapters.cli.canvas import canvas_app
from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.demo import _DEMO_PLACEHOLDER_HINTS, _find_sample_pdf, demo
from anchor.adapters.cli.documents import register_document_commands
from anchor.adapters.cli.extensions import extensions_app
from anchor.adapters.cli.fmu import fmu_app
from anchor.adapters.cli.install import install_app
from anchor.adapters.cli.serve import serve
from anchor.adapters.cli.services import _build_real_services
from anchor.adapters.cli.sysml import sysml_app

app = typer.Typer(help="Anchor - agent-first knowledge canvas.")

app.command()(serve)
register_document_commands(app)
app.command()(demo)

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
]


@app.command()
def version() -> None:
    """Print the installed Anchor version."""
    from anchor import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
