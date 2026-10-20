"""Quotes: the words a citation highlights, the way a reader uses a marker.

A ``source_ref`` says where a value comes from (a page, a region, a cell, a
paragraph). Its ``quotes`` say which words there to light up, one or more:

    {"exact": "EPDM", "prefix": "+140 °C (", "suffix": ")", "page": 2,
     "boxes": [[172.5, 154.7, 201.0, 164.6]]}

``exact`` is the printed text. ``prefix`` / ``suffix`` are the words around
it, given only when ``exact`` occurs more than once, to say which one is
meant: the W3C Web Annotation text-quote selector. ``page`` defaults to the
ref's page. ``boxes`` is where the words sit, filled in when the citation is
saved, so the viewer draws them as they are; a match that wraps a line has a
box per line. A quote that cannot be placed carries ``problem`` instead, with
what the text there actually says, so the writer can correct it.

In a link a quote is one ``quote=`` parameter in the browser's text-fragment
grammar: ``quote=EPDM`` or ``quote=+140 °C (-,EPDM,-)``.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

#: Search ``query`` on ``page`` within ``clip``; page-space rects per line.
Locate = Callable[[int, str, "list[float] | None"], Awaitable[list[list[float]]]]
#: The text on ``page`` within ``clip``.
ReadText = Callable[[int, "list[float] | None"], Awaitable[str]]

MAX_QUOTES = 12
_CONTEXT = 24


def parse_quote(text: str) -> dict[str, str] | None:
    """``prefix-,exact,-suffix`` (each side optional) to a quote."""
    if not isinstance(text, str) or not text.strip():
        return None
    parts = text.split(",")
    prefix = suffix = ""
    if len(parts) > 1 and parts[0].endswith("-"):
        prefix = parts.pop(0)[:-1]
    if len(parts) > 1 and parts[-1].startswith("-"):
        suffix = parts.pop()[1:]
    exact = ",".join(parts)
    if not exact.strip():
        return None
    quote = {"exact": exact}
    if prefix:
        quote["prefix"] = prefix
    if suffix:
        quote["suffix"] = suffix
    return quote


def format_quote(quote: dict[str, Any]) -> str:
    """A quote back to its ``quote=`` text."""
    out = str(quote.get("exact") or "")
    if quote.get("prefix"):
        out = f"{quote['prefix']}-,{out}"
    if quote.get("suffix"):
        out = f"{out},-{quote['suffix']}"
    return out


def _words(text: str) -> str:
    return r"\s*".join(re.escape(part) for part in text.split())


def _phrase(quote: dict[str, Any]) -> re.Pattern[str]:
    exact = _words(str(quote["exact"]))
    prefix = _words(str(quote.get("prefix") or ""))
    suffix = _words(str(quote.get("suffix") or ""))
    body = f"(?P<exact>{exact})"
    if prefix:
        body = f"{prefix}\\s*{body}"
    if suffix:
        body = f"{body}\\s*{suffix}"
    return re.compile(body, re.IGNORECASE)


def _overlaps(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


async def place_quote(
    quote: dict[str, Any], *, page: int, clip: list[float] | None,
    locate: Locate, read: ReadText,
) -> dict[str, Any]:
    """``quote`` with its ``boxes``, or with a ``problem`` saying why not."""
    out = {k: v for k, v in quote.items() if k in ("exact", "prefix", "suffix", "page")}
    if not isinstance(out.get("exact"), str) or not out["exact"].strip():
        return {**out, "problem": "empty"}
    text = await read(page, clip)
    found = list(_phrase(out).finditer(text))
    if len(found) != 1:
        problem = "not_found" if not found else "ambiguous"
        result: dict[str, Any] = {**out, "problem": problem}
        if found:
            # Each occurrence with the words around it: what a prefix or
            # suffix would quote to pick one.
            result["candidates"] = [
                " ".join(text[max(0, m.start() - _CONTEXT):m.end() + _CONTEXT].split())
                for m in found[:5]
            ]
        else:
            result["text_here"] = " ".join(text.split())[:240]
        return result
    match = found[0]
    exact_boxes = await locate(page, " ".join(match.group("exact").split()), clip)
    if out.get("prefix") or out.get("suffix"):
        # The words around pick which occurrence: keep the boxes inside it.
        phrase_boxes = await locate(page, " ".join(match.group(0).split()), clip)
        exact_boxes = [b for b in exact_boxes if any(_overlaps(b, p) for p in phrase_boxes)]
    if not exact_boxes:
        return {**out, "problem": "not_found", "text_here": " ".join(text.split())[:240]}
    return {**out, "boxes": [[round(v, 2) for v in box] for box in exact_boxes]}


async def place_quotes(
    quotes: Any, *, page: int, clip: list[float] | None,
    locate: Locate, read: ReadText,
) -> list[dict[str, Any]]:
    """Place each quote; one on another page searches that whole page."""
    if not isinstance(quotes, list):
        return []
    placed: list[dict[str, Any]] = []
    for raw in quotes[:MAX_QUOTES]:
        quote = parse_quote(raw) if isinstance(raw, str) else raw
        if not isinstance(quote, dict):
            continue
        on = quote.get("page") if type(quote.get("page")) is int else page
        placed.append(await place_quote(
            {**quote, **({"page": on} if on != page else {})},
            page=on, clip=clip if on == page else None, locate=locate, read=read,
        ))
    return placed


def quote_problems(quotes: Any) -> list[dict[str, Any]]:
    """The quotes that could not be placed."""
    return [m for m in quotes if isinstance(m, dict) and m.get("problem")] if isinstance(quotes, list) else []


def text_access(store: Any, renderer: Any, slug: str) -> tuple[Locate, ReadText]:
    """``locate`` and ``read`` over one document's raw PDF.

    A store without an addressable raw PDF finds nothing, so every quote
    reports ``not_found`` rather than failing the citation.
    """
    async def pdf(page: int):
        path = await store.get_raw_pdf_path(slug, page=page)
        return None if path is None or str(path).startswith("memory://") else path

    async def locate(page: int, query: str, clip: list[float] | None) -> list[list[float]]:
        path = await pdf(page)
        return await renderer.locate_text(path, page, query, clip) if path else []

    async def read(page: int, clip: list[float] | None) -> str:
        path = await pdf(page)
        return await renderer.page_text(path, page, clip) if path else ""

    return locate, read
