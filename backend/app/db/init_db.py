"""
Database initialization utilities.
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
from app.db.base import Base
from app.models import document, conversation  # Import to register models


async def create_database_if_not_exists():
    """
    Create the database if it doesn't exist.
    """
    # Extract database name from URL
    db_url = settings.DATABASE_URL
    db_name = db_url.split("/")[-1]
    
    # Connect to postgres database to create our database
    postgres_url = db_url.replace(f"/{db_name}", "/postgres")
    postgres_url = postgres_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    try:
        async with engine.begin() as conn:
            # Check if database exists
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                {"db_name": db_name}
            )
            
            if not result.fetchone():
                # Create database
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Database '{db_name}' created successfully.")
            else:
                print(f"Database '{db_name}' already exists.")
                
    except Exception as e:
        print(f"Error creating database: {e}")
        raise
    finally:
        await engine.dispose()


async def init_database():
    """
    Initialize the database with tables and extensions.
    """
    # Create database if it doesn't exist
    await create_database_if_not_exists()
    
    # Connect to our database
    db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    
    try:
        async with engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            print("pgvector extension enabled.")
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            print("Database tables created successfully.")
            
            # Create vector similarity index
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx "
                     "ON document_chunks USING ivfflat (embedding vector_cosine_ops)")
            )
            print("Vector similarity index created.")
            
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise
    finally:
        await engine.dispose()


async def check_database_connection():
    """
    Check if database connection is working.
    """
    db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(db_url)
    
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            if result.fetchone():
                print("Database connection successful.")
                return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
    finally:
        await engine.dispose()
    
    return False


if __name__ == "__main__":
    asyncio.run(init_database())