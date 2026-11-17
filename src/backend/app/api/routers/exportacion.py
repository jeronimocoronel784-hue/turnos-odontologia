"""Exportación de datasets del consultorio (`/api/exportacion/*`, C-14, D4/D5/D6).

Cumple:
- R1 / R8: schemas Pydantic y montos calculados en servidor.
- R4: `tenant_id` proviene exclusivamente del JWT.
- R9: sin PHI en URLs, logs ni nombres de archivo.
- RBAC: `Recurso.EXPORTACION_TENANT` con `EXPORTAR` (solo Dueño).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas_exportacion import (
    DatasetExportable,
    ExportacionJobRead,
    FormatoExportacion,
)
from app.api.security import ActorAutenticado, requiere
from app.application import auditoria as _auditoria_mod
from app.application import exportacion as _exp
from app.domain.rbac import Accion, Recurso
from app.shared.exceptions import AppError, EntidadInvalida
from app.shared.settings import Settings

# Alias público para permitir monkeypatch en tests (auditoría).
registrar_auditoria = _auditoria_mod.registrar_auditoria
_ORIGINAL_REGISTRAR_AUDITORIA = registrar_auditoria

router = APIRouter(tags=["exportacion"])


def _umbral(settings: Settings) -> int:
    s_val = int(getattr(settings, "exportacion_umbral_filas", 5000))
    if s_val == 5000 and getattr(_exp, "EXPORTACION_UMBRAL_FILAS", 5000) != 5000:
        return int(_exp.EXPORTACION_UMBRAL_FILAS)
    return s_val


def _export_dir(settings: Settings) -> str:
    settings_dir = getattr(settings, "exportaciones_dir", None)
    if settings_dir and settings_dir != "/var/tmp/turnos-exportaciones":
        return str(settings_dir)
    return _exp.EXPORTACIONES_DIR or settings_dir or "/var/tmp/turnos-exportaciones"


def _parse_dt(valor: str | None) -> datetime | None:
    return _exp._parse_fecha(valor)


@router.get(
    "/exportacion/{dataset}",
    response_class=Response,
    responses={
        200: {"description": "Archivo generado (directo)."},
        202: {"description": "Encolado para procesamiento asíncrono."},
        400: {"description": "Solicitud inválida (rango de fechas)."},
        403: {"description": "Permiso insuficiente."},
        422: {"description": "Dataset o formato inválido."},
        503: {"description": "Servicio no disponible."},
    },
)
async def get_exportacion_dataset(
    dataset: Annotated[
        str,
        Path(
            description="Dataset a exportar.",
            json_schema_extra={"enum": [d.value for d in DatasetExportable]},
        ),
    ],
    actor: Annotated[
        ActorAutenticado, Depends(requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR))
    ],
    session: Annotated[AsyncSession, Depends(deps.sesion_db)],
    redis: Annotated[Redis, Depends(deps.cliente_redis)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
    formato: Annotated[
        str,
        Query(
            description="Formato de salida.",
            json_schema_extra={"enum": [f.value for f in FormatoExportacion]},
        ),
    ] = "csv",
    desde: Annotated[
        str | None, Query(description="Fecha/hora desde (ISO-8601, ART si sin offset).")
    ] = None,
    hasta: Annotated[
        str | None, Query(description="Fecha/hora hasta (ISO-8601, ART si sin offset).")
    ] = None,
) -> Response:
    """Descarga (o encola) la exportación de un dataset del consultorio (D4/D5/D6)."""
    # Validar dataset.
    if dataset not in _exp.DATASETS_VALIDOS:
        raise EntidadInvalida(
            "Che, el dataset tiene que ser uno de: " + ", ".join(_exp.DATASETS_VALIDOS) + "."
        )
    # Validar formato.
    formato_limpio = (formato or "csv").strip().lower()
    if formato_limpio not in ("csv", "json"):
        raise EntidadInvalida("Che, el formato tiene que ser 'csv' o 'json'.")

    desde_dt = _exp._parse_fecha(desde)
    hasta_dt = _exp._parse_fecha(hasta)

    # pacientes ignora el período.
    if dataset != "pacientes":
        if desde_dt is None and hasta_dt is None:
            desde_dt, hasta_dt = _exp._default_periodo(dataset)
        else:
            _exp._validar_rango(dataset, desde_dt, hasta_dt)
    else:
        desde_dt = None
        hasta_dt = None

    # Conteo previo (D5).
    filas_count = await _exp.contar_filas_dataset(
        session, tenant_id=actor.tenant_id, dataset=dataset, desde=desde_dt, hasta=hasta_dt
    )

    umbral = _umbral(settings)
    # Camino directo.
    if filas_count <= umbral:
        exportacion = await _exp.exportar_dataset(
            session,
            tenant_id=actor.tenant_id,
            dataset=dataset,
            formato=formato_limpio,
            desde=desde,
            hasta=hasta,
            opaco=str(uuid.uuid4()),
        )

        # Auditoría en la misma transacción (D7).
        async def _registrar_directo() -> None:
            fn = globals().get("registrar_auditoria", _ORIGINAL_REGISTRAR_AUDITORIA)
            await fn(
                session,
                tenant_id=actor.tenant_id,
                actor_id=actor.usuario_id,
                accion="exportacion.solicitar",
                entidad="exportacion",
                entidad_id=str(uuid.uuid4()),
                despues={
                    "dataset": dataset,
                    "formato": formato_limpio,
                    "filas": exportacion.filas,
                    "modo": "directo",
                },
            )

        try:
            await _registrar_directo()
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if isinstance(exc, AppError):
                raise
            raise AppError(
                "¡Uh! Algo salió mal de nuestro lado. Probá de nuevo en un rato.", status_code=500
            ) from exc

        return Response(
            content=exportacion.contenido,
            media_type=exportacion.media_type,
            headers=exportacion.cabeceras(),
        )

    # Camino asíncrono (D6).
    await _exp.purgar_exportaciones_vencidas()

    job_id = str(uuid.uuid4())
    creado_at = datetime.now(UTC)
    expira_at = creado_at + timedelta(seconds=_exp.JOB_TTL_SEGUNDOS)
    hash_key = _exp.clave_job(actor.tenant_id, job_id)

    mapping = {
        "estado": "pendiente",
        "dataset": dataset,
        "formato": formato_limpio,
        "filas": str(filas_count),
        "creado_at": creado_at.isoformat(),
        "expira_at": expira_at.isoformat(),
        "nombre_archivo": "",
        "error": "",
    }

    # 1) Job en Redis antes del commit. Si Redis no responde, abortar sin job ni evento.
    try:
        await redis.hset(hash_key, mapping=mapping)  # type: ignore[arg-type]
        await redis.expire(hash_key, _exp.JOB_TTL_SEGUNDOS)
    except Exception as exc:
        try:
            await redis.delete(hash_key)
        except Exception:
            pass
        await session.rollback()
        raise AppError(
            "Che, el servicio de colas no está disponible. Probá de nuevo en un rato.",
            status_code=503,
        ) from exc

    # 2) Evento de auditoría + commit.
    try:
        fn = globals().get("registrar_auditoria", _ORIGINAL_REGISTRAR_AUDITORIA)
        await fn(
            session,
            tenant_id=actor.tenant_id,
            actor_id=actor.usuario_id,
            accion="exportacion.solicitar",
            entidad="exportacion",
            entidad_id=job_id,
            despues={
                "dataset": dataset,
                "formato": formato_limpio,
                "filas": filas_count,
                "modo": "asincronico",
            },
        )
        await session.commit()
    except Exception as exc:
        try:
            await redis.delete(hash_key)
        except Exception:
            pass
        await session.rollback()
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "¡Uh! Algo salió mal de nuestro lado. Probá de nuevo en un rato.", status_code=500
        ) from exc

    # 3) RPUSH después del commit.
    payload = {
        "tipo": "exportar_dataset",
        "job_id": job_id,
        "tenant_id": str(actor.tenant_id),
        "actor_id": str(actor.usuario_id),
        "dataset": dataset,
        "formato": formato_limpio,
        "desde": desde,
        "hasta": hasta,
    }
    try:
        await redis.rpush(_exp.COLA_JOBS, json.dumps(payload))
    except Exception as exc:
        try:
            await redis.hset(hash_key, "estado", "error")
            await redis.hset(hash_key, "error", "No pudimos encolar el job.")
        except Exception:
            pass
        raise AppError(
            "Che, no pudimos encolar la exportación. Probá de nuevo en un rato.",
            status_code=503,
        ) from exc

    job_read = ExportacionJobRead(
        job_id=job_id,
        estado="pendiente",
        dataset=dataset,
        formato=formato_limpio,
        filas=filas_count,
        creado_at=creado_at,
        expira_at=expira_at,
        nombre_archivo=None,
        error=None,
    )
    return Response(
        content=job_read.model_dump_json(),
        media_type="application/json",
        status_code=202,
    )


@router.get("/exportacion/jobs/{job_id}", response_model=ExportacionJobRead)
async def get_exportacion_job(
    job_id: Annotated[str, Path(description="Identificador del job de exportación.")],
    actor: Annotated[
        ActorAutenticado, Depends(requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR))
    ],
    redis: Annotated[Redis, Depends(deps.cliente_redis)],
) -> ExportacionJobRead:
    data = await _exp.leer_job_exportacion(redis, actor.tenant_id, job_id)
    if not data:
        raise AppError("Che, ese job no existe o ya venció. Volvé a exportar.", status_code=404)
    # Expiry check.
    expira_raw = data.get("expira_at")
    try:
        expira_dt = datetime.fromisoformat(expira_raw) if expira_raw else None
    except (ValueError, TypeError):
        expira_dt = None
    if expira_dt is not None and expira_dt < datetime.now(UTC):
        raise AppError("Che, ese job no existe o ya venció. Volvé a exportar.", status_code=404)

    estado = data.get("estado", "pendiente")
    filas_raw = data.get("filas")
    try:
        filas = int(filas_raw) if filas_raw not in (None, "") else None
    except (ValueError, TypeError):
        filas = None
    creado_raw = data.get("creado_at")
    try:
        creado_dt = datetime.fromisoformat(creado_raw) if creado_raw else None
    except (ValueError, TypeError):
        creado_dt = None
    nombre = data.get("nombre_archivo") or None
    if nombre == "":
        nombre = None
    error = data.get("error") or None
    if error == "":
        error = None

    return ExportacionJobRead(
        job_id=job_id,
        estado=estado,
        dataset=data.get("dataset"),
        formato=data.get("formato"),
        filas=filas,
        creado_at=creado_dt,
        expira_at=expira_dt,
        nombre_archivo=nombre,
        error=error,
    )


@router.get("/exportacion/jobs/{job_id}/descarga")
async def get_exportacion_job_descarga(
    job_id: Annotated[str, Path(description="Identificador del job de exportación.")],
    actor: Annotated[
        ActorAutenticado, Depends(requiere(Recurso.EXPORTACION_TENANT, Accion.EXPORTAR))
    ],
    redis: Annotated[Redis, Depends(deps.cliente_redis)],
    settings: Annotated[Settings, Depends(deps.settings_cacheados)],
) -> Response:
    data = await _exp.leer_job_exportacion(redis, actor.tenant_id, job_id)
    if not data:
        raise AppError("Che, ese job no existe o ya venció. Volvé a exportar.", status_code=404)
    expira_raw = data.get("expira_at")
    try:
        expira_dt = datetime.fromisoformat(expira_raw) if expira_raw else None
    except (ValueError, TypeError):
        expira_dt = None
    if expira_dt is not None and expira_dt < datetime.now(UTC):
        raise AppError("Che, ese job no existe o ya venció. Volvé a exportar.", status_code=404)

    estado = data.get("estado", "pendiente")
    if estado != "listo":
        raise AppError(
            "Che, todavía estamos generando el archivo. Esperá un toque.", status_code=409
        )

    formato = (data.get("formato") or "csv").strip().lower()
    ext = "json" if formato == "json" else "csv"
    nombre = data.get("nombre_archivo") or f"{job_id}.{ext}"
    nombre = os.path.basename(nombre)
    if not nombre.endswith(f".{ext}"):
        nombre = f"{job_id}.{ext}"

    directorio = _export_dir(settings)
    ruta = os.path.join(directorio, nombre)

    def _leer_archivo() -> bytes:
        if not os.path.isfile(ruta):
            raise FileNotFoundError
        with open(ruta, "rb") as fh:
            return fh.read()

    try:
        contenido = await asyncio.to_thread(_leer_archivo)
    except FileNotFoundError:
        raise AppError(
            "Che, ese job no existe o ya venció. Volvé a exportar.", status_code=404
        ) from None

    media_type = "application/json" if ext == "json" else "text/csv; charset=utf-8"
    from urllib.parse import quote

    cd = f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{quote(nombre, safe='')}"
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": cd, "Cache-Control": "no-store"},
    )
