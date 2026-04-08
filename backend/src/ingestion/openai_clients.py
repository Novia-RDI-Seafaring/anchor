"""Concrete OpenAI implementations of the silver/gold ingestion clients.

Kept in its own module so the rest of `ingestion/` doesn't pay the openai
import cost just to type-check. Tests use mock clients and never touch this
file.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI


_PAGE_MD_SYSTEM_PROMPT = """\
You are converting ONE page of a technical product PDF into clean, faithful
markdown. You receive:

1. An image of the page (authoritative — what the document actually shows).
2. A deterministic markdown extraction (good for plain text, often a mess for
   tables and charts — use it as a hint, not as ground truth).
3. The list of docling text items on the page, each with its label and text
   (use these to ground numbers, model names, units, and labels precisely).

Your job: produce a single markdown document that a reader can use as a
faithful, well-structured representation of this page.

Rules:
- NEVER invent values. Every number, unit, model name, and parameter must
  come from the image or the docling items.
- Headings: use `#` only for the document title (rare, mostly p1). Use `##`
  for top-level page sections, `###` for sub-blocks.
- Tables: use GitHub-flavored markdown tables. Group related columns logically;
  if the page has a 4-column block that is really two 2-column spec cards
  side-by-side (e.g. 50 Hz | 60 Hz), render them as TWO separate tables with
  `### LKH-X, 50 Hz` / `### LKH-X, 60 Hz` headings, NOT one wide table.
- Charts and figures: do NOT try to transcribe axis ticks. Instead emit a
  short structured block:
      ### Figure: <what it is>
      - **Type:** chart | diagram | photo | schematic
      - **Axes:** <x label> vs <y label> (if a chart)
      - **Series / labels:** <e.g. A=132, B=120, …>
      - **Range:** <x min–max, y min–max> (if a chart)
      - **Notes:** <anything load-bearing in the caption>
  Keep this block tight — 5–8 lines is plenty.
- Spec / property blocks (label: value): render as a markdown table with
  `Property | Value` headers, OR as a definition list — pick whichever reads
  better for the block.
- Notes / warnings (e.g. "DO NOT FORGET THE SAFETY FACTOR"): render as a
  blockquote `> ...`.
- Preserve the original ordering top-to-bottom on the page.
- Output ONLY the markdown — no preamble, no closing remarks, no code fences
  around the whole document.
"""


@dataclass
class OpenAIPageMdPolisher:
    """Vision-LLM page-md polisher backed by the OpenAI Chat Completions API.

    Implements the `PageMdPolisherClient` Protocol from `silver.py`.
    """

    model: str = ""  # if empty, the call-site model wins
    api_key: str | None = None
    _client: OpenAI = field(init=False)

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.api_key or os.environ.get("OPENAI_API_KEY"))

    def polish_page(
        self,
        *,
        page_image: Path,
        page_no: int,
        deterministic_md: str,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> str:
        if not page_image.exists():
            raise FileNotFoundError(f"page image missing: {page_image}")

        b64 = base64.b64encode(page_image.read_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        items_blob = "\n".join(
            f"- [{it.get('label', '?')}] {(it.get('text') or '').strip()}"
            for it in docling_items
            if (it.get("text") or "").strip()
        )[:8000]  # keep prompt bounded

        user_text = (
            f"Page {page_no} of the document.\n\n"
            f"Deterministic markdown extraction (rough seed):\n"
            f"```markdown\n{deterministic_md.strip() or '(empty)'}\n```\n\n"
            f"Docling text items on this page (label + text):\n"
            f"{items_blob or '(none)'}\n\n"
            "Now produce the clean markdown for this page following the rules."
        )

        chosen_model = self.model or model
        response = self._client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": _PAGE_MD_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        text = response.choices[0].message.content or ""
        return text.strip() + "\n"


_REGION_SYSTEM_PROMPT = """\
You are segmenting ONE page of a technical product PDF into semantic REGIONS.

A region is a logically self-contained visual block on the page: a spec
table, a chart, a diagram, a titled narrative paragraph, a caption, etc.

You receive the page image and the docling text items on the page (label +
text + bbox). Your job is to list the regions in reading order.

For each region return an object with:
  - id:       short stable id like "r1", "r2", …
  - kind:     one of: chart | spec_block | table | figure | diagram | text | caption
  - title:    short human label ("Max inlet pressure", "Performance curves, 50 Hz")
  - description: one sentence about what the region contains
  - bbox:     approximate [left, top, right, bottom] in docling BOTTOMLEFT
              coordinates (top > bottom). Copy the union of the docling
              items that make up the region — do NOT guess pixels.
  - tags:     zero or more short lowercase keywords
  - entities: zero or more product/model identifiers present in the region
              (e.g. ["LKH-5", "LKH-10"]) — empty list if none.

Return ONLY a JSON object of the form:
  { "regions": [ {...}, {...} ] }
No prose, no code fences.
"""


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse: strip code fences, find the outermost JSON object."""
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
    raise ValueError(f"no JSON object found in model output: {text[:200]!r}")


@dataclass
class OpenAIRegionExtractor:
    """Vision-LLM region extractor backed by OpenAI Chat Completions.

    Implements `RegionExtractorClient` from `gold.py`.
    """

    model: str = ""
    api_key: str | None = None
    _client: OpenAI = field(init=False)

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.api_key or os.environ.get("OPENAI_API_KEY"))

    def extract_page(
        self,
        *,
        page_image: Path,
        page_no: int,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        if not page_image.exists():
            raise FileNotFoundError(f"page image missing: {page_image}")

        b64 = base64.b64encode(page_image.read_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        items_blob = "\n".join(
            f"- [{it.get('label', '?')}] bbox={it.get('bbox')} {(it.get('text') or '').strip()}"
            for it in docling_items
            if (it.get("text") or "").strip() or it.get("label") in {"table", "picture"}
        )[:10000]

        user_text = (
            f"Page {page_no}. Segment into semantic regions per the rules.\n\n"
            f"Docling items on this page (label + bbox + text):\n"
            f"{items_blob or '(none)'}\n\n"
            "Return JSON: { \"regions\": [...] }"
        )

        chosen_model = self.model or model
        response = self._client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": _REGION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        data = _extract_json(text)
        regions = data.get("regions") or []
        if not isinstance(regions, list):
            raise ValueError(f"expected 'regions' list, got: {type(regions).__name__}")
        return regions
