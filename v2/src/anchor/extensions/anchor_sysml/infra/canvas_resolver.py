"""Cross-reference resolution for the IR → canvas mapper.

Held in its own module so the mapper's main file stays focused on emission.
The resolver walks the IR a second time after node ids are known, and
appends inheritance / satisfy / subject edges to the canvas batch.
"""
from __future__ import annotations

from typing import Iterable

from anchor.extensions.anchor_sysml.core.schemas import (
    CanvasEdgeSpec,
    Diagnostic,
    IrModel,
    IrPackage,
    SourceRef,
)


def resolve_inheritance_edges(
    ir: IrModel,
    index: dict[str, str],
    edges: list[CanvasEdgeSpec],
) -> None:
    """Walk every block and emit specialise / redefine / subset edges."""
    for pkg in iter_packages(ir):
        for blk in pkg.blocks:
            src_id = index.get(blk.short_name)
            if src_id is None:
                continue
            for ref, marker in (
                *((r, "inheritance") for r in blk.specializes),
                *((r, "redefinition") for r in blk.redefines),
                *((r, "subset") for r in blk.subsets),
            ):
                target = resolve_name(index, ref)
                if target is None:
                    continue
                edges.append(
                    CanvasEdgeSpec(
                        source=src_id,
                        target=target,
                        edge_type="floating",
                        data={"marker": marker, "label": "", "source_ref": _src(blk.source_ref)},
                    )
                )


def resolve_satisfy_edges(
    ir: IrModel,
    index: dict[str, str],
    edges: list[CanvasEdgeSpec],
    diagnostics: list[Diagnostic],
) -> None:
    for pkg in iter_packages(ir):
        for sat in pkg.satisfies:
            src = resolve_name(index, sat.by)
            tgt = resolve_name(index, sat.requirement)
            if src is None or tgt is None:
                diagnostics.append(
                    Diagnostic(
                        level="warning",
                        line=sat.source_ref.line,
                        col=sat.source_ref.col,
                        message=f"satisfy edge unresolved: {sat.by!r} → {sat.requirement!r}",
                    )
                )
                continue
            edges.append(
                CanvasEdgeSpec(
                    source=src,
                    target=tgt,
                    edge_type="floating",
                    data={"marker": "satisfy", "label": "satisfy", "source_ref": _src(sat.source_ref)},
                )
            )


def resolve_subject_edges(
    ir: IrModel,
    index: dict[str, str],
    edges: list[CanvasEdgeSpec],
    diagnostics: list[Diagnostic],
) -> None:
    """Emit a `subject` edge from a requirement to the named subject part."""
    for pkg in iter_packages(ir):
        for req in pkg.requirements:
            if not req.subject:
                continue
            req_id = index.get(req.short_name)
            if req_id is None:
                continue
            target_name = last_qname_segment(req.subject)
            target = resolve_name(index, target_name)
            if target is None:
                diagnostics.append(
                    Diagnostic(
                        level="info",
                        line=req.source_ref.line,
                        col=req.source_ref.col,
                        message=f"subject reference unresolved: {req.subject!r}",
                    )
                )
                continue
            edges.append(
                CanvasEdgeSpec(
                    source=req_id,
                    target=target,
                    edge_type="floating",
                    data={"marker": "subject", "label": "subject", "source_ref": _src(req.source_ref)},
                )
            )


# ── Helpers ──────────────────────────────────────────────────────────────


def iter_packages(ir: IrModel) -> Iterable[IrPackage]:
    for pkg in ir.packages:
        yield pkg
        yield from _flatten(pkg.sub_packages)


def _flatten(pkgs: list[IrPackage]) -> Iterable[IrPackage]:
    for p in pkgs:
        yield p
        yield from _flatten(p.sub_packages)


def join_qname(prefix: str | None, leaf: str) -> str:
    if not prefix:
        return leaf
    return f"{prefix}::{leaf}"


def index_register(index: dict[str, str], node_id: str, names: list[str]) -> None:
    for n in names:
        if not n:
            continue
        index.setdefault(n, node_id)


def resolve_name(index: dict[str, str], ref: str) -> str | None:
    """Try the qualified name first, then fall back to the last segment."""
    if not ref:
        return None
    if ref in index:
        return index[ref]
    last = last_qname_segment(ref)
    return index.get(last)


def last_qname_segment(qname: str) -> str:
    """Strip access operators and qualifier prefixes; return the trailing
    identifier after dotted-path resolution."""
    candidates = qname.replace("::", " ").split()
    skip = {":>", ":>>", "::>", "by", "satisfy", "subject"}
    for tok in reversed(candidates):
        if tok in skip:
            continue
        return tok.split(".")[-1]
    return qname


def _src(ref: SourceRef | None) -> dict | None:
    if ref is None:
        return None
    out = ref.model_dump()
    if all(out.get(k) is None for k in ("file", "line", "col")):
        return None
    return out


__all__ = [
    "resolve_inheritance_edges",
    "resolve_satisfy_edges",
    "resolve_subject_edges",
    "iter_packages",
    "join_qname",
    "index_register",
    "resolve_name",
    "last_qname_segment",
]
