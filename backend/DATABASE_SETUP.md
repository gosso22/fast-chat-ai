# Database Setup Guide

This guide explains how to set up the PostgreSQL database with pgvector extension for the RAG Chatbot application.

## Prerequisites

1. **PostgreSQL 15+** with **pgvector extension**
2. **Python 3.11+** with required dependencies installed
3. **Environment configuration** (see Configuration section)

## Quick Setup

### 1. Install PostgreSQL with pgvector

#### Ubuntu/Debian:
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Install pgvector extension
sudo apt install postgresql-15-pgvector
```

#### macOS (with Homebrew):
```bash
# Install PostgreSQL
brew install postgresql

# Install pgvector
brew install pgvector
```

#### Docker (Alternative):
```bash
# Run PostgreSQL with pgvector in Docker
docker run -d \
  --name rag-postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=rag_chatbot \
  -p 5432:5432 \
  pgvector/pgvector:pg15
```

### 2. Configure Environment

Create a `.env` file in the backend directory:

```bash
cp .env.example .env
```

Edit `.env` with your database credentials:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/rag_chatbot
REDIS_URL=redis://localhost:6379
# ... other configuration
```

### 3. Run Database Setup

```bash
# From the backend directory
python scripts/setup_database.py
```

Or using the virtual environment:

```bash
../.venv/bin/python scripts/setup_database.py
```

## Manual Setup (Alternative)

If you prefer to set up the database manually:

### 1. Create Database

```sql
-- Connect to PostgreSQL as superuser
CREATE DATABASE rag_chatbot;
\c rag_chatbot;

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Run Alembic Migrations

```bash
# From the backend directory
alembic upgrade head
```

## Database Schema

The setup creates the following tables:

### Documents Table
- Stores uploaded document metadata
- Tracks processing status
- Links to document chunks

### Document Chunks Table
- Stores text chunks from processed documents
- Contains vector embeddings (1536 dimensions)
- Includes chunk metadata (position, token count)
- Has vector similarity index for efficient search

### Conversations Table
- Stores chat conversation metadata
- Tracks user sessions
- Links to messages and usage data

### Chat Messages Table
- Stores individual chat messages
- Supports user and assistant roles
- Tracks token counts for cost management

### LLM Usage Table
- Tracks LLM API usage and costs
- Supports multiple providers (OpenAI, Anthropic, Google)
- Enables cost monitoring and optimization

## Vector Operations

The database includes optimized vector operations:

### Vector Similarity Index
```sql
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops);
```

### Similarity Search Example
```sql
SELECT content, embedding <=> %s AS distance
FROM document_chunks
ORDER BY embedding <=> %s
LIMIT 5;
```

## Testing

Run the database tests to verify setup:

```bash
# Test database models
../.venv/bin/python -m pytest tests/test_models.py -v

# Test database operations
../.venv/bin/python -m pytest tests/test_database.py -v
```

## Troubleshooting

### Common Issues

1. **pgvector extension not found**
   - Ensure pgvector is installed for your PostgreSQL version
   - Check that the extension is available: `SELECT * FROM pg_available_extensions WHERE name = 'vector';`

2. **Connection refused**
   - Verify PostgreSQL is running: `sudo systemctl status postgresql`
   - Check connection details in `.env` file
   - Ensure database exists and user has permissions

3. **Permission denied**
   - Grant necessary permissions to your database user:
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE rag_chatbot TO your_user;
   ```

4. **Migration errors**
   - Check Alembic configuration in `alembic.ini`
   - Verify database URL format: `postgresql+asyncpg://user:pass@host:port/db`

### Verification Commands

```bash
# Check database connection
../.venv/bin/python -c "
import asyncio
from app.db.init_db import check_database_connection
print('Connected:', asyncio.run(check_database_connection()))
"

# List tables
psql -d rag_chatbot -c "\dt"

# Check pgvector extension
psql -d rag_chatbot -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:password@localhost:5432/rag_chatbot` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `EMBEDDING_DIMENSION` | Vector embedding dimension | `1536` |
| `CHUNK_SIZE` | Text chunk size in tokens | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

### Database URL Format

```
postgresql://[user[:password]@][host][:port][/database]
```

For async operations (used internally):
```
postgresql+asyncpg://[user[:password]@][host][:port][/database]
```

## Next Steps

After successful database setup:

1. **Start Redis** (for conversation memory)
2. **Configure LLM providers** (OpenAI, Anthropic, Google)
3. **Run the application** with `uvicorn app.main:app --reload`
4. **Test document upload** and chat functionality

## Support

If you encounter issues:

1. Check the application logs
2. Verify PostgreSQL and Redis are running
3. Test database connection with the verification commands
4. Review the troubleshooting section above