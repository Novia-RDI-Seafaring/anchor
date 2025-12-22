# Core module - cross-cutting concerns and configuration
from .config import get_settings, Settings
from .context import get_current_model_id, set_current_model_id, get_active_document_id, set_active_document_id
