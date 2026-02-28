#!/bin/bash

# Script to prepare Git repository with structured commits based on implementation tasks
# This creates a meaningful commit history that reflects the development process

set -e

echo "🚀 Preparing Git repository with structured commits..."

# Reset git repository
rm -rf .git
git init

# Commit 1: Project foundation and structure
echo "📦 Commit 1: Project foundation and structure"
git add .gitignore README.md .kiro/
git commit -m "feat: initialize project structure and documentation

- Add comprehensive README with features and setup instructions
- Create .gitignore for Python, Node.js, and development files
- Add Kiro steering documents (product, tech stack, structure)
- Add project specifications (requirements, design, tasks)

Related to Task 1: Set up project structure and core dependencies"

# Commit 2: Backend foundation
echo "🔧 Commit 2: Backend foundation and configuration"
git add backend/requirements*.txt backend/pyproject.toml backend/.flake8 backend/Makefile
git add backend/app/__init__.py backend/app/main.py
git add backend/.env.example backend/docker-compose.yml
git commit -m "feat: set up backend foundation with FastAPI

- Add Python dependencies (FastAPI, SQLAlchemy, Pydantic, LLM SDKs)
- Configure development tools (black, isort, mypy, flake8, pytest)
- Create FastAPI application entry point with CORS middleware
- Add Docker Compose for PostgreSQL (pgvector) and Redis
- Create Makefile for common development tasks

Related to Task 1: Set up project structure and core dependencies"

# Commit 3: Database setup and models
echo "🗄️ Commit 3: Database setup and ORM models"
git add backend/app/db/ backend/app/models/
git add backend/alembic/ backend/alembic.ini
git add backend/DATABASE_SETUP.md backend/scripts/
git commit -m "feat: implement database layer with PostgreSQL and pgvector

- Create SQLAlchemy async engine and session management
- Implement ORM models (Document, Conversation, ChatMessage, LLMUsage)
- Set up Alembic for database migrations
- Add pgvector extension for vector similarity search
- Create database setup scripts and documentation

Related to Task 2: Configure database and vector storage foundation"

# Commit 4: Core configuration and error handling
echo "⚙️ Commit 4: Core configuration and error handling"
git add backend/app/core/
git commit -m "feat: implement core configuration and error handling

- Create Pydantic settings with environment variable loading
- Implement custom error hierarchy with ErrorCode enum
- Add centralized FastAPI exception handlers
- Create user-friendly error messages with recovery suggestions
- Set up structured logging configuration

Related to Task 9.3: Implement application-wide error handling"

# Commit 5: Document processing services
echo "📄 Commit 5: Document processing services"
git add backend/app/services/file_validator.py
git add backend/app/services/text_extractor.py
git add backend/app/services/text_chunker.py
git add backend/tests/test_file_validator.py
git add backend/tests/test_text_extractor.py
git add backend/tests/test_text_chunker.py
git commit -m "feat: implement document processing pipeline

- Create file validator for PDF, TXT, DOCX, MD formats
- Add PDF text extraction (PyPDF2 and pdfplumber)
- Implement DOCX and Markdown text extraction
- Create chunking algorithm with overlap (500-1000 tokens)
- Add token counting using tiktoken
- Write comprehensive unit tests

Related to Tasks 3.1, 3.2, 3.3: Document processing pipeline"

# Commit 6: Embedding and vector storage
echo "🔢 Commit 6: Embedding and vector storage"
git add backend/app/services/embedding_service.py
git add backend/app/services/vector_store.py
git add backend/tests/test_embedding_service.py
git add backend/tests/test_vector_store.py
git commit -m "feat: implement embedding generation and vector storage

- Integrate OpenAI text-embedding-3-small (1536 dimensions)
- Add batch processing for efficient embedding generation
- Create PostgreSQL vector storage with pgvector
- Implement similarity search with configurable limits
- Add document deletion and cleanup operations
- Write integration tests

Related to Tasks 4.1, 4.2: Embedding generation and vector storage"

# Commit 7: LLM provider system
echo "🤖 Commit 7: Multi-LLM provider system"
git add backend/app/services/llm_providers/
git add backend/app/services/cost_tracker.py
git add backend/tests/test_llm_providers.py
git add backend/tests/test_cost_tracker.py
git add backend/tests/test_llm_provider_failover.py
git commit -m "feat: implement multi-LLM provider system with failover

- Create abstract base class for LLM providers
- Implement OpenAI, Anthropic, and Google AI providers
- Add cost calculation and provider optimization
- Implement automatic failover and health checks
- Create provider factory and manager
- Write comprehensive tests

Related to Tasks 5.1, 5.2, 5.3: LLM provider management"

# Commit 8: Memory management
echo "💾 Commit 8: Conversation memory management"
git add backend/app/services/redis_client.py
git add backend/app/services/memory_manager.py
git add backend/tests/test_redis_session.py
git add backend/tests/test_memory_manager.py
git add backend/tests/test_hybrid_memory_manager.py
git add backend/tests/test_intelligent_token_management.py
git commit -m "feat: implement hybrid conversation memory management

- Set up Redis client for fast session storage
- Create memory manager with PostgreSQL persistence
- Implement hybrid Redis + PostgreSQL memory
- Add automatic conversation summarization
- Create intelligent token management
- Write comprehensive tests

Related to Tasks 6.1, 6.2, 6.3, 6.4: Memory management"

# Commit 9: RAG pipeline
echo "🔎 Commit 9: RAG pipeline and semantic search"
git add backend/app/services/rag_service.py
git add backend/app/services/rag_pipeline.py
git add backend/tests/test_rag_service.py
git add backend/tests/test_rag_pipeline.py
git commit -m "feat: implement complete RAG pipeline

- Create query processing and embedding generation
- Implement similarity search for document retrieval
- Add context ranking and relevance scoring
- Create prompt engineering system
- Implement response generation with source citation
- Write integration tests

Related to Tasks 7.1, 7.2: RAG pipeline"

# Commit 10: Document and chat APIs
echo "💬 Commit 10: Document and chat API endpoints"
git add backend/app/api/documents.py backend/app/api/chat.py backend/app/api/dependencies.py
git add backend/app/schemas/
git add backend/tests/test_documents_api.py
git add backend/tests/test_chat_api.py
git commit -m "feat: implement document and chat API endpoints

- Create document upload and management endpoints
- Implement conversation creation and messaging
- Add conversation history retrieval
- Create Pydantic schemas for validation
- Write API integration tests

Related to Tasks 3.1, 7.3: API endpoints"

# Commit 11: Monitoring and metrics
echo "📊 Commit 11: Monitoring and metrics"
git add backend/app/api/monitoring.py
git add backend/app/services/metrics_collector.py
git add backend/tests/test_monitoring.py
git add backend/tests/test_error_handling.py
git commit -m "feat: implement monitoring and error handling

- Create metrics collection system
- Add health check endpoints
- Implement usage reporting
- Add performance monitoring
- Enhance error handling and recovery
- Write tests

Related to Tasks 9.1, 9.2, 9.4: Monitoring and error handling"

# Commit 12: Environment and RBAC
echo "🌍 Commit 12: Environment management and RBAC"
git add backend/app/api/environments.py backend/app/api/roles.py
git add backend/tests/test_environment_models.py
git add backend/tests/test_environments_api.py
git add backend/tests/test_env_documents_api.py
git add backend/tests/test_rbac.py
git add backend/tests/test_env_chat.py
git commit -m "feat: implement environment management and role-based access

- Create environments for isolated knowledge bases
- Add user_roles with admin and chat_user types
- Implement environment management API
- Add environment-scoped document management
- Create role-based access control
- Implement environment-scoped chat
- Write comprehensive tests

Related to Tasks 10.1-10.5: Environment and RBAC"

# Commit 13: Integration tests
echo "🧪 Commit 13: Integration and E2E tests"
git add backend/tests/test_rag_integration.py
git add backend/tests/test_e2e.py
git add backend/tests/conftest.py
git add backend/tests/test_main.py
git add backend/tests/__init__.py
git add backend/tests/test_models.py
git add backend/tests/test_database.py
git add backend/test_*.py
git commit -m "test: add comprehensive integration and E2E test suite

- Create complete document-to-chat flow tests
- Add multi-provider failover tests
- Test conversation memory management
- Add performance benchmarks
- Test environment isolation
- Add database and model tests

Related to Task 11.1: Integration testing"

# Commit 14: Frontend foundation
echo "⚛️ Commit 14: Frontend foundation with React"
git add frontend/package*.json frontend/tsconfig*.json
git add frontend/vite.config.ts frontend/vitest.config.ts
git add frontend/eslint.config.js frontend/.gitignore
git add frontend/index.html frontend/public/
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/router.tsx
git add frontend/src/index.css frontend/src/assets/
git commit -m "feat: set up React frontend with TypeScript

- Initialize React 19 with TypeScript
- Configure Vite 7 build tool
- Set up Tailwind CSS v4
- Add React Router v7
- Configure Vitest for testing
- Create basic app structure

Related to Task 8.1: React application setup"

# Commit 15: Frontend API and types
echo "🌐 Commit 15: Frontend API client and types"
git add frontend/src/api/
git add frontend/src/types/
git add frontend/src/test/
git add frontend/src/hooks/
git add frontend/src/store/
git commit -m "feat: implement frontend API client and infrastructure

- Create Axios client with interceptors
- Add API modules for chat and documents
- Define TypeScript interfaces
- Set up Vitest with jsdom
- Add placeholder for hooks and state management

Related to Task 8.1: Frontend infrastructure"

# Commit 16: Frontend components
echo "💬 Commit 16: Frontend UI components"
git add frontend/src/components/
git add frontend/src/pages/
git commit -m "feat: implement frontend UI components

- Create file upload component with drag-and-drop
- Add upload progress indicators
- Implement document list component
- Create chat message display components
- Add message input with typing indicators
- Implement conversation list navigation
- Create responsive layout

Related to Tasks 8.2, 8.3: Frontend UI"

echo "✅ All commits created successfully!"
echo ""
echo "📊 Commit Summary:"
git log --oneline --graph --all
echo ""
echo "🎉 Repository is ready to push to GitHub!"
echo ""
echo "Next steps:"
echo "1. Create a new repository on GitHub"
echo "2. Add remote: git remote add origin <your-repo-url>"
echo "3. Push: git push -u origin master"
