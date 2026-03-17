# Core module - cross-cutting concerns and configuration
from .config import get_settings, Settings
from .context import get_current_model_id, set_current_model_id
from .provenance import create_retrieval_id, get_current_trace_id, build_retrieved_chunk
