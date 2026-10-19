"""Find the table cell a spec row's value sits in, when the row cites only the table.

A row that names a table region but no cell lights the whole table when the
reader follows its anchor. The cell is usually not in doubt: the row header
names the key and one cell in that row holds the value. This finds it so the
anchor lands on the value, whichever agent wrote the row.

Locating is not verifying. A cell found here says where the value is printed;
whether the claim holds is still the evidence check's verdict, which needs a
certified key/value pair. Anything short of exactly one match leaves the ref
as it was.
"""
from __future__ import annotations

import re
from typing import Any

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[^\W\d_]{2,}")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def locate_cell(cells: Any, key: Any, value: Any) -> dict[str, int] | None:
    """The one ``{row, col}`` whose row header names ``key`` and whose text is ``value``.

    The row header matches when every word of the key appears in it ("Max
    flow" in "Max flow (m3/h)"). The cell matches when its numbers are all
    numbers of the value ("12" in "12 m³/h"). ``None`` unless exactly one cell
    qualifies.
    """
    if not isinstance(cells, list) or not isinstance(key, str) or not isinstance(value, str):
        return None
    key_words, value_numbers = _words(key), _numbers(value)
    if not key_words or not value_numbers:
        return None
    grid = [
        c for c in cells
        if isinstance(c, dict) and type(c.get("row")) is int and type(c.get("col")) is int
        and isinstance(c.get("text"), str)
    ]
    rows = {
        c["row"] for c in grid
        if (c.get("row_header") or c["col"] == 0) and key_words <= _words(c["text"])
    }
    found = [
        c for c in grid
        if c["row"] in rows and not c.get("row_header") and not c.get("column_header")
        and c["col"] != 0 and (numbers := _numbers(c["text"])) and numbers <= value_numbers
    ]
    if len(found) != 1:
        return None
    return {"row": found[0]["row"], "col": found[0]["col"]}
