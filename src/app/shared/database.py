"""Engine async + session por request (R3). Postgres en CI/Docker, SQLite local."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.shared.settings import Settings


def create_engine_for(url: str):  # type: ignore[no-untyped-def]
    """Crea el engine async según el esquema de la URL."""
    if url.startswith("sqlite"):
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(url, pool_pre_ping=True)


def session_factory_for(url: str) -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones async ligada a una URL (testeable sin settings globales)."""
    engine = create_engine_for(url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def session_por_request(settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI: una AsyncSession por request (R3)."""
    factory = session_factory_for(settings.database_url)
    async with factory() as session:
        yield session
