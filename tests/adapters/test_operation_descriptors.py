"""Adapter parity checks for the checked operation inventory."""

from __future__ import annotations

import typer
from fastapi.routing import APIRoute

from anchor.adapters.cli.canvas import canvas_app
from anchor.adapters.cli.documents import register_document_commands
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import handlers_canvas
from anchor.adapters.operation_descriptors import (
    CANVAS_OPERATION_DESCRIPTORS,
    DOCUMENT_OPERATION_DESCRIPTORS,
)
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.mcp_tool_definitions import tool_definitions as pdf_tool_definitions
from tests.fixtures.services import make_in_memory_services


def _http_surfaces() -> set[tuple[str, str]]:
    services = make_in_memory_services()
    app = build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
    )
    surfaces: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            if method != "HEAD":
                surfaces.add((method, route.path))
    return surfaces


def _canvas_cli_commands() -> set[str]:
    return {cmd.name for cmd in canvas_app.registered_commands}


def test_canvas_operation_descriptors_are_unique():
    ids = [op.id for op in CANVAS_OPERATION_DESCRIPTORS]
    assert len(ids) == len(set(ids))


def test_canvas_operation_descriptors_match_adapter_surfaces():
    http = _http_surfaces()
    mcp = {tool["name"] for tool in handlers_canvas.tool_definitions()}
    cli = _canvas_cli_commands()

    for op in CANVAS_OPERATION_DESCRIPTORS:
        assert hasattr(WorkspaceService, op.service_method), op.id
        assert (op.http.method, op.http.path) in http, op.id
        assert op.mcp_tool in mcp, op.id
        assert op.cli_command[0] == "canvas", op.id
        assert op.cli_command[1] in cli, op.id


def _document_cli_commands() -> set[str]:
    app = typer.Typer()
    register_document_commands(app)
    names: set[str] = set()
    for cmd in app.registered_commands:
        # Bare `app.command()(fn)` leaves name=None; typer derives it from the
        # callback name (underscores -> hyphens) at build time.
        name = cmd.name
        if name is None and cmd.callback is not None:
            name = cmd.callback.__name__.replace("_", "-")
        if name:
            names.add(name)
    return names


def test_document_operation_descriptors_are_unique():
    ids = [op.id for op in DOCUMENT_OPERATION_DESCRIPTORS]
    assert len(ids) == len(set(ids))


def test_document_operation_descriptors_match_adapter_surfaces():
    http = _http_surfaces()
    mcp = {tool["name"] for tool in pdf_tool_definitions()}
    cli = _document_cli_commands()

    for op in DOCUMENT_OPERATION_DESCRIPTORS:
        assert (
            hasattr(DocStore, op.service_method)
            or hasattr(IngestService, op.service_method)
        ), op.id
        assert (op.http.method, op.http.path) in http, op.id
        assert op.mcp_tool in mcp, op.id
        assert len(op.cli_command) == 1, op.id
        assert op.cli_command[0] in cli, op.id
