"""MCP aggregation tests for process-isolated external OIP producers."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)

from anchor.adapters.external_oip.gateway import (
    ExternalProducerStatus,
    GatewayCatalog,
)
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.mcp.services import build_bundle
from anchor.infra.config import AnchorConfig


class FakeExternalGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def can_handle(self, name: str) -> bool:
        return name.startswith("vendor.")

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(arguments))],
            structuredContent={"proxied": True},
        )


class FakeExternalGateways:
    def __init__(self) -> None:
        self.gateway = FakeExternalGateway()
        self.closed = False
        self.catalog = GatewayCatalog(
            tools=(
                Tool(
                    name="vendor.echo",
                    description="External echo",
                    inputSchema={
                        "type": "object",
                        "properties": {"value": {}},
                    },
                ),
            ),
            statuses=(
                ExternalProducerStatus(
                    name="vendor-producer",
                    source="project",
                    available=True,
                    tool_count=1,
                ),
            ),
        )

    async def catalog_for(self, _data_dir) -> GatewayCatalog:
        return self.catalog

    async def gateway_for(self, _data_dir) -> FakeExternalGateway:
        return self.gateway

    async def close(self) -> None:
        self.closed = True


def _server(tmp_path):
    gateways = FakeExternalGateways()
    bundle = build_bundle(AnchorConfig(data_dir=tmp_path / "data"))
    return (
        build_mcp_server(bundle=bundle, external_gateways=gateways),
        gateways,
    )


async def test_external_tools_are_advertised_with_namespaced_name(tmp_path):
    server, _gateways = _server(tmp_path)
    handler = server.request_handlers[ListToolsRequest]

    result = await handler(ListToolsRequest(method="tools/list"))

    tools = {tool.name: tool for tool in result.root.tools}
    assert tools["vendor.echo"].description == "External echo"


async def test_external_tool_call_preserves_native_mcp_result(tmp_path):
    server, gateways = _server(tmp_path)
    handler = server.request_handlers[CallToolRequest]
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="vendor.echo",
            arguments={"value": 7},
        ),
    )

    result = await handler(request)

    assert result.root.content[0].text == '{"value": 7}'
    assert result.root.structuredContent == {"proxied": True}
    assert gateways.gateway.calls == [("vendor.echo", {"value": 7})]


async def test_extension_status_includes_external_producer(tmp_path):
    server, _gateways = _server(tmp_path)
    handler = server.request_handlers[CallToolRequest]
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="anchor_extension_status",
            arguments={},
        ),
    )

    result = await handler(request)

    payload = json.loads(result.root.content[0].text)
    by_name = {item["name"]: item for item in payload["extensions"]}
    assert by_name["vendor-producer"] == {
        "name": "vendor-producer",
        "source": "project",
        "available": True,
        "reason": None,
        "error_type": None,
    }


async def test_mcp_lifespan_closes_external_processes(tmp_path):
    server, gateways = _server(tmp_path)

    async with server.lifespan(server):
        assert gateways.closed is False

    assert gateways.closed is True
