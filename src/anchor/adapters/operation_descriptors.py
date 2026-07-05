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


def canvas_operation_descriptors() -> tuple[OperationDescriptor, ...]:
    return CANVAS_OPERATION_DESCRIPTORS
