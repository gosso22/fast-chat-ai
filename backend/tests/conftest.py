"""
Pytest configuration and fixtures for the RAG Chatbot application.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def sample_text():
    """Sample text for testing document processing."""
    return """
    This is a sample document for testing the RAG chatbot functionality.
    It contains multiple paragraphs and should be processed correctly.
    
    The document processing system should be able to extract this text
    and chunk it appropriately for vector storage and retrieval.
    """