from contextvars import ContextVar
from typing import Optional

# Context variable to store the model ID for the current request
model_id_ctx: ContextVar[Optional[str]] = ContextVar("model_id", default=None)

def get_current_model_id() -> Optional[str]:
    """Get the model ID for the current request."""
    return model_id_ctx.get()

def set_current_model_id(model_id: str) -> None:
    """Set the model ID for the current request."""
    model_id_ctx.set(model_id)
