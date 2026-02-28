# Tech Stack

## Backend (Python 3.11)
- Framework: FastAPI with Pydantic v2 for validation and settings
- Server: Uvicorn (ASGI)
- Database: PostgreSQL 15 with pgvector extension (async via asyncpg + SQLAlchemy 2.0 async)
- Migrations: Alembic
- Cache/Sessions: Redis 7
- LLM SDKs: openai, anthropic, google-generativeai
- Document processing: PyPDF2, pdfplumber, python-docx, markdown
- Embeddings: OpenAI text-embedding-3-small (1536 dimensions)
- HTTP client: httpx (async)
- Tokenization: tiktoken

## Frontend (TypeScript)
- Framework: React 19 with React Router v7
- Build tool: Vite 7
- Styling: Tailwind CSS v4
- HTTP client: Axios
- Testing: Vitest + React Testing Library + jsdom
- Linting: ESLint with typescript-eslint, react-hooks, react-refresh plugins

## Python Virtual Environment
- Location: `.venv/` at the project root
- Python version: 3.13.11 (`/usr/bin/python3.13`)
- Activate: `source .venv/bin/activate`
- All backend Python commands (pytest, alembic, uvicorn, etc.) should run with the venv activated or via `.venv/bin/python`

## Infrastructure
- Docker Compose for local PostgreSQL (pgvector/pgvector:pg15) and Redis
- PostgreSQL exposed on port 5433 (maps to container 5432)
- Redis on port 6379

## Common Commands

### Backend (run from `backend/`)
```bash
make install          # Install dependencies
make test             # Run pytest
make lint             # flake8 + mypy
make format           # black + isort
make run              # Start dev server (uvicorn, port 8000)
make debug            # Dev server with debug logging
make clean            # Remove cache files
```

### Frontend (run from `frontend/`)
```bash
npm run dev           # Start Vite dev server
npm run build         # TypeScript check + Vite build
npm run test          # Vitest single run (--run)
npm test -- --watch   # Vitest watch mode
npm run lint          # ESLint
```

### Database
```bash
# Start local Postgres + Redis
docker compose -f backend/docker-compose.yml up -d

# Run migrations (from backend/)
alembic upgrade head
```

## Code Style

### Python
- Formatter: black (line length 88)
- Import sorting: isort (profile "black")
- Linting: flake8 (max-line-length 88, ignores E203/W503/E501)
- Type checking: mypy (strict mode — disallow_untyped_defs, no_implicit_optional, etc.)
- Target: Python 3.11

### TypeScript/React
- ESLint flat config with recommended rules for TS and React hooks
- ECMAScript 2020 target
