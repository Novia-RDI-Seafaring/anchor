"""Pre-computed Q&A index — generates all answerable queries from gold regions.

Each query template is embedded once and tagged with per-entity answers. At
search time: embed user input → nearest neighbor → instant answer + region ref.

Shape of the index:
    [
        {
            "id": "q-p2-r5-1",
            "query": "What is the max inlet pressure?",
            "topic": "operating_data",
            "region_id": "p2-r5",
            "doc_slug": "sample-pump-datasheet",
            "page": 2,
            "answers": {
                "SP-5": "600 kPa (6 bar)",
                "SP-10 - 70": "1000 kPa (10 bar)",
                ...
            },
            "global_answer": null,          // for non-entity-specific questions
            "vector": [0.012, -0.034, ...]  // text-embedding-3-large
        }
    ]

When `answers` has entries, the question is entity-scoped. When only
`global_answer` is set, the answer applies to the whole document/product.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_QUERY_MODEL = "gpt-5.4"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"

_QUERY_GENERATION_PROMPT = """\
You are generating a Q&A index from a region of a technical product document.

You receive:
1. The region metadata (kind, title, description, entities, tags).
2. The region markdown content (if available).
3. The polished page markdown for context.

Your job: produce ALL natural-language questions that can be answered from
this region's data. Think like an engineer searching for specs.

Rules:
- Each question should be a short, natural search query (not a full sentence).
  Examples: "max inlet pressure", "motor speed range", "pump dimensions",
  "product wetted materials", "shaft seal water consumption".
- For questions where the answer varies by entity (model/variant), list the
  per-entity answers in `answers: { "SP-5": "...", "SP-10": "..." }`.
  Leave `global_answer` as null.
- For questions with a single answer (same for all models), put the answer
  in `global_answer` and leave `answers` as {}.
- Every answer must be a direct, concise value from the data. No invented info.
- Include unit-aware variations: "max inlet pressure in bar", "in kPa", etc.
  only if the source actually provides multiple units.
- Keep questions short — they'll be matched against user search input.
- Generate 3–15 questions per region depending on data density. Sparse regions
  (captions, logos) may yield 0.

Return ONLY a JSON object:
{ "queries": [
    { "query": "...", "answers": { "Entity1": "val", ... }, "global_answer": null },
    { "query": "...", "answers": {}, "global_answer": "..." },
    ...
]}
No prose, no code fences.
"""


def _extract_json(text: str) -> dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"no JSON in model output: {text[:200]!r}")


def generate_queries_for_region(
    region: dict[str, Any],
    page_md: str,
    *,
    model: str = DEFAULT_QUERY_MODEL,
) -> list[dict[str, Any]]:
    """Ask an LLM to generate Q&A pairs for a single region."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    region_info = (
        f"Kind: {region.get('kind', '?')}\n"
        f"Title: {region.get('title', '?')}\n"
        f"Description: {region.get('description', '')}\n"
        f"Entities: {region.get('entities', [])}\n"
        f"Tags: {region.get('tags', [])}\n"
    )
    region_md = region.get("markdown") or ""

    user_text = (
        f"Region metadata:\n{region_info}\n"
        f"Region markdown:\n{region_md[:3000] or '(none)'}\n\n"
        f"Page markdown (context):\n{page_md[:4000]}\n\n"
        "Generate the Q&A index for this region."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _QUERY_GENERATION_PROMPT},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or "{}"
    data = _extract_json(text)
    return data.get("queries") or []


def build_query_index(
    gold_dir: Path,
    silver_dir: Path,
    *,
    model: str = DEFAULT_QUERY_MODEL,
) -> list[dict[str, Any]]:
    """Generate query templates for all gold regions across all documents.

    Returns a list of query entries (without vectors — embed separately).
    """
    entries: list[dict[str, Any]] = []

    for slug_dir in sorted(gold_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        pages_dir = slug_dir / "pages"
        if not pages_dir.is_dir():
            continue

        slug = slug_dir.name
        silver_pages = silver_dir / slug / "pages"

        for region_file in sorted(pages_dir.glob("*.regions.json")):
            try:
                data = json.loads(region_file.read_text())
            except Exception:
                continue

            page_no = data.get("page", 0)
            page_md = ""
            md_path = silver_pages / f"{page_no}.md"
            if md_path.exists():
                page_md = md_path.read_text(encoding="utf-8")

            for region in data.get("regions", []):
                rid = region.get("id", "")
                kind = region.get("kind", "")

                # Skip low-value regions
                if kind in ("caption",) and not region.get("markdown"):
                    continue

                try:
                    queries = generate_queries_for_region(region, page_md, model=model)
                except Exception as e:
                    logger.warning("query gen failed for %s/%s: %s", slug, rid, e)
                    continue

                for i, q in enumerate(queries):
                    entries.append({
                        "id": f"q-{rid}-{i + 1}",
                        "query": q.get("query", ""),
                        "topic": _infer_topic(region),
                        "region_id": rid,
                        "doc_slug": slug,
                        "page": page_no,
                        "answers": q.get("answers") or {},
                        "global_answer": q.get("global_answer"),
                        "svg": (region.get("crops") or {}).get("svg"),
                        "png": (region.get("crops") or {}).get("png"),
                    })

    logger.info("query_index: generated %d query templates", len(entries))
    return entries


def embed_query_index(
    entries: list[dict[str, Any]],
    *,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 100,
) -> list[dict[str, Any]]:
    """Add embedding vectors to query entries."""
    from openai import OpenAI

    if not entries:
        return entries

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        texts = [e["query"] for e in batch]
        response = client.embeddings.create(model=embedding_model, input=texts)
        for entry, emb in zip(batch, response.data):
            entry["vector"] = emb.embedding

    return entries


def build_and_save(
    data_dir: Path,
    *,
    model: str = DEFAULT_QUERY_MODEL,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Path:
    """Full pipeline: generate queries → embed → write to disk."""
    gold_dir = data_dir / "gold"
    silver_dir = data_dir / "silver"

    entries = build_query_index(gold_dir, silver_dir, model=model)
    entries = embed_query_index(entries, embedding_model=embedding_model)

    out = data_dir / "query_index.json"
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("query_index: wrote %d entries to %s", len(entries), out)
    return out


def _infer_topic(region: dict[str, Any]) -> str:
    """Quick topic from region kind."""
    kind = region.get("kind", "")
    mapping = {
        "chart": "performance",
        "spec_block": "specifications",
        "table": "specifications",
        "diagram": "dimensions",
        "figure": "figures",
    }
    return mapping.get(kind, "general")


# ── Search (used at runtime) ───────────────────────────────────────────────


def load_query_index(data_dir: Path) -> list[dict[str, Any]]:
    """Load the pre-built query index from disk."""
    path = data_dir / "query_index.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def search_queries(
    index: list[dict[str, Any]],
    query_vector: list[float],
    *,
    top_k: int = 10,
    entity_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Find the best matching pre-computed queries by cosine similarity.

    Returns top_k entries sorted by score, optionally filtered to queries
    that have an answer for a specific entity.
    """
    import math

    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in index:
        vec = entry.get("vector")
        if not vec:
            continue

        # Entity filter: skip entries that don't mention the entity
        if entity_filter:
            answers = entry.get("answers") or {}
            has_entity = any(
                entity_filter.lower() in k.lower() for k in answers
            )
            if not has_entity and not entry.get("global_answer"):
                continue

        score = _cosine(query_vector, vec)
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, entry in scored[:top_k]:
        result = {
            "id": entry["id"],
            "query": entry["query"],
            "score": round(score, 4),
            "region_id": entry["region_id"],
            "doc_slug": entry["doc_slug"],
            "page": entry["page"],
            "topic": entry.get("topic"),
            "svg": entry.get("svg"),
            "png": entry.get("png"),
        }
        if entity_filter:
            answers = entry.get("answers") or {}
            for k, v in answers.items():
                if entity_filter.lower() in k.lower():
                    result["answer"] = v
                    result["entity"] = k
                    break
            if "answer" not in result and entry.get("global_answer"):
                result["answer"] = entry["global_answer"]
        else:
            result["answers"] = entry.get("answers") or {}
            result["global_answer"] = entry.get("global_answer")

        results.append(result)

    return results
