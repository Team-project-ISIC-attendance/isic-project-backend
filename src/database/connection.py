"""Database connection and session management."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings


def _ensure_database_directory() -> None:
    """Ensure database directory exists."""
    # Extract database path from URL
    # Formats:
    # - sqlite+aiosqlite:///./data/isic_scans.db (relative with ./)
    # - sqlite+aiosqlite:////app/data/isic_scans.db (absolute with //)
    # - sqlite+aiosqlite:///data/isic_scans.db (relative)
    url = settings.database_url
    if url.startswith("sqlite+aiosqlite:///"):
        db_path = url.replace("sqlite+aiosqlite:///", "", 1)
        
        # Handle absolute paths (starting with //)
        if db_path.startswith("//"):
            db_path = "/" + db_path[2:]
            db_file = Path(db_path)
        # Handle relative paths with ./
        elif db_path.startswith("./"):
            db_path = db_path[2:]
            db_file = Path(db_path).resolve()
        # Handle relative paths without ./
        else:
            db_file = Path(db_path).resolve()
        
        db_dir = db_file.parent
        
        # Create directory if it doesn't exist and is not root
        if db_dir and db_dir != Path("/") and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)


# Ensure database directory exists before creating engine
_ensure_database_directory()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

