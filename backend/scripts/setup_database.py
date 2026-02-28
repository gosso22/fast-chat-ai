#!/usr/bin/env python3
"""
Database setup script for RAG Chatbot.

This script initializes the database with all required tables and extensions.
Run this after setting up PostgreSQL and before starting the application.
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.init_db import init_database, check_database_connection
from app.core.config import settings


async def main():
    """Main setup function."""
    print("🚀 Starting RAG Chatbot Database Setup")
    print("=" * 50)
    
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Redis URL: {settings.REDIS_URL}")
    print()
    
    # Check if we can connect to the database
    print("📡 Checking database connection...")
    if not await check_database_connection():
        print("❌ Database connection failed!")
        print("Please ensure PostgreSQL is running and the connection details are correct.")
        print("Check your .env file or environment variables.")
        return False
    
    print("✅ Database connection successful!")
    print()
    
    # Initialize the database
    print("🔧 Initializing database...")
    try:
        await init_database()
        print("✅ Database initialization completed successfully!")
        print()
        
        print("📋 Database setup summary:")
        print("  • pgvector extension enabled")
        print("  • All tables created:")
        print("    - documents")
        print("    - document_chunks (with vector embeddings)")
        print("    - conversations")
        print("    - chat_messages")
        print("    - llm_usage")
        print("  • Vector similarity indexes created")
        print("  • Foreign key constraints established")
        print()
        
        print("🎉 Database setup completed successfully!")
        print("You can now start the RAG Chatbot application.")
        
        return True
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("Please check the error message above and try again.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)