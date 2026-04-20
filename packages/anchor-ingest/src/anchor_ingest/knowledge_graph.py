"""Knowledge graph — cross-document entity/topic/region graph.

Built deterministically from gold region files. No LLM needed.

The graph connects:
    - Entities (product models like LKH-5, LKH-10) → regions that mention them
    - Topics (inferred from region kind + title) → regions about that topic
    - Documents → their regions

This enables queries like "everything about LKH-5" or "all performance curves"
across all documents.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RegionRef:
    """Lightweight pointer to a gold region."""
    region_id: str
    doc_slug: str
    page: int
    kind: str
    title: str
    description: str
    entities: list[str]
    tags: list[str]
    svg: str | None = None
    png: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "region_id": self.region_id,
            "doc_slug": self.doc_slug,
            "page": self.page,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
        }
        if self.entities:
            d["entities"] = self.entities
        if self.tags:
            d["tags"] = self.tags
        if self.svg:
            d["svg"] = self.svg
        if self.png:
            d["png"] = self.png
        return d


@dataclass
class KnowledgeGraph:
    """In-memory cross-document graph."""
    entities: dict[str, list[RegionRef]] = field(default_factory=dict)
    topics: dict[str, list[RegionRef]] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    all_regions: list[RegionRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": {
                k: [r.to_dict() for r in refs]
                for k, refs in sorted(self.entities.items())
            },
            "topics": {
                k: [r.to_dict() for r in refs]
                for k, refs in sorted(self.topics.items())
            },
            "documents": self.documents,
            "stats": {
                "entity_count": len(self.entities),
                "topic_count": len(self.topics),
                "document_count": len(self.documents),
                "region_count": len(self.all_regions),
            },
        }

    def find_by_entity(self, entity: str) -> list[RegionRef]:
        """Find all regions mentioning an entity (case-insensitive)."""
        key = entity.strip().lower()
        for k, refs in self.entities.items():
            if k.lower() == key:
                return refs
        return []

    def find_by_topic(self, topic: str) -> list[RegionRef]:
        """Find all regions matching a topic (case-insensitive)."""
        key = topic.strip().lower()
        for k, refs in self.topics.items():
            if k.lower() == key:
                return refs
        return []

    def find_by_query(self, query: str) -> list[RegionRef]:
        """Simple keyword search across region titles and descriptions."""
        terms = query.lower().split()
        results: list[RegionRef] = []
        for ref in self.all_regions:
            text = f"{ref.title} {ref.description} {' '.join(ref.entities)}".lower()
            if all(t in text for t in terms):
                results.append(ref)
        return results


# ── Topic inference ─────────────────────────────────────────────────────────

# Map region kind + title patterns → topic labels
_TOPIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"performance|curve|characteristic", re.I), "performance"),
    (re.compile(r"dimension|measure|size", re.I), "dimensions"),
    (re.compile(r"material|steel|elastomer|seal", re.I), "materials"),
    (re.compile(r"motor|IEC|pole|kW", re.I), "motor"),
    (re.compile(r"connection|clamp|union|fitting", re.I), "connections"),
    (re.compile(r"temperature|pressure|operating|inlet", re.I), "operating_data"),
    (re.compile(r"warranty|safety|warning|note", re.I), "warranty_safety"),
    (re.compile(r"technical data|spec|specification", re.I), "specifications"),
    (re.compile(r"overview|summary|introduction|description", re.I), "overview"),
]

_KIND_TO_TOPIC: dict[str, str] = {
    "chart": "performance",
    "diagram": "dimensions",
    "figure": "figures",
}


def _infer_topics(ref: RegionRef) -> list[str]:
    """Infer topic labels from region kind, title, and description."""
    topics: list[str] = []
    text = f"{ref.title} {ref.description}"

    # Kind-based default
    if ref.kind in _KIND_TO_TOPIC:
        topics.append(_KIND_TO_TOPIC[ref.kind])

    # Pattern-based
    for pattern, topic in _TOPIC_PATTERNS:
        if pattern.search(text):
            if topic not in topics:
                topics.append(topic)

    return topics or ["general"]


# ── Builder ─────────────────────────────────────────────────────────────────


def build_knowledge_graph(gold_dir: Path) -> KnowledgeGraph:
    """Build a knowledge graph from all gold region files.

    Scans `gold_dir/<slug>/pages/*.regions.json` for every document slug.
    """
    graph = KnowledgeGraph()

    for slug_dir in sorted(gold_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        pages_dir = slug_dir / "pages"
        if not pages_dir.is_dir():
            continue

        slug = slug_dir.name
        region_count = 0

        for region_file in sorted(pages_dir.glob("*.regions.json")):
            try:
                data = json.loads(region_file.read_text())
            except Exception:
                continue

            for region in data.get("regions", []):
                crops = region.get("crops") or {}
                ref = RegionRef(
                    region_id=region.get("id", ""),
                    doc_slug=slug,
                    page=region.get("page", 0),
                    kind=region.get("kind", "text"),
                    title=region.get("title", ""),
                    description=region.get("description", ""),
                    entities=region.get("entities", []),
                    tags=region.get("tags", []),
                    svg=crops.get("svg"),
                    png=crops.get("png"),
                )
                graph.all_regions.append(ref)
                region_count += 1

                # Entity edges
                for entity in ref.entities:
                    graph.entities.setdefault(entity, []).append(ref)

                # Topic edges
                for topic in _infer_topics(ref):
                    graph.topics.setdefault(topic, []).append(ref)

        if region_count > 0:
            graph.documents[slug] = {
                "slug": slug,
                "region_count": region_count,
            }

    return graph


def build_and_save(data_dir: Path) -> Path:
    """Build the knowledge graph and write it to `data_dir/knowledge_graph.json`."""
    gold_dir = data_dir / "gold"
    graph = build_knowledge_graph(gold_dir)
    out = data_dir / "knowledge_graph.json"
    out.write_text(json.dumps(graph.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return out
