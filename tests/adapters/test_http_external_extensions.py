"""HTTP parity tests for external OIP producer tools."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from mcp.types import CallToolResult, TextContent, Tool

from anchor.adapters.external_oip.gateway import (
    ExternalProducerStatus,
    ExternalToolNotFoundError,
    GatewayCatalog,
)
from anchor.adapters.http.app import build_app
from tests.fixtures.services import make_in_memory_services


class FakeExternalGateway:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def catalog(self):
        return GatewayCatalog(
            tools=(
                Tool(
                    name="vendor.echo",
                    description="External echo",
                    inputSchema={"type": "object"},
                ),
            ),
            statuses=(
                ExternalProducerStatus(
                    name="vendor",
                    source="project",
                    available=True,
                    tool_count=1,
                ),
            ),
        )

    async def call(self, name, arguments):
        if name != "vendor.echo":
            raise ExternalToolNotFoundError(name)
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(arguments))]
        )

    async def close(self):
        self.closed = True


def _app(gateway):
    services = make_in_memory_services()
    return build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
        external_gateway=gateway,
    )


def test_http_lists_and_calls_external_tools():
    gateway = FakeExternalGateway()

    with TestClient(_app(gateway)) as client:
        catalog = client.get("/api/extensions/external/tools")
        called = client.post(
            "/api/extensions/external/call/vendor.echo",
            json={"value": 11},
        )

    assert catalog.status_code == 200
    assert catalog.json()["tools"][0]["name"] == "vendor.echo"
    assert called.status_code == 200
    assert json.loads(called.json()["content"][0]["text"]) == {"value": 11}
    assert gateway.calls == [("vendor.echo", {"value": 11})]
    assert gateway.closed is True


def test_http_status_includes_external_diagnostics():
    gateway = FakeExternalGateway()

    with TestClient(_app(gateway)) as client:
        response = client.get("/api/extensions/status")

    assert response.status_code == 200
    assert response.json() == {
        "extensions": [
            {
                "name": "vendor",
                "source": "project",
                "available": True,
                "reason": None,
                "error_type": None,
            }
        ],
        "summary": {"available": 1, "unavailable": 0},
    }


def test_http_unknown_external_tool_is_404():
    gateway = FakeExternalGateway()

    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/api/extensions/external/call/vendor.missing",
            json={},
        )

    assert response.status_code == 404
