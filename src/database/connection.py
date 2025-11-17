from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

SQLITE_URL_PREFIX = "sqlite+aiosqlite:///"
ROOT_PATH = Path("/")


def _extract_database_path_from_url(url: str) -> Path | None:
    if not url.startswith(SQLITE_URL_PREFIX):
        return None

    path_string = url.replace(SQLITE_URL_PREFIX, "", 1)

    if path_string.startswith("//"):
        absolute_path = "/" + path_string[2:]
        return Path(absolute_path)
    elif path_string.startswith("./"):
        relative_path = path_string[2:]
        return Path(relative_path).resolve()
    else:
        return Path(path_string).resolve()


def _ensure_database_directory() -> None:
    db_file = _extract_database_path_from_url(settings.database_url)
    if db_file is None:
        return

    db_directory = db_file.parent

    is_not_root = db_directory != ROOT_PATH
    directory_exists = db_directory.exists()

    if db_directory and is_not_root and not directory_exists:
        db_directory.mkdir(parents=True, exist_ok=True)


_ensure_database_directory()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

