"""Worker de jobs Redis (mensajes, vencimientos de seña, reintentos — KB §08 Outbox)."""

import asyncio
import json
import os
import time
import uuid
from typing import Any

from app.shared.logging import logger
from app.shared.settings import get_settings

# Throttle de purga en el loop del worker (D6): una vez cada 5 minutos.
PURGA_THROTTLE_SEGUNDOS = 300
_ultima_purga_monotonic: float = 0.0


async def _purgar_si_corresponde(force: bool = False) -> None:
    """Barrido throttled de archivos de exportación vencidos (D6, 5.5)."""
    global _ultima_purga_monotonic
    import app.application.exportacion as _exp

    ahora = time.monotonic()
    if not force and (ahora - _ultima_purga_monotonic) < PURGA_THROTTLE_SEGUNDOS:
        return
    try:
        await _exp.purgar_exportaciones_vencidas()
    except Exception:  # pragma: no cover
        logger.exception("Falló la purga de exportaciones vencidas.")
    _ultima_purga_monotonic = time.monotonic()


# Alias para tests/compatibilidad.
barrer_exportaciones = _purgar_si_corresponde
barrer_si_corresponde = _purgar_si_corresponde
purgar_si_corresponde = _purgar_si_corresponde


async def procesar_job(
    payload: dict[str, Any],
    redis: Any = None,
    session: Any = None,
    settings: Any = None,
    session_factory: Any = None,
) -> None:
    """Procesa un job de la cola Redis sin exponer jamás PHI en logs (R9)."""
    tipo = str(payload.get("tipo", "desconocido"))
    logger.info("Job recibido de tipo=%s", tipo)
    if tipo == "procesar_outbox":
        from app.application.comunicaciones import procesar_outbox_pendientes
        from app.shared.database import session_factory_for

        if settings is None:
            settings = get_settings()
        factory = session_factory or session_factory_for(settings.database_url)
        async with factory() as ses:
            await procesar_outbox_pendientes(ses)
            await ses.commit()
        return

    if tipo != "exportar_dataset":
        return

    import app.application.exportacion as _exp

    if settings is None:
        settings = get_settings()
    if redis is None:
        import redis.asyncio as redis_async

        redis = redis_async.from_url(
            settings.redis_url,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
    if session is None and session_factory is None:
        from app.shared.database import session_factory_for

        session_factory = session_factory_for(settings.database_url)

    job_id = str(payload.get("job_id"))
    tenant_id = uuid.UUID(str(payload.get("tenant_id")))
    dataset = str(payload.get("dataset"))
    formato = str(payload.get("formato", "csv")).strip().lower()
    desde = payload.get("desde")
    hasta = payload.get("hasta")

    hash_key = _exp.clave_job(tenant_id, job_id)

    directorio = getattr(_exp, "EXPORTACIONES_DIR", None)
    if not directorio:
        directorio = getattr(settings, "exportaciones_dir", None) or "/var/tmp/turnos-exportaciones"
    os.makedirs(directorio, exist_ok=True)

    ext = "json" if formato == "json" else "csv"
    nombre_archivo = f"{job_id}.{ext}"
    ruta = os.path.join(directorio, nombre_archivo)

    exito = False
    try:
        await _purgar_si_corresponde(force=True)
        try:
            await redis.hset(hash_key, "estado", "procesando")
        except Exception:
            pass

        async def _armar(ses: Any) -> None:
            nonlocal exito
            exportacion = await _exp.exportar_dataset(
                ses,
                tenant_id=tenant_id,
                dataset=dataset,
                formato=formato,
                desde=desde,
                hasta=hasta,
                opaco=job_id,
            )

            def _escribir() -> None:
                with open(ruta, "wb") as fh:
                    fh.write(exportacion.contenido)

            await asyncio.to_thread(_escribir)
            try:
                await redis.hset(
                    hash_key,
                    mapping={
                        "estado": "listo",
                        "filas": str(exportacion.filas),
                        "nombre_archivo": nombre_archivo,
                        "error": "",
                    },
                )
            except Exception:
                pass
            exito = True

        if session is not None:
            await _armar(session)
        else:
            async with session_factory() as ses:
                await _armar(ses)
    except Exception:
        try:
            await redis.hset(
                hash_key,
                mapping={
                    "estado": "error",
                    "error": "No pudimos generar el archivo.",
                },
            )
        except Exception:
            pass
        logger.exception("Job exportar_dataset falló job_id=%s", job_id)
    finally:
        if not exito:
            try:
                os.remove(ruta)
            except FileNotFoundError:
                pass
            except OSError:
                pass


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
    await _purgar_si_corresponde(force=True)
    while True:
        try:
            await _purgar_si_corresponde()
            item = await cliente.brpop("turnos:jobs", timeout=2)
        except (TimeoutError, redis_async.TimeoutError):
            continue
        except Exception:
            logger.exception("Error leyendo la cola.")
            await asyncio.sleep(1)
            continue
        if item is None:
            continue
        await _purgar_si_corresponde(force=True)
        try:
            await procesar_job(json.loads(item[1]), redis=cliente, settings=settings)
        except Exception:
            logger.exception("El job falló y se descarta (reintentos en C-08).")


if __name__ == "__main__":
    asyncio.run(run())
