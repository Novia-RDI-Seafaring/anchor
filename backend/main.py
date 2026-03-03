"""Main FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.core import logging # Initialize Logfire early
from src.agent.agent import agent, AgentDeps
from src.agent.state import RAGState
from src.core.config import get_settings
from src.core.context import set_current_model_id
from src.api import documents_router, search_router, config_router
from src.observability.langfuse.config import init_langfuse
from src.knowledge_base.service import DocumentService



# Create main FastAPI app
app = FastAPI(title="Knowledge Base API")

# Initialize Langfuse observability (works alongside Logfire)
init_langfuse()


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def model_context_middleware(request: Request, call_next):
    """Extract model query param and set in context."""
    model_param = request.query_params.get("model")
    if model_param:
        set_current_model_id(model_param)
    response = await call_next(request)
    return response

# Mount the AG-UI agent
ag_ui_app = agent.to_ag_ui(deps=AgentDeps(state=RAGState(), doc_service=DocumentService()))
app.mount("/agent", ag_ui_app)

# Include API routers
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(config_router)


# ===== Health Check =====

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app", 
        host=settings.host, 
        port=settings.port, 
        reload=settings.reload
    )
