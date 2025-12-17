from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.grader import build_grader, build_grader_prompt
from evals.metrics import RetrievalCaseResult, first_hit_rank
from evals.trace_logger import log_event
from src.active_document import set_active_document_id
from src.agent import AppState, StateDeps, agent
from src.request_context import set_current_model_id


@dataclass(frozen=True)
class QACase:
    id: str
    query: str
    top_k: int = 5
    active_document_id: str | None = None
    expected_document_ids: list[str] = None  # type: ignore[assignment]
    expected_filenames: list[str] = None  # type: ignore[assignment]
    must_include: list[str] = None  # type: ignore[assignment]
    forbidden_claims: list[str] = None  # type: ignore[assignment]

    @staticmethod
    def from_json(obj: dict[str, Any]) -> "QACase":
        return QACase(
            id=str(obj.get("id") or obj.get("case_id") or ""),
            query=str(obj.get("query") or ""),
            top_k=int(obj.get("top_k") or 5),
            active_document_id=obj.get("active_document_id"),
            expected_document_ids=list(obj.get("expected_document_ids") or []),
            expected_filenames=list(obj.get("expected_filenames") or []),
            must_include=list(obj.get("must_include") or []),
            forbidden_claims=list(obj.get("forbidden_claims") or []),
        )


def load_cases(path: Path) -> list[QACase]:
    cases: list[QACase] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(QACase.from_json(json.loads(line)))
    return cases


def _extract_answer_text(run_result: Any) -> str:
    # pydantic_ai has evolved; handle a few common shapes.
    for attr in ("data", "output", "result"):
        if hasattr(run_result, attr):
            v = getattr(run_result, attr)
            if isinstance(v, str):
                return v
            try:
                return str(v)
            except Exception:
                continue
    try:
        return str(run_result)
    except Exception:
        return ""


async def run_one(case: QACase, *, model_id: str, top_k_override: int | None = None) -> dict[str, Any]:
    # Configure model for this run (DynamicChatModel reads request_context)
    set_current_model_id(model_id)
    set_active_document_id(case.active_document_id)

    # Fresh state per case to avoid cross-case contamination
    deps = StateDeps(AppState())

    # Run the agent
    run = await agent.run(case.query, deps=deps)
    answer = _extract_answer_text(run)

    chunks = deps.state.last_chunks or []
    predicted_doc_ids = [str(c.get("document_id") or "") for c in chunks]
    predicted_filenames = [str(c.get("filename") or "") for c in chunks]

    doc_rank = first_hit_rank(predicted_doc_ids, case.expected_document_ids)
    file_rank = first_hit_rank(predicted_filenames, case.expected_filenames)
    rank_candidates = [r for r in [doc_rank, file_rank] if r is not None]
    rank = min(rank_candidates) if rank_candidates else None
    hit = rank is not None

    retrieval = RetrievalCaseResult(case_id=case.id, top_k=top_k_override or case.top_k, hit=hit, rank=rank)

    return {
        "case_id": case.id,
        "query": case.query,
        "answer": answer,
        "chunks": chunks,
        "retrieval_hit": retrieval.hit,
        "retrieval_rank": retrieval.rank,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run groundedness eval cases (agent + LLM judge).")
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).resolve().parent / "datasets" / "qa_gold.jsonl"),
        help="Path to QA JSONL dataset.",
    )
    parser.add_argument(
        "--model-id",
        default=os.getenv("EVAL_MODEL_ID") or os.getenv("DEFAULT_MODEL") or "",
        help="Model under test, e.g. 'azure:novia-gpt-5-nano' or 'ollama:gemma3:12b'.",
    )
    parser.add_argument(
        "--grader-model",
        default=os.getenv("EVAL_GRADER_MODEL") or os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("DEFAULT_MODEL") or "",
        help="Grader model name/deployment (recommended: stable Azure deployment).",
    )
    parser.add_argument(
        "--grader-provider",
        default=os.getenv("EVAL_GRADER_PROVIDER") or "azure",
        choices=["azure", "openai", "ollama"],
        help="Grader provider.",
    )
    parser.add_argument("--top-k", type=int, default=None, help="Override top_k for all cases (informational only).")
    parser.add_argument("--run-id", default=os.getenv("EVAL_RUN_ID"), help="Optional run id for logging.")
    args = parser.parse_args()

    if not args.model_id:
        raise SystemExit("--model-id is required (or set EVAL_MODEL_ID)")
    if not args.grader_model:
        raise SystemExit("--grader-model is required (or set EVAL_GRADER_MODEL / AZURE_OPENAI_DEPLOYMENT)")

    dataset_path = Path(args.dataset)
    cases = load_cases(dataset_path)
    if not cases:
        raise SystemExit(f"No cases found in {dataset_path}")

    if args.run_id:
        os.environ["EVAL_RUN_ID"] = args.run_id

    grader = build_grader(args.grader_model, provider=args.grader_provider)

    log_event(
        {
            "type": "groundedness_eval_start",
            "dataset": str(dataset_path),
            "case_count": len(cases),
            "model_id": args.model_id,
            "grader_model": args.grader_model,
            "grader_provider": args.grader_provider,
        }
    )

    scores = []
    for case in cases:
        if not case.id or not case.query:
            continue

        sample = await run_one(case, model_id=args.model_id, top_k_override=args.top_k)
        prompt = build_grader_prompt(
            query=sample["query"],
            answer=sample["answer"],
            chunks=sample["chunks"],
            must_include=case.must_include,
            forbidden_claims=case.forbidden_claims,
        )
        grade_run = await grader.run(prompt)
        grade = getattr(grade_run, "data", None) or getattr(grade_run, "output", None) or grade_run

        payload = {
            "type": "groundedness_eval_case",
            "case_id": case.id,
            "model_id": args.model_id,
            "grader_model": args.grader_model,
            "retrieval_hit": sample["retrieval_hit"],
            "retrieval_rank": sample["retrieval_rank"],
            "groundedness": getattr(grade, "groundedness", None),
            "citation_quality": getattr(grade, "citation_quality", None),
            "answers_question": getattr(grade, "answers_question", None),
            "hallucinations": getattr(grade, "hallucinations", None),
            "missing_must_include": getattr(grade, "missing_must_include", None),
            "forbidden_claims_found": getattr(grade, "forbidden_claims_found", None),
        }
        log_event(payload)
        scores.append(payload)

    def avg(key: str) -> float:
        vals = [s.get(key) for s in scores if isinstance(s.get(key), int)]
        return float(sum(vals) / len(vals)) if vals else 0.0

    summary = {
        "type": "groundedness_eval_summary",
        "dataset": str(dataset_path),
        "cases_run": len(scores),
        "model_id": args.model_id,
        "grader_model": args.grader_model,
        "avg_groundedness": avg("groundedness"),
        "avg_citation_quality": avg("citation_quality"),
        "avg_answers_question": avg("answers_question"),
        "retrieval_hit_rate": float(sum(1 for s in scores if s.get("retrieval_hit")) / len(scores)) if scores else 0.0,
    }
    log_event(summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

