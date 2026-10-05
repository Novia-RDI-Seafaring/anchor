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
        id="canvas.changes",
        service_method="canvas_changes",
        http=HttpSurface("GET", "/api/workspaces/{slug}/changes"),
        mcp_tool="canvas_changes",
        cli_command=("canvas", "changes"),
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
    OperationDescriptor(
        id="canvas.propose_set",
        service_method="open_proposal_set",
        http=HttpSurface("POST", "/api/workspaces/{slug}/proposal-sets"),
        mcp_tool="canvas_propose_set",
        cli_command=("canvas", "propose-set"),
    ),
    OperationDescriptor(
        id="canvas.add_proposal_set_members",
        service_method="add_proposal_set_members",
        http=HttpSurface("POST", "/api/workspaces/{slug}/proposal-sets/{set_id}/members"),
        mcp_tool="canvas_add_to_proposal_set",
        cli_command=("canvas", "add-to-set"),
    ),
    OperationDescriptor(
        id="canvas.list_proposal_sets",
        service_method="list_proposal_sets",
        http=HttpSurface("GET", "/api/workspaces/{slug}/proposal-sets"),
        mcp_tool="canvas_list_proposal_sets",
        cli_command=("canvas", "proposal-sets"),
    ),
    OperationDescriptor(
        id="canvas.review_proposal_set",
        service_method="review_proposal_set",
        http=HttpSurface("POST", "/api/workspaces/{slug}/proposal-sets/{set_id}/review"),
        mcp_tool="canvas_review_proposal_set",
        cli_command=("canvas", "review-set"),
    ),
    # Presence is served by the in-memory PresenceTracker (per serve
    # process), not WorkspaceService; the parity test resolves
    # `service_method` against either.
    OperationDescriptor(
        id="canvas.presence",
        service_method="roster",
        http=HttpSurface("GET", "/api/workspaces/{slug}/presence"),
        mcp_tool="canvas_presence",
        cli_command=("canvas", "presence"),
    ),
)


# Scoped-ask threads (#343). `service_method` resolves against IntentService.
# CLI commands hang off `anchor intent <cmd>`; the inbox verbs (`anchor
# intents`, `anchor intent next/resolve`) predate the descriptor table and
# are covered by the intents surface tests.
INTENT_OPERATION_DESCRIPTORS: tuple[OperationDescriptor, ...] = (
    OperationDescriptor(
        id="intent.ask",
        service_method="enqueue",
        http=HttpSurface("POST", "/api/intents"),
        mcp_tool="intent_ask",
        cli_command=("intent", "ask"),
    ),
    OperationDescriptor(
        id="intent.get",
        service_method="get",
        http=HttpSurface("GET", "/api/intents/{intent_id}"),
        mcp_tool="get_intent",
        cli_command=("intent", "show"),
    ),
    OperationDescriptor(
        id="intent.add_item",
        service_method="add_item",
        http=HttpSurface("POST", "/api/intents/{intent_id}/items"),
        mcp_tool="intent_add_item",
        cli_command=("intent", "add-item"),
    ),
    OperationDescriptor(
        id="intent.answer",
        service_method="answer_question",
        http=HttpSurface("POST", "/api/intents/{intent_id}/items/{item_id}/answer"),
        mcp_tool="intent_answer",
        cli_command=("intent", "answer"),
    ),
    OperationDescriptor(
        id="intent.apply",
        service_method="apply_suggestion",
        http=HttpSurface("POST", "/api/intents/{intent_id}/items/{item_id}/apply"),
        mcp_tool="intent_apply",
        cli_command=("intent", "apply"),
    ),
    OperationDescriptor(
        id="intent.decline",
        service_method="decline_suggestion",
        http=HttpSurface("POST", "/api/intents/{intent_id}/items/{item_id}/decline"),
        mcp_tool="intent_decline",
        cli_command=("intent", "decline"),
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
        id="document.list_entities",
        service_method="get_regions",
        http=HttpSurface("GET", "/api/documents/{slug}/entities"),
        mcp_tool="list_entities",
        cli_command=("entities",),
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
    OperationDescriptor(
        id="document.derive_region",
        service_method="derive_region",
        http=HttpSurface("POST", "/api/documents/{slug}/derived-regions"),
        mcp_tool="derive_region",
        cli_command=("derive-region",),
    ),
    OperationDescriptor(
        id="document.remove_region",
        service_method="remove_region",
        http=HttpSurface("DELETE", "/api/documents/{slug}/regions/{region_id:path}"),
        mcp_tool="remove_region",
        cli_command=("remove-region",),
    ),
    OperationDescriptor(
        id="document.resolve_source_ref",
        service_method="resolve_source_ref",
        http=HttpSurface("GET", "/api/documents/{slug}/resolve-ref"),
        mcp_tool="resolve_source_ref",
        cli_command=("resolve-ref",),
    ),
)
