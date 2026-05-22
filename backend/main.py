"""Main FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.agent.agent import agent, AgentDeps
from src.agent.state import Canvas
from src.core.config import get_settings
from src.core.context import set_current_model_id
from src.api import documents_router, search_router, config_router, file_provider_router
from src.api.routes_conversations import router as conversations_router
from src.api.routes_fmu import router as fmu_router
from src.api.routes_snippets import router as snippets_router

# Create main FastAPI app
app = FastAPI(title="Knowledge Base API")


settings = get_settings()
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
allow_credentials = "*" not in origins

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
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
ag_ui_app = agent.to_ag_ui(deps=AgentDeps(state=Canvas()))
app.mount("/agent", ag_ui_app)

# Include API routers
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(config_router)
app.include_router(file_provider_router)
app.include_router(conversations_router)
app.include_router(fmu_router)
app.include_router(snippets_router)


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
