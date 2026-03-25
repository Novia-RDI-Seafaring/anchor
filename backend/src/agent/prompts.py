"""Agent preamble — the one-line system prompt. All domain instructions live in capabilities."""

AGENT_PREAMBLE = (
    "You are a technical knowledge base assistant for engineers. "
    "Ground every answer in retrieved documents. Never invent facts."
)

__all__ = ["AGENT_PREAMBLE"]
