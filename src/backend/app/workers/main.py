"""Worker de jobs Redis (mensajes, vencimientos de seña, reintentos — KB §08 Outbox).

En este change solo deja el esqueleto ejecutable: conecta a Redis y procesa la
cola `turnos:jobs`. Los jobs reales llegan en C-08/C-12.
"""

import asyncio
import json
from typing import Any

from app.shared.logging import logger
from app.shared.settings import get_settings


async def procesar_job(payload: dict[str, Any]) -> None:
    """Procesa un job de la cola Redis sin exponer jamás PHI en logs (R9)."""
    tipo = str(payload.get("tipo", "desconocido"))
    logger.info("Job recibido de tipo=%s", tipo)
    if tipo == "procesar_outbox":
        from app.application.comunicaciones import procesar_outbox_pendientes
        from app.shared.database import session_factory_for

        factory = session_factory_for(get_settings().database_url)
        async with factory() as session:
            await procesar_outbox_pendientes(session)
            await session.commit()


async def run() -> None:
    """Loop del worker contra Redis (sale si Redis no está disponible)."""
    import redis.asyncio as redis_async

    settings = get_settings()
    cliente = redis_async.from_url(
        settings.redis_url,
        socket_connect_timeout=5,
        socket_timeout=10,
    )
    try:
        await cliente.ping()
    except Exception:
        logger.error("Che, el worker no llegó a Redis. Revisá que esté levantado.")
        raise
    logger.info("Worker escuchando cola turnos:jobs.")
    while True:
        try:
            item = await cliente.brpop("turnos:jobs", timeout=2)
        except (TimeoutError, redis_async.TimeoutError):
            continue
        if item is None:
            continue
        try:
            await procesar_job(json.loads(item[1]))
        except Exception:
            logger.exception("El job falló y se descarta (reintentos en C-08).")


if __name__ == "__main__":
    asyncio.run(run())
