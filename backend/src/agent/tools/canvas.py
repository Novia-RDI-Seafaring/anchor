from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, Relation, SourceHighlight, SpecProperty, NodeStatus
from ..helpers import (
    _snapshot, 
    _mark_node_for_run, 
    _ensure_relation, 
    _resolve_source_details, 
    _get_or_create_source_node
)

async def check_canvas(ctx: RunContext[AgentDeps]):
    """Return the current canvas state (nodes + relations)."""
    return ctx.deps.state

async def add_topic(
    ctx: RunContext[AgentDeps],
    title: str,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Add a topic node to the canvas. Returns the new node's id.

    During the PLAN phase use status="pending". Set status="found" once confirmed.
    """
    node = CanvasNode(node_type="topic", title=title, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result

async def add_fact(
    ctx: RunContext[AgentDeps],
    text: str,
    topic_id: str,
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a fact node linked to a topic. Returns the new node's id.

    During the PLAN phase, pass a placeholder text and status="pending".
    After finding the data, prefer finalize_fact_with_source to fill the real
    text, mark the status, and attach evidence in one step.
    """
    node = CanvasNode(node_type="fact", text=text, status=status)
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=topic_id, to_id=node.id))
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result

async def add_source(
    ctx: RunContext[AgentDeps],
    fact_id: str,
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
) -> ToolReturn:
    """Add a source node linked to a fact.

    - page / bbox: primary reference (first/most relevant location).
    - highlights: ordered list of {page, bbox} refs so the PDF viewer can
      step through all relevant locations in the document. If omitted, a
      single highlight is created from page + bbox automatically.
    - If filename/page/bbox are omitted, the tool uses the cached chunk from the
      most recent search_knowledge_base call in this run.

    bbox format: [left, top, right, bottom] in PDF points (BOTTOMLEFT origin).
    Use [0,0,0,0] if the bounding box is unknown.
    """
    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )
    if not resolved_filename or resolved_page is None:
        return ToolReturn(
            return_value={
                "success": False,
                "error": "Source details missing. Provide filename/page/bbox or search the knowledge base first.",
            }
        )

    source_node = _get_or_create_source_node(
        ctx=ctx,
        filename=resolved_filename,
        page=resolved_page,
        bbox=resolved_bbox,
        highlights=resolved_highlights,
    )
    if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
        ctx.deps.state.nodes.append(source_node)
    _ensure_relation(ctx, fact_id, source_node.id)

    result = _snapshot(ctx)
    result.return_value = {"success": True, "fact_id": fact_id, "source_id": source_node.id}
    return result

async def add_relation(ctx: RunContext[AgentDeps], from_id: str, to_id: str, label: str = "") -> ToolReturn:
    """Connect any two canvas nodes with an optional relationship label."""
    ctx.deps.state.relations.append(Relation(from_id=from_id, to_id=to_id, label=label))
    return _snapshot(ctx)

async def add_spec_node(
    ctx: RunContext[AgentDeps],
    parent_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    status: NodeStatus = "pending",
) -> ToolReturn:
    """Add a spec (property table) node linked to a topic or fact.

    Use this instead of add_fact when data is tabular/parametric:
    dimensions, temperatures, flow rates, material grades, model numbers, etc.

    During the PLAN phase use status="pending" and an empty properties list.
    After extracting the table data, prefer finalize_spec_with_source so the
    table and supporting evidence are attached together.

    - parent_id: id of the parent topic or fact node
    - spec_title: short label for the table (e.g. "Dimensions (mm)", "Operating Limits")
    - properties: list of {key, value, unit} rows (can be [] during planning)
    """
    node = CanvasNode(
        node_type="spec",
        spec_title=spec_title,
        properties=properties,
        status=status,
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    ctx.deps.state.relations.append(Relation(from_id=parent_id, to_id=node.id))
    result = _snapshot(ctx)
    result.return_value = {"success": True, "id": node.id}
    return result

async def finalize_fact_with_source(
    ctx: RunContext[AgentDeps],
    fact_id: str,
    text: str,
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Finalize an existing fact node and attach a source in one step.

    Use this after you already created a pending fact during the planning phase.
    This is the preferred way to complete a factual finding because it updates the
    text, marks the status, and connects the source evidence in a single action.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == fact_id), None)
    if node is None or node.node_type != "fact":
        return ToolReturn(return_value={"success": False, "error": f"Fact node {fact_id} not found"})

    _mark_node_for_run(node, ctx)
    node.text = text
    node.status = status

    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )

    if resolved_filename and resolved_page is not None:
        source_node = _get_or_create_source_node(
            ctx=ctx,
            filename=resolved_filename,
            page=resolved_page,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )
        if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
            ctx.deps.state.nodes.append(source_node)
        _ensure_relation(ctx, fact_id, source_node.id)

    return _snapshot(ctx)

async def finalize_spec_with_source(
    ctx: RunContext[AgentDeps],
    spec_id: str,
    spec_title: str,
    properties: list[SpecProperty],
    filename: str | None = None,
    page: int | None = None,
    bbox: list[float] | None = None,
    highlights: list[SourceHighlight] | None = None,
    chunk_index: int = 0,
    status: NodeStatus = "found",
) -> ToolReturn:
    """Finalize an existing spec node and attach a source in one step.

    Use this after planning a pending spec node when the retrieved result is
    best represented as a table or property list. If you have just called
    search_knowledge_base, you can omit filename/page/bbox and use chunk_index.
    """
    node = next((n for n in ctx.deps.state.nodes if n.id == spec_id), None)
    if node is None or node.node_type != "spec":
        return ToolReturn(return_value={"success": False, "error": f"Spec node {spec_id} not found"})

    _mark_node_for_run(node, ctx)
    node.spec_title = spec_title
    node.properties = properties
    node.status = status

    resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(
        ctx=ctx,
        filename=filename,
        page=page,
        bbox=bbox,
        highlights=highlights,
        chunk_index=chunk_index,
    )

    if resolved_filename and resolved_page is not None:
        source_node = _get_or_create_source_node(
            ctx=ctx,
            filename=resolved_filename,
            page=resolved_page,
            bbox=resolved_bbox,
            highlights=resolved_highlights,
        )
        if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
            ctx.deps.state.nodes.append(source_node)
        _ensure_relation(ctx, spec_id, source_node.id)

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

    Use this to:
    - Mark a node's status after searching (status="found"/"partial"/"not_found")
    - Fill in the real content after planning (text, title, spec_title, properties)
    - Correct or refine previously added content

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

    has_linked_source = any(
        rel.from_id == node.id
        and any(candidate.id == rel.to_id and candidate.node_type == "source" for candidate in ctx.deps.state.nodes)
        for rel in ctx.deps.state.relations
    )
    if (
        node.node_type in {"fact", "spec"}
        and node.status in {"found", "partial"}
        and not has_linked_source
    ):
        resolved_filename, resolved_page, resolved_bbox, resolved_highlights = _resolve_source_details(ctx=ctx)
        if resolved_filename and resolved_page is not None:
            source_node = _get_or_create_source_node(
                ctx=ctx,
                filename=resolved_filename,
                page=resolved_page,
                bbox=resolved_bbox,
                highlights=resolved_highlights,
            )
            if not any(n.id == source_node.id for n in ctx.deps.state.nodes):
                ctx.deps.state.nodes.append(source_node)
            _ensure_relation(ctx, node.id, source_node.id)
    return _snapshot(ctx)

async def delete_node(ctx: RunContext[AgentDeps], node_id: str) -> ToolReturn:
    """Delete a canvas node and all its relations.

    Use this to remove placeholder nodes that turned out to be irrelevant,
    or to clean up duplicates.
    """
    ctx.deps.state.nodes = [n for n in ctx.deps.state.nodes if n.id != node_id]
    ctx.deps.state.relations = [
        r for r in ctx.deps.state.relations
        if r.from_id != node_id and r.to_id != node_id
    ]
    return _snapshot(ctx)
