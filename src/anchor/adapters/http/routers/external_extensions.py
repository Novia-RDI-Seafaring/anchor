"""HTTP adapter for enabled external OIP producer tools."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from anchor.adapters.external_oip.gateway import (
    ExternalProducerError,
    ExternalProducerGateway,
    ExternalToolNotFoundError,
)
from anchor.adapters.external_producers import external_catalog_payload

router = APIRouter(prefix="/api/extensions/external", tags=["extensions"])


def get_external_gateway(request: Request) -> ExternalProducerGateway:
    return request.app.state.external_gateway


@router.get("/tools")
async def list_external_tools(request: Request) -> dict[str, object]:
    """Start enabled producers and return their namespaced tool catalog."""
    gateway = get_external_gateway(request)
    return external_catalog_payload(await gateway.catalog())


@router.post("/call/{tool_name:path}")
async def call_external_tool(
    tool_name: str,
    arguments: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    """Call one enabled external tool with MCP-compatible arguments."""
    gateway = get_external_gateway(request)
    try:
        result = await gateway.call(tool_name, arguments)
    except ExternalToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExternalProducerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump(mode="json", by_alias=True, exclude_none=True)
