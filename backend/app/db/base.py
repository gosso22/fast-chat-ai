"""
Database base configuration and session management.
"""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# Create declarative base
Base = declarative_base()


# Create async engine for database operations
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=True,  # Set to False in production
    future=True,
)


def get_async_session() -> AsyncSession:
    """
    Create a new async session.
    """
    return AsyncSession(engine, expire_on_commit=False)


async def get_db():
    """
    Dependency to get database session.
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    """
    try:
        async with engine.begin() as conn:
            # Import all models to ensure they are registered
            from app.models import document, conversation, environment, user_role  # noqa: F401
            
            # Enable pgvector extension
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            
            # Create vector similarity index
            await conn.execute(
                sa.text("CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx "
                       "ON document_chunks USING ivfflat (embedding vector_cosine_ops)")
            )
    except Exception as e:
        print(f"Database initialization failed: {e}")
        raise


async def close_db() -> None:
    """
    Close database connections.
    """
    await engine.dispose()