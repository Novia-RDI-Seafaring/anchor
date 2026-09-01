"""Checked operation inventory for adapter parity.

These descriptors are a small, explicit map from core canvas operations to
their HTTP, MCP, and CLI surfaces. They do not generate adapter code. Their
job is to make parity drift testable before it becomes user-visible.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HttpSurface:
    method: str
    path: str


@dataclass(frozen=True, slots=True)
class OperationDescriptor:
    id: str
    service_method: str
    http: HttpSurface
    mcp_tool: str
    cli_command: tuple[str, ...]


CANVAS_OPERATION_DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    OperationDescriptor(
        id="canvas.list_workspaces",
        service_method="list_workspaces",
        http=HttpSurface("GET", "/api/workspaces"),
        mcp_tool="canvas_list_workspaces",
        cli_command=("canvas", "list"),
    ),
    OperationDescriptor(
        id="canvas.create_workspace",
        service_method="create_workspace",
        http=HttpSurface("POST", "/api/workspaces"),
        mcp_tool="canvas_create_workspace",
        cli_command=("canvas", "create"),
    ),
    OperationDescriptor(
        id="canvas.delete_workspace",
        service_method="delete_workspace",
        http=HttpSurface("DELETE", "/api/workspaces/{slug}"),
        mcp_tool="canvas_delete_workspace",
        cli_command=("canvas", "delete"),
    ),
    OperationDescriptor(
        id="canvas.get_state",
        service_method="get_state",
        http=HttpSurface("GET", "/api/workspaces/{slug}/state"),
        mcp_tool="canvas_get_state",
        cli_command=("canvas", "state"),
    ),
    OperationDescriptor(
        id="canvas.add_node",
        service_method="add_node",
        http=HttpSurface("POST", "/api/workspaces/{slug}/nodes"),
        mcp_tool="canvas_add_node",
        cli_command=("canvas", "add-node"),
    ),
    OperationDescriptor(
        id="canvas.update_node",
        service_method="update_node",
        http=HttpSurface("PATCH", "/api/workspaces/{slug}/nodes/{node_id}"),
        mcp_tool="canvas_update_node",
        cli_command=("canvas", "update-node"),
    ),
    OperationDescriptor(
        id="canvas.remove_node",
        service_method="remove_node",
        http=HttpSurface("DELETE", "/api/workspaces/{slug}/nodes/{node_id}"),
        mcp_tool="canvas_remove_node",
        cli_command=("canvas", "remove-node"),
    ),
    OperationDescriptor(
        id="canvas.add_edge",
        service_method="add_edge",
        http=HttpSurface("POST", "/api/workspaces/{slug}/edges"),
        mcp_tool="canvas_add_edge",
        cli_command=("canvas", "add-edge"),
    ),
    OperationDescriptor(
        id="canvas.update_edge",
        service_method="update_edge",
        http=HttpSurface("PATCH", "/api/workspaces/{slug}/edges/{edge_id}"),
        mcp_tool="canvas_update_edge",
        cli_command=("canvas", "update-edge"),
    ),
    OperationDescriptor(
        id="canvas.remove_edge",
        service_method="remove_edge",
        http=HttpSurface("DELETE", "/api/workspaces/{slug}/edges/{edge_id}"),
        mcp_tool="canvas_remove_edge",
        cli_command=("canvas", "remove-edge"),
    ),
    OperationDescriptor(
        id="canvas.clear",
        service_method="clear",
        http=HttpSurface("POST", "/api/workspaces/{slug}/clear"),
        mcp_tool="canvas_clear",
        cli_command=("canvas", "clear"),
    ),
)


# Document (anchor_pdfs) read ops. `service_method` resolves against DocStore or
# IngestService; CLI commands are root-level (`anchor <cmd>`), so the tuple is a
# single element. inspect_region / get_region_content are #242 P1 additions
# backed by DocStore.get_regions.
DOCUMENT_OPERATION_DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    OperationDescriptor(
        id="document.get_index",
        service_method="get_index",
        http=HttpSurface("GET", "/api/documents/{slug}/index"),
        mcp_tool="get_document_index",
        cli_command=("index",),
    ),
    OperationDescriptor(
        id="document.get_regions",
        service_method="get_regions",
        http=HttpSurface("GET", "/api/documents/{slug}/regions"),
        mcp_tool="get_gold_regions",
        cli_command=("regions",),
    ),
    OperationDescriptor(
        id="document.get_page_text",
        service_method="get_page_text",
        http=HttpSurface("GET", "/api/documents/{slug}/pages/{page}/text"),
        mcp_tool="get_page_text",
        cli_command=("page-text",),
    ),
    OperationDescriptor(
        id="document.search",
        service_method="search",
        http=HttpSurface("GET", "/api/documents/_search"),
        mcp_tool="search_documents",
        cli_command=("search",),
    ),
    OperationDescriptor(
        id="document.inspect_region",
        service_method="get_regions",
        http=HttpSurface("GET", "/api/documents/{slug}/regions/{region_id:path}"),
        mcp_tool="inspect_region",
        cli_command=("inspect-region",),
    ),
    OperationDescriptor(
        id="document.get_region_content",
        service_method="get_regions",
        http=HttpSurface("GET", "/api/documents/{slug}/region-content/{region_id:path}"),
        mcp_tool="get_region_content",
        cli_command=("region-content",),
    ),
)
