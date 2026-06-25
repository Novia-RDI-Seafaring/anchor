"""Regression tests for the operating-point regex in synopsis._OPERATING_POINT_RE.

Covers:
- Normal inputs that must match and capture the right substring.
- Inputs that must NOT match (no Hz or no rpm).
- Adversarial ReDoS input: must complete in under 1 second.
"""
from __future__ import annotations

import time

import pytest

from anchor.extensions.anchor_pdfs.core.synopsis import _OPERATING_POINT_RE


# ---------------------------------------------------------------------------
# Matching cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_fragment", [
    ("50 Hz at 2900 rpm", "50 Hz at 2900 rpm"),
    ("60Hz -> 3500 rpm", "60Hz -> 3500 rpm"),
    ("runs 50 Hz / 2900 rpm continuous", "50 Hz / 2900 rpm"),
    ("0Hz 0 rpm", "0Hz 0 rpm"),
    ("operating at 50Hz motor speed 2900 rpm nominal", "50Hz motor speed 2900 rpm"),
])
def test_operating_point_matches(text: str, expected_fragment: str) -> None:
    m = _OPERATING_POINT_RE.search(text)
    assert m is not None, f"Expected match in {text!r}"
    assert m.group(1) == expected_fragment, f"Wrong capture: {m.group(1)!r}"


# ---------------------------------------------------------------------------
# Non-matching cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "50 Hz only no rpm here",
    "no frequency here 2900 rpm",
    "no numbers at all",
    "",
])
def test_operating_point_no_match(text: str) -> None:
    m = _OPERATING_POINT_RE.search(text)
    assert m is None, f"Unexpected match {m!r} in {text!r}"


# ---------------------------------------------------------------------------
# ReDoS safety: adversarial input must complete in under 1 second
# ---------------------------------------------------------------------------

def test_operating_point_adversarial_is_instant() -> None:
    """'0Hz' followed by many digits triggered polynomial backtracking in the
    original unbounded r'(\\d+\\s*Hz[^.,;]*?\\d+\\s*rpm)'.  The fixed pattern
    uses bounded quantifiers and excludes digits from the gap character class,
    making this O(n) rather than O(n^2).
    """
    adversarial = "0Hz" + "0" * 100_000
    t0 = time.perf_counter()
    m = _OPERATING_POINT_RE.search(adversarial)
    elapsed = time.perf_counter() - t0
    assert m is None
    assert elapsed < 1.0, (
        f"ReDoS detected: adversarial input took {elapsed:.3f}s (limit 1s)"
    )
