# Structured logging utility for backend
# Uses Logfire for observability with structured logs

import logfire
from typing import Any
import os

# Configure Logfire
logfire_token = (os.getenv("LOGFIRE_TOKEN") or "").strip()
if logfire_token and logfire_token.lower() != "none":
    # ### Modify to use explicit token only ##
    # Why: avoids accidentally picking stale local credentials and producing 401 export noise.
    logfire.configure(token=logfire_token, scrubbing=False, send_to_logfire=True)
    print("Logfire configured (remote export enabled)")
else:
    # ### Modify to local-only mode ##
    # Why: with no valid token, Logfire defaults can still attempt remote export and spam 401 warnings.
    logfire.configure(send_to_logfire=False)
    print("Logfire local-only mode (remote export disabled)")

# Instrument Pydantic AI for automatic LLM tracking
logfire.instrument_pydantic_ai()

# Instrument HTTP client for raw LLM request/response tracking
logfire.instrument_httpx(capture_all=True)

# Instrument OpenAI SDK
logfire.instrument_openai()

# Instrument LlamaIndex for RAG tracking
try:
    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
    LlamaIndexInstrumentor().instrument()
    print("LlamaIndex instrumented")
except ImportError:
    print("LlamaIndex instrumentor not found, skipping")

# Instrument SQLAlchemy for database tracking
try:
    logfire.instrument_sqlalchemy()
    print("SQLAlchemy instrumented")
except Exception:
    pass

# Create logger instance
logger = logfire


# Convenience functions for common logging patterns
def log_rag_query(query: str, top_k: int, result_count: int, duration_ms: float, context: list[dict[str, Any]] | None = None):
    """Log RAG query with relevant metadata and optionally context snippets."""
    logfire.info(
        "RAG Query",
        query=query,
        top_k=top_k,
        result_count=result_count,
        duration_ms=duration_ms,
        context_preview=[c.get("content", "")[:200] for c in (context or [])],
        event_type="rag_query"
    )


def log_agent_tool_call(tool_name: str, args: dict[str, Any]):
    """Log agent tool invocation."""
    logfire.info(
        f"Agent Tool: {tool_name}",
        tool_name=tool_name,
        args=args,
        event_type="agent_tool"
    )


def log_db_operation(operation: str, collection: str, duration_ms: float, success: bool = True):
    """Log database operations."""
    level = logfire.info if success else logfire.error
    level(
        f"DB Operation: {operation}",
        operation=operation,
        collection=collection,
        duration_ms=duration_ms,
        success=success,
        event_type="db_operation"
    )


def log_error(message: str, error: Exception, context: dict[str, Any] | None = None):
    """Log errors with full context."""
    logfire.error(
        message,
        error=str(error),
        error_type=type(error).__name__,
        context=context or {},
        event_type="error"
    )
