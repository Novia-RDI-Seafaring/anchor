"""MCP-facing projection of the external OIP producer gateway."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path

from mcp.types import Tool

from anchor.adapters.extension_host import ExtensionRuntimeStatus
from anchor.adapters.external_producers import (
    ExternalProducerGateways,
    external_statuses,
)


async def catalog_tools(
    gateways: ExternalProducerGateways,
    data_dir: Path,
    *,
    multiproject: bool,
) -> list[Tool]:
    catalog = await gateways.catalog_for(data_dir)
    if not multiproject:
        return list(catalog.tools)
    return [_with_project_tool(tool) for tool in catalog.tools]


async def combined_statuses(
    gateways: ExternalProducerGateways,
    data_dir: Path,
    bundled: Mapping[str, ExtensionRuntimeStatus],
) -> dict[str, ExtensionRuntimeStatus]:
    catalog = await gateways.catalog_for(data_dir)
    return {**bundled, **external_statuses(catalog.statuses)}


def _with_project_tool(tool: Tool) -> Tool:
    schema = copy.deepcopy(tool.inputSchema)
    properties = schema.setdefault("properties", {})
    properties["project"] = {
        "type": "string",
        "description": "Anchor project name (default: current project).",
    }
    return tool.model_copy(update={"inputSchema": schema})
