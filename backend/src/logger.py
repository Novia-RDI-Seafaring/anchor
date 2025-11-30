# Structured logging utility for backend
# Uses Logfire for observability with structured logs

import logfire
from typing import Any
import os

# Configure Logfire
# logfire_token = os.getenv("LOGFIRE_TOKEN")
# if logfire_token:
#    logfire.configure(token=logfire_token)
# else:
    # Development mode - log to console
#    logfire.configure(send_to_logfire=False)

# Configure Logfire - always use console mode for now [TO BE REMOVE LATER]
logfire.configure(send_to_logfire=False)

# Create logger instance
logger = logfire


# Convenience functions for common logging patterns
def log_rag_query(query: str, top_k: int, result_count: int, duration_ms: float):
    """Log RAG query with relevant metadata."""
    logfire.info(
        "RAG Query",
        query=query,
        top_k=top_k,
        result_count=result_count,
        duration_ms=duration_ms,
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
