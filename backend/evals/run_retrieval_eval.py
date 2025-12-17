from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.metrics import RetrievalCaseResult, first_hit_rank, mrr, recall_at_k
from evals.trace_logger import log_event
from src.active_document import set_active_document_id
from src.document_service import get_document_service


@dataclass(frozen=True)
class RetrievalCase:
    id: str
    query: str
    top_k: int = 5
    active_document_id: str | None = None
    expected_document_ids: list[str] = None  # type: ignore[assignment]
    expected_filenames: list[str] = None  # type: ignore[assignment]

    @staticmethod
    def from_json(obj: dict[str, Any]) -> "RetrievalCase":
        return RetrievalCase(
            id=str(obj.get("id") or obj.get("case_id") or ""),
            query=str(obj.get("query") or ""),
            top_k=int(obj.get("top_k") or 5),
            active_document_id=obj.get("active_document_id"),
            expected_document_ids=list(obj.get("expected_document_ids") or []),
            expected_filenames=list(obj.get("expected_filenames") or []),
        )


def load_cases(path: Path) -> list[RetrievalCase]:
    cases: list[RetrievalCase] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(RetrievalCase.from_json(json.loads(line)))
    return cases


async def run_case(case: RetrievalCase, top_k_override: int | None = None) -> RetrievalCaseResult:
    top_k = top_k_override or case.top_k
    set_active_document_id(case.active_document_id)
    service = await get_document_service()
    results = await service.search(case.query, top_k=top_k, document_id=case.active_document_id)

    predicted_doc_ids = [str(r.get("document_id") or "") for r in results]
    predicted_filenames = [str(r.get("filename") or "") for r in results]

    doc_rank = first_hit_rank(predicted_doc_ids, case.expected_document_ids)
    file_rank = first_hit_rank(predicted_filenames, case.expected_filenames)
    rank_candidates = [r for r in [doc_rank, file_rank] if r is not None]
    rank = min(rank_candidates) if rank_candidates else None

    hit = rank is not None
    return RetrievalCaseResult(case_id=case.id, top_k=top_k, hit=hit, rank=rank)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval eval cases against the current KB.")
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).resolve().parent / "datasets" / "retrieval_gold.jsonl"),
        help="Path to retrieval JSONL dataset.",
    )
    parser.add_argument("--top-k", type=int, default=None, help="Override top_k for all cases.")
    parser.add_argument("--run-id", default=os.getenv("EVAL_RUN_ID"), help="Optional run id for logging.")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = load_cases(dataset_path)
    if not cases:
        raise SystemExit(f"No cases found in {dataset_path}")

    if args.run_id:
        os.environ["EVAL_RUN_ID"] = args.run_id

    log_event(
        {
            "type": "retrieval_eval_start",
            "dataset": str(dataset_path),
            "case_count": len(cases),
            "top_k_override": args.top_k,
        }
    )

    results: list[RetrievalCaseResult] = []
    for case in cases:
        if not case.id or not case.query:
            continue
        r = await run_case(case, top_k_override=args.top_k)
        results.append(r)
        log_event(
            {
                "type": "retrieval_eval_case",
                "case_id": r.case_id,
                "top_k": r.top_k,
                "hit": r.hit,
                "rank": r.rank,
            }
        )

    summary = {
        "type": "retrieval_eval_summary",
        "dataset": str(dataset_path),
        "cases_run": len(results),
        "recall_at_k": recall_at_k(results),
        "mrr": mrr(results),
    }
    log_event(summary)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

