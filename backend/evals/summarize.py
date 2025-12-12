"""
Aggregate eval logs from logs/runs.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

LOG_FILE = Path(__file__).resolve().parent / "logs" / "runs.jsonl"


def _quantiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0}
    values = sorted(values)
    n = len(values)

    def q(p: float) -> float:
        if n == 1:
            return values[0]
        idx = min(n - 1, max(0, int(p * (n - 1))))
        return values[idx]

    return {
        "p50": q(0.50),
        "p95": q(0.95),
        "p99": q(0.99),
    }


def load_events() -> List[Dict[str, Any]]:
    if not LOG_FILE.exists():
        print(f"No log file found at {LOG_FILE}")
        return []
    events = []
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def summarize(events: List[Dict[str, Any]]) -> None:
    llm_events = [e for e in events if e.get("type") == "llm_call"]
    ret_events = [e for e in events if e.get("type") == "retrieval"]
    emb_events = [e for e in events if e.get("type") == "embedding"]
    state_events = [e for e in events if e.get("type") == "state"]

    print("=== LLM Calls ===")
    if llm_events:
        latencies = [e.get("latency_ms", 0) for e in llm_events]
        prompt_tokens = [e.get("prompt_tokens_est", 0) for e in llm_events]
        resp_tokens = [e.get("usage", {}).get("completion_tokens", 0) for e in llm_events]
        print(f"count={len(llm_events)}")
        print(f"latency_ms={_quantiles(latencies)}")
        print(f"prompt_tokens_est=avg {int(mean(prompt_tokens))} max {max(prompt_tokens)}")
        if resp_tokens:
            print(f"response_tokens=avg {int(mean(resp_tokens))} max {max(resp_tokens)}")
    else:
        print("none")

    print("\n=== Retrieval ===")
    if ret_events:
        latencies = [e.get("latency_ms", 0) for e in ret_events]
        print(f"count={len(ret_events)}")
        print(f"latency_ms={_quantiles(latencies)}")
        avg_results = mean([e.get("result_count", 0) for e in ret_events])
        print(f"avg_results={avg_results:.2f}")
        avg_chunk_tokens = mean([e.get("total_chunk_tokens", 0) for e in ret_events])
        print(f"avg_total_chunk_tokens={avg_chunk_tokens:.0f}")
    else:
        print("none")

    print("\n=== Embeddings ===")
    if emb_events:
        latencies = [e.get("latency_ms", 0) for e in emb_events]
        print(f"count={len(emb_events)}")
        print(f"latency_ms={_quantiles(latencies)}")
    else:
        print("none")

    print("\n=== State Snapshots ===")
    if state_events:
        latest = state_events[-1]
        print(f"conversation_history={latest.get('conversation_len')}")
        print(f"last_chunks={latest.get('last_chunks_len')}")
        print(f"active_ui_components={latest.get('ui_components_len')}")
    else:
        print("none")


if __name__ == "__main__":
    events = load_events()
    summarize(events)
