"""IR → canvas batch mapping.

Pure projection: takes the ``IrModel`` produced by the parser and produces a
``CanvasBatch`` with ``CanvasNodeSpec`` / ``CanvasEdgeSpec`` entries the
service layer will hand to ``WorkspaceService.add_node`` / ``add_edge``.

Layout strategy (Phase 1): grid-pack at the package level — 4 columns, each
``CELL_W × CELL_H`` plus a ``GUTTER`` between cells. The whole batch is
shifted by the caller-supplied ``x_offset`` / ``y_offset`` so multiple
SysML imports on the same canvas don't overlap.

Cross-reference resolution (inheritance, satisfy, subject) lives in
``canvas_resolver`` so this file stays focused on emission.
"""
from __future__ import annotations

from anchor.core.ids import new_id
from anchor.extensions.anchor_sysml.core.schemas import (
    CanvasBatch,
    CanvasEdgeSpec,
    CanvasNodeSpec,
    Diagnostic,
    IrBlock,
    IrModel,
    IrPackage,
    IrRequirement,
    SourceRef,
)
from anchor.extensions.anchor_sysml.infra.canvas_layout import apply_layout
from anchor.extensions.anchor_sysml.infra.canvas_resolver import (
    index_register,
    join_qname,
    resolve_inheritance_edges,
    resolve_satisfy_edges,
    resolve_subject_edges,
)


# ── Layout constants ─────────────────────────────────────────────────────

GRID_COLS = 4
CELL_W = 280
CELL_H = 200
GUTTER = 80


def _grid_xy(index: int, x_offset: float, y_offset: float) -> tuple[float, float]:
    col = index % GRID_COLS
    row = index // GRID_COLS
    return (
        x_offset + col * (CELL_W + GUTTER),
        y_offset + row * (CELL_H + GUTTER),
    )


# ── Public API ───────────────────────────────────────────────────────────


class SysmlCanvasMapper:
    """Concrete ``CanvasMapper`` — IR → canvas batch."""

    def map(
        self,
        ir: IrModel,
        *,
        x_offset: float = 0,
        y_offset: float = 0,
    ) -> CanvasBatch:
        nodes: list[CanvasNodeSpec] = []
        edges: list[CanvasEdgeSpec] = []
        diagnostics: list[Diagnostic] = list(ir.diagnostics)
        index: dict[str, str] = {}
        # Emission writes placeholder (0, 0) coords; ``apply_layout`` below
        # repositions every node based on the resolved relationship graph.
        cursor = _Cursor(0, 0)
        for pkg in ir.packages:
            _emit_package(pkg, nodes, edges, diagnostics, index, cursor, parent_qname=None)
        # Resolve relationship edges in a second pass so forward references
        # (inheritance, satisfy targets, subjects) work even when the parent
        # block appears later in the file.
        resolve_inheritance_edges(ir, index, edges)
        resolve_satisfy_edges(ir, index, edges, diagnostics)
        resolve_subject_edges(ir, index, edges, diagnostics)
        batch = CanvasBatch(nodes=nodes, edges=edges, diagnostics=diagnostics)
        # Hierarchy-aware positions: superclass above subclasses, requirements
        # alongside their subject, packages sized to fit their members.
        apply_layout(batch, x_offset=x_offset, y_offset=y_offset)
        return batch


# ── Layout cursor ────────────────────────────────────────────────────────


class _Cursor:
    def __init__(self, x_offset: float, y_offset: float) -> None:
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.count = 0

    def next_xy(self) -> tuple[float, float]:
        x, y = _grid_xy(self.count, self.x_offset, self.y_offset)
        self.count += 1
        return x, y


# ── Emission ─────────────────────────────────────────────────────────────


def _emit_package(
    pkg: IrPackage,
    nodes: list[CanvasNodeSpec],
    edges: list[CanvasEdgeSpec],
    diagnostics: list[Diagnostic],
    index: dict[str, str],
    cursor: _Cursor,
    *,
    parent_qname: str | None,
) -> str:
    qname = join_qname(parent_qname, pkg.short_name) or pkg.qualified_name
    pkg_id = new_id()
    px, py = cursor.next_xy()
    nodes.append(
        CanvasNodeSpec(
            id=pkg_id,
            node_type="sysml:package",
            label=pkg.short_name or qname,
            x=px,
            y=py,
            data={
                "qualified_name": qname,
                "short_name": pkg.short_name,
                "doc": pkg.doc,
                "metadata": dict(pkg.metadata),
                "source_ref": _src(pkg.source_ref),
            },
        )
    )
    index_register(index, pkg_id, [qname, pkg.short_name, pkg.qualified_name])
    for blk in pkg.blocks:
        _emit_block(blk, nodes, edges, index, cursor, package_qname=qname)
    for req in pkg.requirements:
        _emit_requirement(req, nodes, index, cursor, package_qname=qname)
    for sub in pkg.sub_packages:
        _emit_package(sub, nodes, edges, diagnostics, index, cursor, parent_qname=qname)
    return pkg_id


def _emit_block(
    blk: IrBlock,
    nodes: list[CanvasNodeSpec],
    edges: list[CanvasEdgeSpec],
    index: dict[str, str],
    cursor: _Cursor,
    *,
    package_qname: str,
) -> str:
    qname = join_qname(package_qname, blk.short_name)
    blk_id = new_id()
    bx, by = cursor.next_xy()
    nodes.append(
        CanvasNodeSpec(
            id=blk_id,
            node_type="sysml:block",
            label=blk.short_name,
            x=bx,
            y=by,
            data={
                "kind": blk.kind,
                "qualified_name": qname,
                "short_name": blk.short_name,
                "attributes": [a.model_dump() for a in blk.attributes],
                "ports": [p.model_dump() for p in blk.ports],
                "parts": [p.model_dump() for p in blk.parts],
                "doc": blk.doc,
                "metadata": dict(blk.metadata),
                "source_ref": _src(blk.source_ref),
            },
        )
    )
    index_register(index, blk_id, [qname, blk.short_name, blk.qualified_name])
    if blk.typed_as:
        edges.append(
            CanvasEdgeSpec(
                source=blk_id,
                target=blk.typed_as,
                edge_type="floating",
                data={"marker": "association", "label": "typed-as", "source_ref": _src(blk.source_ref)},
            )
        )
    # Interface → port-to-port anchored edge. Endpoint paths point at handle
    # names — the frontend's anchored-edge resolver picks them up.
    for iface in blk.interfaces:
        edges.append(
            CanvasEdgeSpec(
                source=iface.end_a,
                target=iface.end_b,
                edge_type="anchored",
                label=iface.name,
                data={
                    "marker": "interface-connection",
                    "label": iface.name,
                    "source_ref": _src(iface.source_ref),
                },
            )
        )
    return blk_id


def _emit_requirement(
    req: IrRequirement,
    nodes: list[CanvasNodeSpec],
    index: dict[str, str],
    cursor: _Cursor,
    *,
    package_qname: str,
) -> str:
    qname = join_qname(package_qname, req.short_name)
    rid = new_id()
    rx, ry = cursor.next_xy()
    nodes.append(
        CanvasNodeSpec(
            id=rid,
            node_type="sysml:requirement",
            label=req.short_name,
            x=rx,
            y=ry,
            data={
                "qualified_name": qname,
                "short_name": req.short_name,
                "req_id": req.req_id,
                "subject": req.subject,
                "asserts": list(req.asserts),
                "doc": req.doc,
                "metadata": dict(req.metadata),
                "source_ref": _src(req.source_ref),
            },
        )
    )
    index_register(index, rid, [qname, req.short_name, req.qualified_name])
    return rid


def _src(ref: SourceRef | None) -> dict | None:
    if ref is None:
        return None
    out = ref.model_dump()
    if all(out.get(k) is None for k in ("file", "line", "col")):
        return None
    return out


__all__ = ["SysmlCanvasMapper"]
