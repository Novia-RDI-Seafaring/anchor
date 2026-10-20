"""Quotes: words a citation highlights, placed when saved."""
from __future__ import annotations

import asyncio

from anchor.extensions.anchor_pdfs.core.quotes import format_quote, parse_quote, place_quotes

TEXT = "Temperature range -10 to +140 °C (EPDM)\nSeals: EPDM or FKM\n"
BOXES = {
    "EPDM": [[170, 150, 200, 160], [250, 480, 280, 490]],
    "+140 °C (EPDM)": [[120, 150, 202, 160]],
    "-10": [[100, 150, 115, 160]],
}


async def _locate(page, query, clip):
    return BOXES.get(query, [])


async def _read(page, clip):
    return TEXT


def _place(quotes):
    return asyncio.run(place_quotes(quotes, page=2, clip=None, locate=_locate, read=_read))


def test_link_grammar_round_trips():
    for text, quote in [
        ("EPDM", {"exact": "EPDM"}),
        ("+140 °C (-,EPDM,-)", {"exact": "EPDM", "prefix": "+140 °C (", "suffix": ")"}),
        ("6,3 bar", {"exact": "6,3 bar"}),
    ]:
        assert parse_quote(text) == quote
        assert format_quote(quote) == text


def test_a_word_printed_once_is_placed():
    assert _place([{"exact": "-10"}]) == [{"exact": "-10", "boxes": [[100, 150, 115, 160]]}]


def test_a_word_printed_twice_asks_which_and_shows_both():
    [quote] = _place(["EPDM"])
    assert quote["problem"] == "ambiguous"
    assert len(quote["candidates"]) == 2


def test_the_words_around_pick_the_one_meant():
    [quote] = _place(["+140 °C (-,EPDM,-)"])
    assert quote["boxes"] == [[170, 150, 200, 160]]


def test_words_not_on_the_page_say_what_is_there():
    [quote] = _place([{"exact": "m³/h"}])
    assert quote["problem"] == "not_found"
    assert "Temperature range" in quote["text_here"]


def test_the_cell_holding_a_quote_is_found():
    from anchor.extensions.anchor_pdfs.core.node_data import _cell_holding

    cells = [
        {"row": 0, "col": 0, "bbox": [10, 10, 50, 20]},
        {"row": 0, "col": 1, "bbox": [50, 10, 120, 20]},
        {"row": 1, "col": 1, "bbox": [50, 20, 120, 30]},
    ]
    assert _cell_holding(cells, [90, 12, 110, 18]) == {"row": 0, "col": 1}
    assert _cell_holding(cells, [200, 12, 210, 18]) is None
