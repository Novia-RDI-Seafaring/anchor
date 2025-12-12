"""
Token estimation helpers for instrumentation.
"""
from __future__ import annotations

from typing import Iterable, Optional

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None  # type: ignore


def estimate_tokens(text: str, model_name: Optional[str] = None) -> int:
    """
    Estimate token count for a string. Falls back to a rough char/4 heuristic.
    """
    if not text:
        return 0

    if tiktoken:
        try:
            enc = (
                tiktoken.encoding_for_model(model_name)
                if model_name
                else tiktoken.get_encoding("cl100k_base")
            )
            return len(enc.encode(text))
        except Exception:
            pass

    # Rough heuristic if tokenizer is unavailable
    return max(1, len(text) // 4)


def estimate_tokens_bulk(texts: Iterable[str], model_name: Optional[str] = None) -> int:
    """
    Estimate tokens for multiple strings by summing the individual estimates.
    """
    return sum(estimate_tokens(t, model_name=model_name) for t in texts)
