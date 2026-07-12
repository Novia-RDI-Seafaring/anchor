"""External OIP producer gateway policy and routing tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from anchor.adapters.external_oip.gateway import (
    ExternalProducerGateway,
    ExternalToolNotFoundError,
    ProducerSpec,
)


class FakeProducerClient:
    def __init__(
        self,
        tools: list[Tool],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.tools = tools
        self.failure = failure
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def list_tools(self) -> list[Tool]:
        if self.failure is not None:
            raise self.failure
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        if self.failure is not None:
            raise self.failure
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text=f"called:{name}")]
        )

    async def close(self) -> None:
        self.closed = True


def _manifest(
    name: str,
    namespace: str,
    *,
    command: str = "producer-mcp",
    kind: str = "mcp-stdio",
    source: str = "project",
) -> dict[str, Any]:
    return {
        "oip_version": "0.1",
        "producer": {"name": name, "version": "1.0.0"},
        "invocation": {
            "kind": kind,
            "command": command,
            "args": ["--quiet"],
            "tools_namespace": namespace,
        },
        "_anchor_source": source,
        "_anchor_execution_enabled": True,
    }


def _tool(name: str) -> Tool:
    return Tool(
        name=name,
        description=f"Test tool {name}",
        inputSchema={"type": "object"},
    )


@pytest.mark.asyncio
async def test_catalog_namespaces_tools_and_call_forwards_remote_name():
    client = FakeProducerClient([_tool("inspect")])

    async def connect(_spec: ProducerSpec) -> FakeProducerClient:
        return client

    gateway = ExternalProducerGateway(
        [_manifest("third-party-cad", "vendor_cad")],
        connector=connect,
    )

    catalog = await gateway.catalog()
    result = await gateway.call("vendor_cad.inspect", {"slug": "pump"})

    assert [tool.name for tool in catalog.tools] == ["vendor_cad.inspect"]
    assert catalog.statuses[0].available is True
    assert catalog.statuses[0].tool_count == 1
    assert client.calls == [("inspect", {"slug": "pump"})]
    assert result.content[0].text == "called:inspect"
    await gateway.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_invalid_invocation_fails_closed_without_connecting():
    connected = False

    async def connect(_spec: ProducerSpec) -> FakeProducerClient:
        nonlocal connected
        connected = True
        return FakeProducerClient([])

    gateway = ExternalProducerGateway(
        [_manifest("remote-only", "remote", kind="mcp-http")],
        connector=connect,
    )

    catalog = await gateway.catalog()

    assert catalog.tools == ()
    assert catalog.statuses[0].available is False
    assert "mcp-stdio" in (catalog.statuses[0].reason or "")
    assert connected is False


@pytest.mark.asyncio
async def test_registered_but_disabled_manifest_is_never_started():
    manifest = _manifest("disabled", "disabled")
    manifest["_anchor_execution_enabled"] = False
    connected = False

    async def connect(_spec: ProducerSpec) -> FakeProducerClient:
        nonlocal connected
        connected = True
        return FakeProducerClient([])

    gateway = ExternalProducerGateway(
        [manifest],
        connector=connect,
    )
    catalog = await gateway.catalog()

    assert catalog.statuses[0].available is False
    assert "extensions enable disabled" in (catalog.statuses[0].reason or "")
    assert connected is False
    assert gateway.can_handle("disabled.some_tool") is True


@pytest.mark.asyncio
async def test_external_producer_cannot_reuse_bundled_identity():
    catalog = await ExternalProducerGateway(
        [_manifest("anchor-cad", "other_cad")],
        reserved_producer_names={"anchor-cad"},
    ).catalog()

    assert catalog.tools == ()
    assert catalog.statuses[0].error_type == "ProducerNameCollisionError"


@pytest.mark.asyncio
async def test_namespace_collision_disables_both_producers():
    gateway = ExternalProducerGateway(
        [
            _manifest("producer-a", "shared"),
            _manifest("producer-b", "shared", source="system"),
        ]
    )

    catalog = await gateway.catalog()

    assert catalog.tools == ()
    assert {status.name for status in catalog.statuses} == {
        "producer-a",
        "producer-b",
    }
    assert all(status.error_type == "NamespaceCollisionError" for status in catalog.statuses)


@pytest.mark.asyncio
async def test_failing_producer_does_not_hide_working_catalog():
    clients = {
        "broken": FakeProducerClient([], failure=RuntimeError("startup failed")),
        "working": FakeProducerClient([_tool("run")]),
    }

    async def connect(spec: ProducerSpec) -> FakeProducerClient:
        return clients[spec.name]

    gateway = ExternalProducerGateway(
        [_manifest("broken", "bad"), _manifest("working", "good")],
        connector=connect,
    )

    catalog = await gateway.catalog()

    assert [tool.name for tool in catalog.tools] == ["good.run"]
    by_name = {status.name: status for status in catalog.statuses}
    assert by_name["broken"].available is False
    assert by_name["broken"].reason == "startup failed"
    assert by_name["working"].available is True
    assert clients["broken"].closed is True


@pytest.mark.asyncio
async def test_unknown_external_tool_has_actionable_error():
    async def connect(_spec: ProducerSpec) -> FakeProducerClient:
        return FakeProducerClient([_tool("known")])

    gateway = ExternalProducerGateway(
        [_manifest("producer", "sample")],
        connector=connect,
    )

    with pytest.raises(ExternalToolNotFoundError, match="sample.missing"):
        await gateway.call("sample.missing")
    await gateway.close()


@pytest.mark.asyncio
async def test_real_mcp_stdio_process_catalog_call_and_shutdown():
    script = Path(__file__).parents[1] / "fixtures" / "external_oip_mcp_server.py"
    manifest = _manifest(
        "process-fixture",
        "fixture",
        command=sys.executable,
    )
    manifest["invocation"]["args"] = [str(script)]
    gateway = ExternalProducerGateway([manifest])

    catalog = await gateway.catalog()
    result = await gateway.call("fixture.echo", {"value": 42})

    assert [tool.name for tool in catalog.tools] == ["fixture.echo"]
    assert result.content[0].text == '{"echo": 42}'
    await gateway.close()
