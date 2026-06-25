"""The operating-point regex in synopsis._extract_extras is linear-time.

The pattern that pulls "50 Hz -> 2900 rpm" out of a chart-region description
must not be ReDoS-prone (CodeQL py/polynomial-redos): a gold-region
description is model-produced text, so an adversarial run of digits between
'Hz' and 'rpm' must not blow up. These tests pin both the correctness (normal
strings still parse) and the bound (adversarial input returns fast).
"""
from __future__ import annotations

import time

from anchor.extensions.anchor_pdfs.core.synopsis import _OPERATING_POINT_RE


def test_matches_normal_operating_point_strings():
    cases = {
        "Performance at 50 Hz and 2900 rpm continuous.": "50 Hz and 2900 rpm",
        "60Hz -> 3500 rpm": "60Hz -> 3500 rpm",
        "runs 50 Hz / 2900 rpm": "50 Hz / 2900 rpm",
    }
    for text, expected in cases.items():
        m = _OPERATING_POINT_RE.search(text)
        assert m is not None
        assert m.group(1) == expected


def test_no_match_when_separator_breaks_the_phrase():
    # A sentence boundary between the two tokens is not an operating point.
    assert _OPERATING_POINT_RE.search("50 Hz. Some other clause about 2900 rpm") is None


def test_adversarial_input_is_linear_not_polynomial():
    # A long run of zeros after "0Hz" that never reaches "rpm": the old
    # unbounded `\d+...\d+` pattern backtracked polynomially here; the bounded
    # pattern returns effectively instantly.
    adversarial = "0Hz" + "0" * 200_000
    start = time.perf_counter()
    assert _OPERATING_POINT_RE.search(adversarial) is None
    assert time.perf_counter() - start < 1.0
