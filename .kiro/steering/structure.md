# Project Structure

```
backend/                        # Python FastAPI backend
├── app/
│   ├── main.py                 # FastAPI app entry point, middleware, router registration
│   ├── api/                    # Route handlers (chat, documents, monitoring)
│   ├── core/                   # Config (pydantic-settings), logging, error handling
│   │   ├── config.py           # Settings loaded from .env via pydantic-settings
│   │   ├── errors.py           # AppError hierarchy with ErrorCode enum and user-friendly messages
│   │   └── error_handlers.py   # Centralized FastAPI exception handlers
│   ├── db/
│   │   └── base.py             # SQLAlchemy async engine, Base, session helpers, init_db
│   ├── models/                 # SQLAlchemy ORM models (Document, Conversation, ChatMessage, LLMUsage, Environment, UserRole)
│   ├── schemas/                # Pydantic request/response schemas
│   └── services/               # Business logic layer
│       ├── embedding_service.py
│       ├── vector_store.py
│       ├── rag_service.py      # Semantic search: query processing, retrieval, ranking
│       ├── rag_pipeline.py     # Full RAG pipeline orchestration
│       ├── text_chunker.py
│       ├── text_extractor.py
│       ├── file_validator.py
│       ├── memory_manager.py   # Conversation memory (Redis-backed)
│       ├── cost_tracker.py     # LLM usage cost tracking
│       ├── metrics_collector.py
│       ├── redis_client.py
│       └── llm_providers/      # Multi-provider LLM abstraction
│           ├── base.py         # ABC LLMProvider, request/response models, error types
│           ├── factory.py      # Provider config from settings, global manager singleton
│           ├── manager.py      # Priority-based failover across providers
│           ├── openai_provider.py
│           ├── anthropic_provider.py
│           └── google_provider.py
├── alembic/                    # Database migrations
│   └── versions/               # Numbered migration files (001_, 002_, 003_)
├── tests/                      # Pytest test suite
│   ├── conftest.py             # Fixtures (TestClient, sample data)
│   └── test_*.py               # Test modules mirror app structure
├── docker-compose.yml          # Local Postgres (pgvector) + Redis
├── Makefile                    # Common dev commands
├── requirements.txt            # Full dependencies
├── requirements-core.txt       # Minimal runtime dependencies
└── pyproject.toml              # black, isort, mypy, pytest config

frontend/                       # React SPA
├── src/
│   ├── main.tsx                # React root render
│   ├── App.tsx                 # RouterProvider wrapper
│   ├── router.tsx              # Route definitions (/, /chat, /documents)
│   ├── api/                    # Axios API client modules (chat, documents)
│   │   └── client.ts           # Shared Axios instance with interceptors
│   ├── components/
│   │   ├── chat/               # ChatMessage, ConversationList, MessageInput, MessageList
│   │   ├── documents/          # FileUpload, DocumentList, UploadProgress
│   │   └── layout/             # App shell layout
│   ├── pages/                  # ChatPage, DocumentsPage (with co-located tests)
│   ├── types/                  # TypeScript interfaces matching backend schemas
│   ├── hooks/                  # Custom React hooks (placeholder)
│   ├── store/                  # State management (placeholder)
│   └── test/
│       └── setup.ts            # Vitest/jsdom setup (@testing-library/jest-dom)
├── package.json
├── eslint.config.js
└── index.html
```

## Architecture Patterns

- Backend follows a layered architecture: API routes → Services → Models/DB
- Services are the primary business logic layer; route handlers stay thin
- LLM providers use an abstract base class with a factory + manager pattern for failover
- All database operations are async (SQLAlchemy async sessions)
- Error handling uses a custom AppError hierarchy with error codes, user-friendly messages, and recovery suggestions
- Frontend uses page-level components that compose smaller feature components
- API client is centralized with shared Axios instance and error interceptor
- Frontend types mirror backend Pydantic schemas
