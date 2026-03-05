# API module - HTTP routes and schemas
from .routes_documents import router as documents_router
from .routes_search import router as search_router
from .routes_config import router as config_router
from .file_provider import router as file_provider_router

__all__ = ["documents_router", "search_router", "config_router", "file_provider_router"]
