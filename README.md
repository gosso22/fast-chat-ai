# Fast Chat AI - RAG Chatbot Application

A Retrieval-Augmented Generation (RAG) chatbot application that allows users to upload documents and engage in intelligent conversations grounded in their specific knowledge base.

## Features

- **Document Processing**: Upload PDF, TXT, DOCX, and Markdown files with intelligent chunking and overlap strategies
- **Vector Storage**: PostgreSQL with pgvector extension for efficient semantic search
- **Multi-LLM Support**: Automatic provider selection and failover (OpenAI, Anthropic, Google AI)
- **Cost Optimization**: Intelligent provider selection based on cost and availability
- **Conversation Memory**: Hybrid Redis + PostgreSQL memory management with automatic summarization
- **Environment Management**: Multi-tenant support with isolated knowledge bases
- **Role-Based Access**: Admin and chat user roles for document management and conversations
- **Web Interface**: Modern React frontend with TypeScript and Tailwind CSS

## Architecture

```
backend/                        # Python FastAPI backend
├── app/
│   ├── api/                    # Route handlers
│   ├── core/                   # Config, logging, error handling
│   ├── db/                     # Database setup
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic schemas
│   └── services/               # Business logic
│       └── llm_providers/      # Multi-provider LLM abstraction
├── alembic/                    # Database migrations
└── tests/                      # Pytest test suite

frontend/                       # React SPA
├── src/
│   ├── api/                    # Axios API client
│   ├── components/             # React components
│   ├── pages/                  # Page components
│   └── types/                  # TypeScript interfaces
```

## Tech Stack

### Backend
- Python 3.11+ with FastAPI
- PostgreSQL 15 with pgvector extension
- Redis 7 for session management
- SQLAlchemy 2.0 (async)
- Alembic for migrations
- OpenAI, Anthropic, Google AI SDKs

### Frontend
- React 19 with TypeScript
- React Router v7
- Vite 7
- Tailwind CSS v4
- Axios for HTTP client

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ with pgvector extension
- Redis 7+
- API keys for at least one LLM provider (OpenAI, Anthropic, or Google AI)

### Backend Setup

1. Create and activate virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Start PostgreSQL and Redis:
```bash
docker compose up -d
```

5. Run database migrations:
```bash
alembic upgrade head
```

6. Start the development server:
```bash
make run  # or: uvicorn app.main:app --reload
```

### Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm run dev
```

3. Open http://localhost:5173 in your browser

## Development

### Backend Commands

```bash
make install          # Install dependencies
make test             # Run pytest
make lint             # Run flake8 + mypy
make format           # Run black + isort
make run              # Start dev server
make debug            # Dev server with debug logging
make clean            # Remove cache files
```

### Frontend Commands

```bash
npm run dev           # Start Vite dev server
npm run build         # TypeScript check + Vite build
npm run test          # Run Vitest tests
npm run lint          # Run ESLint
```

## Testing

The project includes comprehensive test coverage:

- Unit tests for all services and utilities
- Integration tests for API endpoints
- End-to-end tests for complete workflows
- RAG pipeline integration tests

Run all tests:
```bash
cd backend
make test
```

## Configuration

Key configuration options in `backend/.env`:

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GOOGLE_API_KEY`: Google AI API key
- `DEFAULT_LLM_PROVIDER`: Primary LLM provider
- `EMBEDDING_MODEL`: Embedding model name

## License

MIT

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting pull requests.
