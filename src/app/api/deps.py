"""Dependencias FastAPI: settings + session por request (R3)."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import session_factory_for
from app.shared.settings import Settings, get_settings


@lru_cache
def settings_cacheados() -> Settings:
    """Settings singleton (falla al arrancar si falta una requerida, spec 1.2)."""
    return get_settings()


async def sesion_db() -> AsyncGenerator[AsyncSession, None]:
    """Una AsyncSession por request; se cierra sola al terminar (R3)."""
    factory = session_factory_for(settings_cacheados().database_url)
    async with factory() as session:
        yield session
