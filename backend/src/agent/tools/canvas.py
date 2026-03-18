from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, Relation, SourceHighlight, SpecProperty, NodeStatus
from ..helpers import (
    _snapshot,
    _mark_node_for_run,
    _ensure_relation,
    _ensure_evidence_relation,
    _resolve_source_details,
    _get_cached_document_id,
    _find_node_by_title,
)


async def check_canvas(ctx: RunContext[AgentDeps]):
    """Return the current canvas state (nodes + relations)."""
    return ctx.deps.state


async def add_topic(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id."""
    node = CanvasNode(node_type="topic", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_concept(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a concept node — the root organizer for a knowledge cluster.
    A concept represents the high-level subject (e.g. 'A2UI', 'Material X').
    Returns the node id; reuse it when calling resolve_technical_query.
    """
    node = CanvasNode(node_type="concept", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_fact(
    ctx: RunContext[AgentDeps],
    text: str,
    topic_id: str,
    status: NodeStatus = "found",
    doc_id: str | None = None,
    page: int = 0,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
) -> ToolReturn:
    """Add a fact node linked to a topic.

    Optionally attach evidence by providing doc_id + page (or chunk_index to use cached
    search results). The evidence creates an edge from this fact to the document node.
    """
    node = CanvasNode(node_type="fact", text=text, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    _ensure_relation(ctx, topic_id, node.id)

    resolved_doc_id = doc_id or _get_cached_document_id(ctx, chunk_index)
    if resolved_doc_id:
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
            ctx=ctx, page=page if page else None, bbox=bbox, highlights=highlights, chunk_index=chunk_index,
        )
        _ensure_evidence_relation(
            ctx, node.id, resolved_doc_id,
            page=resolved_page or page or 0,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )

    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_spec_node(
    ctx: RunContext[AgentDeps],
    parent_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    status: NodeStatus = "found",
    doc_id: str | None = None,
    page: int = 0,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
) -> ToolReturn:
    """Add a spec (property table) node linked to a topic.

    Use for tabular/parametric data: dimensions, ratings, model numbers, etc.
    Optionally attach evidence by providing doc_id (or use chunk_index for cached results).
    """
    node = CanvasNode(
        node_type="spec",
        spec_title=spec_title,
        properties=properties,
        status=status,
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    _ensure_relation(ctx, parent_id, node.id)

    resolved_doc_id = doc_id or _get_cached_document_id(ctx, chunk_index)
    if resolved_doc_id:
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
            ctx=ctx, page=page if page else None, bbox=bbox, highlights=highlights, chunk_index=chunk_index,
        )
        _ensure_evidence_relation(
            ctx, node.id, resolved_doc_id,
            page=resolved_page or page or 0,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )

    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result


async def add_relation(
    ctx: RunContext[AgentDeps],
    from_id: str,
    to_id: str,
    label: str = "",
) -> ToolReturn:
    """Connect any two canvas nodes with an optional relationship label."""
    ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))
    return _snapshot(ctx)


async def update_node(
    ctx: RunContext[AgentDeps],
    node_id: str,
    status: NodeStatus | None = None,
    title: str | None = None,
    text: str | None = None,
    spec_title: str | None = None,
    properties: list[SpecProperty] | None = None,
) -> ToolReturn:
    """Update fields on an existing canvas node.

    Only the fields you provide are changed; others stay as-is.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == node_id), None)
    if node is None:
        return ToolReturn(return_value={"success": False, "error": f"Node {node_id} not found"})
    _mark_node_for_run(node, ctx)
    if status is not None:
        node.status = status
    if title is not None:
        node.title = title
    if text is not None:
        node.text = text
    if spec_title is not None:
        node.spec_title = spec_title
    if properties is not None:
        node.properties = properties
    return _snapshot(ctx)


async def delete_node(ctx: RunContext[AgentDeps], node_id: str) -> ToolReturn:
    """Delete a canvas node and all its relations."""
    ctx.deps.state.nodes = [n for n in ctx.deps.state.nodes if n.id != node_id]
    ctx.deps.state.relations = [
        r for r in ctx.deps.state.relations
        if r.from_id != node_id and r.to_id != node_id
    ]
    return _snapshot(ctx)
