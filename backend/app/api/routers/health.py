"""GET /api/health público: estado de API + PostgreSQL + Redis (spec foundation 1.1).

Respuestas en rioplatense, sin stack traces ni PHI (R9). 200 sano, 503 si cae
una dependencia con indicación de qué revisar.
"""

from fastapi import APIRouter, Depends, Response

from app.api import deps
from app.api.schemas import HealthEstado
from app.shared.settings import Settings

router = APIRouter(tags=["salud"])


async def _chequear_db(url: str) -> bool:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    try:
        engine = create_async_engine(url, pool_pre_ping=False)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        finally:
            await engine.dispose()
    except Exception:
        return False


async def _chequear_redis(url: str) -> bool:
    try:
        import redis.asyncio as redis_async

        cliente = redis_async.from_url(url, socket_connect_timeout=2)
        try:
            await cliente.ping()
            return True
        finally:
            await cliente.aclose()
    except Exception:
        return False


@router.get("/health", response_model=HealthEstado)
async def health(
    response: Response,
    settings: Settings = Depends(deps.settings_cacheados),  # noqa: B008
) -> HealthEstado:
    """Health check público: 200 si todo ok, 503 si DB o Redis no responden."""
    db_ok = await _chequear_db(settings.database_url)
    redis_ok = await _chequear_redis(settings.redis_url)
    if db_ok and redis_ok:
        return HealthEstado(estado="ok", api="ok", base_de_datos="ok", redis="ok")
    caidos = [n for n, ok in (("la base de datos", db_ok), ("redis", redis_ok)) if not ok]
    response.status_code = 503
    return HealthEstado(
        estado="error",
        api="ok",
        base_de_datos="ok" if db_ok else "caida",
        redis="ok" if redis_ok else "caido",
        detalle=f"Che, no llegamos a {' y '.join(caidos)}. Revisá que el servicio esté levantado.",
    )
