from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    top_k: int
    hit: bool
    rank: int | None  # 1-based rank of first hit


def first_hit_rank(
    predicted: Sequence[str],
    expected: Iterable[str],
) -> int | None:
    expected_set = {e for e in expected if e}
    if not expected_set:
        return None
    for idx, item in enumerate(predicted, start=1):
        if item in expected_set:
            return idx
    return None


def recall_at_k(results: Sequence[RetrievalCaseResult]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.hit) / len(results)


def mrr(results: Sequence[RetrievalCaseResult]) -> float:
    if not results:
        return 0.0
    total = 0.0
    for r in results:
        if r.rank:
            total += 1.0 / r.rank
    return total / len(results)

