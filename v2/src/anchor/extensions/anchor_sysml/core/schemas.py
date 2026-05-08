"""SysML v2 IR + canvas-mapping data contracts.

Two layers live here:

1. **IR** — the structured form produced by the parser. One pydantic model
   per construct we care about (block, requirement, package, port, …).
   Pure data, no rendering decisions.

2. **Canvas specs** — what the mapper emits. ``CanvasNodeSpec`` /
   ``CanvasEdgeSpec`` mirror the kwargs accepted by
   ``WorkspaceService.add_node`` / ``add_edge`` so the service layer can
   forward them with no translation.

The frontend agent reads ``CanvasNodeSpec.data`` shapes verbatim — that
contract (block / requirement / package data + edge ``marker``) is the
external API of this extension.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Source-ref + diagnostics ─────────────────────────────────────────────


class SourceRef(BaseModel):
    """Position in the source SysML text. ``file`` may be None for inline."""

    kind: Literal["sysml-text"] = "sysml-text"
    file: str | None = None
    line: int | None = None
    col: int | None = None


class Diagnostic(BaseModel):
    """Non-fatal parser/mapper warning surfaced back to the caller."""

    level: Literal["info", "warning", "error"] = "warning"
    line: int | None = None
    col: int | None = None
    message: str


# ── IR primitives ────────────────────────────────────────────────────────


PortDirection = Literal["in", "out", "inout"]


class IrAttribute(BaseModel):
    name: str
    type: str | None = None
    default: str | None = None  # serialized literal, e.g. "750" or "true"


class IrPort(BaseModel):
    name: str
    direction: PortDirection | None = None
    type: str | None = None


class IrPart(BaseModel):
    """A nested part declared inside a block."""

    name: str
    type: str | None = None
    is_ref: bool = False  # `ref part` keyword


class IrInterface(BaseModel):
    """An ``interface … connect a to b`` connection inside a block."""

    name: str
    type: str | None = None
    end_a: str  # qualified path of one endpoint, e.g. "hull.highSlot1"
    end_b: str
    source_ref: SourceRef = Field(default_factory=SourceRef)


# ── IR top-level constructs ──────────────────────────────────────────────

BlockKind = Literal["block-def", "block-usage"]


class IrBlock(BaseModel):
    """A SysML `part def` (definition) or `part` (usage)."""

    kind: BlockKind
    short_name: str
    qualified_name: str
    specializes: list[str] = Field(default_factory=list)   # `:>` and `:>>`
    redefines: list[str] = Field(default_factory=list)     # `:>>`
    subsets: list[str] = Field(default_factory=list)       # `::>`
    typed_as: str | None = None  # `name : Type`
    attributes: list[IrAttribute] = Field(default_factory=list)
    ports: list[IrPort] = Field(default_factory=list)
    parts: list[IrPart] = Field(default_factory=list)
    interfaces: list[IrInterface] = Field(default_factory=list)
    doc: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_ref: SourceRef = Field(default_factory=SourceRef)


class IrRequirement(BaseModel):
    short_name: str
    qualified_name: str
    req_id: str | None = None
    is_def: bool = False          # `requirement def` vs `requirement`
    subject: str | None = None    # text of the subject clause
    asserts: list[str] = Field(default_factory=list)
    doc: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_ref: SourceRef = Field(default_factory=SourceRef)


class IrSatisfy(BaseModel):
    """`satisfy <requirement> by <part>` statement at package level."""

    requirement: str  # qualified name
    by: str           # qualified name of the satisfying part
    source_ref: SourceRef = Field(default_factory=SourceRef)


class IrPackage(BaseModel):
    qualified_name: str
    short_name: str
    imports: list[str] = Field(default_factory=list)
    blocks: list[IrBlock] = Field(default_factory=list)
    requirements: list[IrRequirement] = Field(default_factory=list)
    satisfies: list[IrSatisfy] = Field(default_factory=list)
    sub_packages: list["IrPackage"] = Field(default_factory=list)
    doc: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_ref: SourceRef = Field(default_factory=SourceRef)


class IrModel(BaseModel):
    """Top-level IR — the result of parsing one .sysml file."""

    packages: list[IrPackage] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


# ── Canvas-ready specs (mapper output) ───────────────────────────────────


EdgeMarker = Literal[
    "inheritance",
    "redefinition",
    "subset",
    "composition",
    "interface-connection",
    "satisfy",
    "subject",
    "association",
]


class CanvasNodeSpec(BaseModel):
    """One ``WorkspaceService.add_node`` call, pre-shaped."""

    id: str
    node_type: str  # e.g. "sysml:block", "sysml:requirement", "sysml:package"
    label: str = ""
    x: float = 0
    y: float = 0
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasEdgeSpec(BaseModel):
    """One ``WorkspaceService.add_edge`` call, pre-shaped."""

    source: str
    target: str
    edge_type: Literal["floating", "anchored"] = "floating"
    label: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class CanvasBatch(BaseModel):
    """Mapper output — a batch of node + edge specs ready for the service."""

    nodes: list[CanvasNodeSpec] = Field(default_factory=list)
    edges: list[CanvasEdgeSpec] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


# ── Service result ───────────────────────────────────────────────────────


class SysmlRenderResult(BaseModel):
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
