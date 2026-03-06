"""
FastAPI main application entry point for RAG Chatbot.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.error_handlers import register_error_handlers
from app.api import documents, chat, environments, monitoring, roles, users

# Initialize logging before anything else
setup_logging()

app = FastAPI(
    title="RAG Chatbot API",
    description="A Retrieval-Augmented Generation chatbot with document processing capabilities",
    version="1.0.0",
)

# Register centralized error handlers and request logging middleware
register_error_handlers(app)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(documents.env_docs_router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)
app.include_router(chat.env_chat_router, prefix=settings.API_V1_STR)
app.include_router(environments.router, prefix=settings.API_V1_STR)
app.include_router(monitoring.router, prefix=settings.API_V1_STR)
app.include_router(roles.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "RAG Chatbot API is running"}


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "service": "rag-chatbot-api",
        "version": "1.0.0"
    }
