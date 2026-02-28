#!/bin/bash

# Start local database services for RAG Chatbot testing

echo "🚀 Starting RAG Chatbot Local Database Services"
echo "================================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Start services
echo "📦 Starting PostgreSQL with pgvector and Redis..."
docker compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check PostgreSQL
echo "🔍 Checking PostgreSQL connection..."
if docker compose exec -T postgres pg_isready -U postgres -d rag_chatbot > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "⚠️  PostgreSQL is starting up, please wait a moment..."
fi

# Check Redis
echo "🔍 Checking Redis connection..."
if docker compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is ready"
else
    echo "⚠️  Redis is starting up, please wait a moment..."
fi

echo ""
echo "📋 Service Information:"
echo "  PostgreSQL: localhost:5433"
echo "    Database: rag_chatbot"
echo "    Username: postgres"
echo "    Password: password"
echo ""
echo "  Redis: localhost:6379"
echo ""
echo "🔧 Next steps:"
echo "  1. Copy .env.example to .env (if not done already)"
echo "  2. Run: python scripts/setup_database.py"
echo "  3. Run tests: ../.venv/bin/python -m pytest tests/ -v"
echo ""
echo "🛑 To stop services: docker-compose down"