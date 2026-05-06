"""CAD domain schemas — pure data, no I/O.

Modest scope today: a `CadModel` that records what was ingested (filename,
slug, kind, basic geometry stats) and the parametric/structural shapes
that a fuller implementation will populate. Real parsing of STL/OBJ/STEP
is a follow-on; today the producer is registered, the OIP manifest is
real, and the data contract is defined so consumers can be written
against it before the parser lands.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CadKind = Literal["stl", "obj", "step", "iges", "gltf", "jscad", "openscad", "unknown"]


class CadParameter(BaseModel):
    """A named parameter in a parametric model (JSCAD, OpenSCAD, CadQuery)."""

    name: str
    value: float | int | str | bool
    unit: str | None = None
    description: str = ""
    minimum: float | None = None
    maximum: float | None = None
    default: float | int | str | bool | None = None


class CadPart(BaseModel):
    """One part in an assembly. For non-parametric solids this is the whole model."""

    id: str
    name: str = ""
    kind: Literal["part", "assembly", "feature"] = "part"
    parent_id: str | None = None  # for assembly hierarchy


class CadGeometryStats(BaseModel):
    """Coarse-grained geometry stats — what we can know without a full parser."""

    triangle_count: int | None = None
    vertex_count: int | None = None
    bounding_box: list[float] | None = None  # [xmin, ymin, zmin, xmax, ymax, zmax]
    units: str | None = None  # mm, m, in, ...


class CadModel(BaseModel):
    """An ingested CAD source."""

    slug: str
    filename: str
    kind: CadKind = "unknown"
    title: str = ""
    description: str = ""
    parameters: list[CadParameter] = Field(default_factory=list)
    parts: list[CadPart] = Field(default_factory=list)
    geometry: CadGeometryStats = Field(default_factory=CadGeometryStats)


# ── Source-ref kinds for OIP ────────────────────────────────────────────


class CadParameterRef(BaseModel):
    """SourceRef pointing at a named parameter in a parametric CAD model."""

    kind: Literal["cad-parameter-name"] = "cad-parameter-name"
    cad_slug: str
    parameter_name: str


class CadPartRef(BaseModel):
    """SourceRef pointing at a part in an assembly."""

    kind: Literal["cad-part-id"] = "cad-part-id"
    cad_slug: str
    part_id: str


class CadFeatureRef(BaseModel):
    """SourceRef pointing at a feature (hole, fillet, pocket) in a part."""

    kind: Literal["cad-feature-id"] = "cad-feature-id"
    cad_slug: str
    feature_id: str


# ── Node `data` schemas ─────────────────────────────────────────────────


class CadModelNodeData(BaseModel):
    """Data for a `cad:model` node — a 3D viewport rendering the model."""

    cad_slug: str
    title: str = ""
    parameters: list[str] = Field(default_factory=list)  # parameter names exposed on the node
    view_state: dict[str, float | int | str | bool] = Field(default_factory=dict)
    # view_state can carry: exploded_factor, section_plane, camera, etc.


class CadParameterNodeData(BaseModel):
    """Data for a `cad:parameter` node — a single tunable value."""

    cad_slug: str
    parameter_name: str
    current_value: float | int | str | bool
    unit: str | None = None
