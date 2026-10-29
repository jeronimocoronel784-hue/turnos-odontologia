"""Dependencias FastAPI: settings + session por request (R3) + cliente Redis."""

from collections.abc import AsyncGenerator
from functools import lru_cache

import redis.asyncio as redis_async
from redis.asyncio import Redis
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


@lru_cache
def _cliente_redis() -> Redis:
    """Cliente Redis compartido (rate limiting, colas)."""
    return redis_async.from_url(settings_cacheados().redis_url, decode_responses=True)


async def cliente_redis() -> AsyncGenerator[Redis, None]:
    """Dependency del cliente Redis; los tests la overridean con fakeredis."""
    yield _cliente_redis()
