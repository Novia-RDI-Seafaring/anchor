# Backend Configuration Service
#
# This file provides configuration management for the backend using Pydantic Settings.
# Environment variables are loaded from .env file automatically.

import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Create a .env file in the backend directory with your configuration.
    See .env.example for template.
    """
    
    # ===== API Settings =====
    host: str = "0.0.0.0"
    port: int = 8001
    reload: bool = True
    
    # ===== Logfire (Observability) =====
    logfire_token: str | None = None
    
    # ===== pgvector/Supabase Settings =====
    pgvector_host: str = "localhost"
    pgvector_port: int = 6543
    pgvector_db: str = "postgres"
    pgvector_user: str = "postgres"
    pgvector_password: str = ""
    pgsslmode: str = "disable"
    
    # ===== Vector DB Settings =====
    vector_db_collection: str = "documents"
    embedding_dimension: int = 3072  # text-embedding-3-large dimension
    
    # ===== RAG Configuration =====
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k_results: int = 5
    similarity_threshold: float = 0.3
    
    # ===== Document Storage =====
    uploads_dir: str = "../uploads"
    
    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection URL from components."""
        return f"postgresql://{self.pgvector_user}:{self.pgvector_password}@{self.pgvector_host}:{self.pgvector_port}/{self.pgvector_db}?sslmode={self.pgsslmode}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
