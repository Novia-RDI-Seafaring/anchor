"""Ingest event types — pipeline progress and outcomes.

Cross-workspace; published on the global EventBus channel rather than the
per-workspace channel. `IngestProgress` is high-frequency and is NEVER
persisted to events.jsonl — it lives only on the bus for live updates.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

IngestEventType = Literal[
    "DocBronzed",
    "DocSilvered",
    "DocPolished",
    "DocGoldExtracted",
    "DocIngested",
    "DocIngestFailed",
    "IngestProgress",
]


class DocBronzed(BaseModel):
    type: Literal["DocBronzed"] = "DocBronzed"
    slug: str
    bronze_path: str


class DocSilvered(BaseModel):
    type: Literal["DocSilvered"] = "DocSilvered"
    slug: str
    page_count: int


class DocPolished(BaseModel):
    type: Literal["DocPolished"] = "DocPolished"
    slug: str
    polished_pages: list[int]


class DocGoldExtracted(BaseModel):
    type: Literal["DocGoldExtracted"] = "DocGoldExtracted"
    slug: str
    region_count: int


class DocIngested(BaseModel):
    type: Literal["DocIngested"] = "DocIngested"
    slug: str
    summary: dict[str, Any]


class DocIngestFailed(BaseModel):
    type: Literal["DocIngestFailed"] = "DocIngestFailed"
    slug: str
    stage: str
    error: str


class IngestProgress(BaseModel):
    """High-frequency. Bus-only; never persisted."""

    type: Literal["IngestProgress"] = "IngestProgress"
    slug: str
    stage: str
    current: int
    total: int
