from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel


class GroundednessGrade(BaseModel):
    groundedness: int = Field(ge=0, le=5, description="How well the answer is supported by the provided chunks.")
    citation_quality: int = Field(
        ge=0, le=5, description="If citations/sources are present, are they consistent with the chunks?"
    )
    answers_question: int = Field(ge=0, le=5, description="Does the answer address the user query?")
    hallucinations: list[str] = Field(default_factory=list, description="Specific unsupported claims, if any.")
    missing_must_include: list[str] = Field(default_factory=list, description="Items from must_include not present.")
    forbidden_claims_found: list[str] = Field(default_factory=list, description="Forbidden claims that appear.")
    notes: str = Field(default="", description="Short explanation for the scores.")


def build_grader(model_name: str, provider: Literal["azure", "ollama", "openai"] = "azure") -> Agent[Any, GroundednessGrade]:
    """
    Create a strict JSON-output grader agent.

    Notes:
    - Use a stable grader model/provider (typically Azure) to keep scoring comparable across runs.
    """
    system = (
        "You are a strict RAG evaluator.\n"
        "Only use the provided CHUNKS as evidence.\n"
        "If a claim is not supported by the chunks, list it as a hallucination.\n"
        "Return ONLY valid JSON matching the schema."
    )
    return Agent(
        model=OpenAIModel(model_name, provider=provider),
        result_type=GroundednessGrade,
        system_prompt=system,
    )


def build_grader_prompt(
    *,
    query: str,
    answer: str,
    chunks: list[dict[str, Any]],
    must_include: list[str] | None = None,
    forbidden_claims: list[str] | None = None,
    max_chunk_chars: int = 1500,
) -> str:
    def chunk_text(c: dict[str, Any]) -> str:
        content = str(c.get("content") or "")
        content = content[:max_chunk_chars]
        doc = str(c.get("document_id") or "")
        fn = str(c.get("filename") or "")
        sim = c.get("similarity")
        meta = c.get("metadata") or {}
        return f"- doc_id={doc} filename={fn} similarity={sim}\n  {content}\n  meta_keys={list(meta.keys())}"

    chunks_block = "\n".join(chunk_text(c) for c in chunks[:20]) if chunks else "(none)"
    must = must_include or []
    forbid = forbidden_claims or []
    return (
        f"QUERY:\n{query}\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"MUST_INCLUDE:\n{must}\n\n"
        f"FORBIDDEN_CLAIMS:\n{forbid}\n\n"
        f"CHUNKS:\n{chunks_block}\n"
    )

