"""
Application configuration settings.
"""

from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "RAG Chatbot"
    
    # CORS Configuration
    ALLOWED_HOSTS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/rag_chatbot"
    
    # Redis Configuration (for conversation memory)
    REDIS_URL: str = "redis://localhost:6379"
    
    # File Upload Configuration
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_DIR: str = "uploads"
    
    # LLM Provider Configuration
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    
    # LLM Provider Settings
    OPENAI_ENABLED: bool = True
    ANTHROPIC_ENABLED: bool = True
    GOOGLE_ENABLED: bool = True
    
    OPENAI_PRIORITY: int = 2
    ANTHROPIC_PRIORITY: int = 1  # Highest priority (cheapest)
    GOOGLE_PRIORITY: int = 3
    
    # Default model preferences
    PREFERRED_MODEL: Optional[str] = None
    
    # Embedding Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    
    # Chunking Configuration
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # Global admin user IDs (comma-separated)
    ADMIN_USER_IDS: List[str] = ["default_admin"]

    @field_validator("ADMIN_USER_IDS", mode="before")
    @classmethod
    def assemble_admin_ids(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v


settings = Settings()