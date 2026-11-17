"""Exportación tenant-wide de datasets del consultorio (C-14, D4/D5/D12/D13).

Genera en memoria el archivo (CSV o JSON) para los cuatro datasets del Flujo 7,
con el servidor como única fuente de verdad (R8), enmascarado de identificadores
en los textos libres de caja y liquidaciones (D12) y conteo previo contra el
umbral (D5). Sin migración, sin cambios de esquema.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.caja import MovimientoCaja
from app.domain.liquidacion_os import LiquidacionOS
from app.domain.paciente import Paciente
from app.domain.prestacion import Prestacion
from app.domain.sillon import Sillon
from app.domain.turno import Turno
from app.domain.usuario import Usuario
from app.shared.exceptions import EntidadInvalida, SolicitudInvalida
from app.shared.sanitizar_phi import sanitizar_phi

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ZONA_ART = timezone(timedelta(hours=-3))

# Umbral de filas para exportación directa (D5). Configurable por entorno.
EXPORTACION_UMBRAL_FILAS = int(os.getenv("EXPORTACION_UMBRAL_FILAS", "5000"))

# Directorio de archivos de exportación (D6).
EXPORTACIONES_DIR = os.getenv("EXPORTACIONES_DIR", "/var/tmp/turnos-exportaciones")

# TTL fijo de 24 h para jobs y archivos (D6): sin variable de entorno.
JOB_TTL_SEGUNDOS = 24 * 60 * 60

# Cola Redis reutilizada (D6).
COLA_JOBS = "turnos:jobs"

# Estados posibles del job (D6).
JOB_ESTADOS = ("pendiente", "en_cola", "procesando", "listo", "error")

DATASETS_VALIDOS = ("agenda", "pacientes", "caja", "liquidaciones")

# Columnas cerradas (D4): lista exacta y en orden.
COLUMNAS_AGENDA = (
    "turno_id",
    "inicio",
    "fin",
    "estado",
    "prestacion",
    "profesional",
    "matricula",
    "sillon",
    "paciente_id",
    "paciente_nombre",
    "sobreturno",
)
COLUMNAS_PACIENTES = (
    "paciente_id",
    "nombre",
    "dni",
    "telefono",
    "email",
    "fecha_nac",
    "obra_social",
    "nro_afiliado",
    "optin_wa",
    "activo",
    "created_at",
)
COLUMNAS_CAJA = (
    "movimiento_id",
    "created_at",
    "tipo",
    "concepto",
    "medio",
    "monto",
    "turno_id",
    "cierre_id",
)
COLUMNAS_LIQUIDACIONES = (
    "liquidacion_id",
    "obra_social",
    "periodo",
    "estado",
    "total",
    "total_reconocido",
    "turnos_sin_cobertura",
    "observaciones",
    "created_at",
)

COLUMNAS_POR_DATASET: dict[str, tuple[str, ...]] = {
    "agenda": COLUMNAS_AGENDA,
    "pacientes": COLUMNAS_PACIENTES,
    "caja": COLUMNAS_CAJA,
    "liquidaciones": COLUMNAS_LIQUIDACIONES,
}

# Alias usados por posibles callers/tests.
COLUMNAS_EXPORTACION = COLUMNAS_POR_DATASET


@dataclass(frozen=True)
class ExportacionDataset:
    """Archivo de exportación ya armado en memoria (R3)."""

    contenido: bytes
    media_type: str
    nombre_archivo: str
    nombre_legible: str
    filas: int = 0

    def cabeceras(self) -> dict[str, str]:
        from urllib.parse import quote

        extendido = quote(self.nombre_legible, safe="")
        return {
            "Content-Disposition": (
                f"attachment; filename=\"{self.nombre_archivo}\"; filename*=UTF-8''{extendido}"
            ),
            "Cache-Control": "no-store",
        }


# Alias de compatibilidad.
Exportacion = ExportacionDataset
ExportacionDirecta = ExportacionDataset


def _periodo_filename(desde: datetime | None, hasta: datetime | None, dataset: str) -> str:
    if dataset == "pacientes":
        return "padron"
    if desde is None or hasta is None:
        return "periodo"
    desde_txt = desde.astimezone(ZONA_ART).date().strftime("%Y%m%d")
    hasta_txt = (hasta.astimezone(ZONA_ART) - timedelta(days=1)).date().strftime("%Y%m%d")
    return f"{desde_txt}_{hasta_txt}"


def _nombre_archivo(dataset: str, periodo: str, opaco: str, ext: str) -> str:
    return f"exportacion-{dataset}-{periodo}-{opaco}.{ext}"


def _parse_fecha(valor: str | None) -> datetime | None:
    if valor is None:
        return None
    texto = valor.strip()
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SolicitudInvalida(
            "Che, la fecha tiene que estar en formato ISO-8601 (AAAA-MM-DD o AAAA-MM-DDThh:mm:ss)."
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZONA_ART)
    return dt.astimezone(UTC)


def _default_periodo(dataset: str) -> tuple[datetime, datetime]:
    ahora = datetime.now(ZONA_ART)
    primer_dia = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if primer_dia.month == 12:
        siguiente = primer_dia.replace(year=primer_dia.year + 1, month=1)
    else:
        siguiente = primer_dia.replace(month=primer_dia.month + 1)
    return primer_dia.astimezone(UTC), siguiente.astimezone(UTC)


def _validar_rango(dataset: str, desde: datetime | None, hasta: datetime | None) -> None:
    if dataset == "pacientes":
        return
    ahora = datetime.now(UTC)
    if hasta is not None and hasta > ahora:
        raise SolicitudInvalida("Che, 'hasta' no puede ser una fecha futura.")
    if desde is not None and hasta is not None:
        if desde > hasta:
            raise SolicitudInvalida("Che, 'desde' no puede ser posterior a 'hasta'. Corregilo.")
        if (hasta - desde) > timedelta(days=366):
            raise SolicitudInvalida(
                "Che, el rango no puede superar los 366 dias. "
                "Dividi el pedido en periodos mas chicos."
            )


def _mes_periodo(fecha: datetime) -> str:
    return fecha.astimezone(ZONA_ART).strftime("%Y%m")


def _meses_del_rango(desde: datetime, hasta: datetime) -> tuple[str, str]:
    return _mes_periodo(desde), _mes_periodo(hasta)


# ---------------------------------------------------------------------------
# Consultas por dataset
# ---------------------------------------------------------------------------


async def _filas_agenda(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> list[dict[str, Any]]:
    stmt = (
        select(Turno, Paciente, Usuario, Prestacion, Sillon)
        .join(Paciente, Turno.paciente_id == Paciente.id)
        .join(Usuario, Turno.profesional_id == Usuario.id)
        .join(Prestacion, Turno.prestacion_id == Prestacion.id)
        .join(Sillon, Turno.sillon_id == Sillon.id)
        .where(Turno.tenant_id == tenant_id)
    )
    if desde is not None:
        stmt = stmt.where(Turno.inicio >= desde)
    if hasta is not None:
        stmt = stmt.where(Turno.inicio < hasta)
    stmt = stmt.order_by(Turno.inicio.asc(), Turno.id.asc())
    result = await session.execute(stmt)
    filas: list[dict[str, Any]] = []
    for turno, paciente, profesional, prestacion, sillon in result.all():
        filas.append(
            {
                "turno_id": str(turno.id),
                "inicio": _iso(turno.inicio),
                "fin": _iso(turno.fin),
                "estado": turno.estado,
                "prestacion": prestacion.nombre,
                "profesional": profesional.nombre,
                "matricula": profesional.matricula,
                "sillon": sillon.nombre,
                "paciente_id": str(paciente.id),
                "paciente_nombre": paciente.nombre,
                "sobreturno": bool(turno.sobreturno),
            }
        )
    return filas


async def _contar_agenda(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> int:
    stmt = select(func.count()).select_from(Turno).where(Turno.tenant_id == tenant_id)
    if desde is not None:
        stmt = stmt.where(Turno.inicio >= desde)
    if hasta is not None:
        stmt = stmt.where(Turno.inicio < hasta)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _filas_pacientes(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    stmt = (
        select(Paciente)
        .where(Paciente.tenant_id == tenant_id)
        .order_by(Paciente.created_at.asc(), Paciente.id.asc())
    )
    result = await session.execute(stmt)
    filas: list[dict[str, Any]] = []
    for paciente in result.scalars().all():
        filas.append(
            {
                "paciente_id": str(paciente.id),
                "nombre": paciente.nombre,
                "dni": paciente.dni,
                "telefono": paciente.telefono,
                "email": paciente.email,
                "fecha_nac": paciente.fecha_nac.isoformat() if paciente.fecha_nac else None,
                "obra_social": str(paciente.obra_social_id) if paciente.obra_social_id else None,
                "nro_afiliado": paciente.nro_afiliado,
                "optin_wa": bool(paciente.optin_wa),
                "activo": bool(paciente.activo),
                "created_at": _iso(paciente.created_at),
            }
        )
    return filas


async def _contar_pacientes(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Paciente).where(Paciente.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _filas_caja(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> list[dict[str, Any]]:
    stmt = select(MovimientoCaja).where(MovimientoCaja.tenant_id == tenant_id)
    if desde is not None:
        stmt = stmt.where(MovimientoCaja.created_at >= desde)
    if hasta is not None:
        stmt = stmt.where(MovimientoCaja.created_at < hasta)
    stmt = stmt.order_by(MovimientoCaja.created_at.asc(), MovimientoCaja.id.asc())
    result = await session.execute(stmt)
    filas: list[dict[str, Any]] = []
    for mov in result.scalars().all():
        filas.append(
            {
                "movimiento_id": str(mov.id),
                "created_at": _iso(mov.created_at),
                "tipo": mov.tipo,
                "concepto": sanitizar_phi(mov.concepto),
                "medio": mov.medio,
                "monto": _decimal_str(mov.monto),
                "turno_id": str(mov.turno_id) if mov.turno_id else None,
                "cierre_id": str(mov.cierre_id) if mov.cierre_id else None,
            }
        )
    return filas


async def _contar_caja(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> int:
    stmt = (
        select(func.count())
        .select_from(MovimientoCaja)
        .where(MovimientoCaja.tenant_id == tenant_id)
    )
    if desde is not None:
        stmt = stmt.where(MovimientoCaja.created_at >= desde)
    if hasta is not None:
        stmt = stmt.where(MovimientoCaja.created_at < hasta)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _filas_liquidaciones(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> list[dict[str, Any]]:
    stmt = select(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant_id)
    if desde is not None and hasta is not None:
        mes_desde, mes_hasta = _meses_del_rango(desde, hasta)
        stmt = stmt.where(LiquidacionOS.periodo >= mes_desde)
        stmt = stmt.where(LiquidacionOS.periodo <= mes_hasta)
    elif desde is not None:
        stmt = stmt.where(LiquidacionOS.periodo >= _mes_periodo(desde))
    elif hasta is not None:
        stmt = stmt.where(LiquidacionOS.periodo <= _mes_periodo(hasta))
    stmt = stmt.order_by(LiquidacionOS.created_at.asc(), LiquidacionOS.id.asc())
    result = await session.execute(stmt)
    filas: list[dict[str, Any]] = []
    for liq in result.scalars().all():
        filas.append(
            {
                "liquidacion_id": str(liq.id),
                "obra_social": liq.obra_social,
                "periodo": liq.periodo,
                "estado": liq.estado,
                "total": _decimal_str(liq.total),
                "total_reconocido": _decimal_str(liq.total_reconocido)
                if liq.total_reconocido is not None
                else None,
                "turnos_sin_cobertura": int(liq.turnos_sin_cobertura or 0),
                "observaciones": sanitizar_phi(liq.observaciones),
                "created_at": _iso(liq.created_at),
            }
        )
    return filas


async def _contar_liquidaciones(
    session: AsyncSession, tenant_id: uuid.UUID, desde: datetime | None, hasta: datetime | None
) -> int:
    stmt = (
        select(func.count()).select_from(LiquidacionOS).where(LiquidacionOS.tenant_id == tenant_id)
    )
    if desde is not None and hasta is not None:
        mes_desde, mes_hasta = _meses_del_rango(desde, hasta)
        stmt = stmt.where(LiquidacionOS.periodo >= mes_desde)
        stmt = stmt.where(LiquidacionOS.periodo <= mes_hasta)
    elif desde is not None:
        stmt = stmt.where(LiquidacionOS.periodo >= _mes_periodo(desde))
    elif hasta is not None:
        stmt = stmt.where(LiquidacionOS.periodo <= _mes_periodo(hasta))
    result = await session.execute(stmt)
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# Helpers de serialización
# ---------------------------------------------------------------------------


def _iso(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.astimezone(UTC).isoformat() if valor.tzinfo else valor.isoformat()
    return str(valor)


def _decimal_str(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return str(valor)
    return str(valor)


def _csv_bytes(columnas: Sequence[str], filas: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=",", quotechar='"', lineterminator="\r\n")
    escritor.writerow(list(columnas))
    for fila in filas:
        escritor.writerow([_csv_valor(fila.get(col)) for col in columnas])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _csv_valor(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return str(valor)
    return str(valor)


def _json_bytes(filas: list[dict[str, Any]]) -> bytes:
    # Decimal ya convertido a str en filas; asegurar que no queden Decimal.
    serializables = [_json_safe(fila) for fila in filas]
    return json.dumps(serializables, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


async def contar_filas_dataset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    dataset: str,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> int:
    if dataset not in DATASETS_VALIDOS:
        raise EntidadInvalida(
            "Che, el dataset tiene que ser uno de: " + ", ".join(DATASETS_VALIDOS) + "."
        )
    if dataset == "agenda":
        return await _contar_agenda(session, tenant_id, desde, hasta)
    if dataset == "pacientes":
        return await _contar_pacientes(session, tenant_id)
    if dataset == "caja":
        return await _contar_caja(session, tenant_id, desde, hasta)
    return await _contar_liquidaciones(session, tenant_id, desde, hasta)


async def exportar_dataset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    dataset: str,
    formato: str = "csv",
    desde: str | datetime | None = None,
    hasta: str | datetime | None = None,
    opaco: str | None = None,
) -> ExportacionDataset:
    """Arma en memoria el archivo del dataset pedido (D4, R8, R9)."""
    if dataset not in DATASETS_VALIDOS:
        raise EntidadInvalida(
            "Che, el dataset tiene que ser uno de: " + ", ".join(DATASETS_VALIDOS) + "."
        )
    formato_limpio = (formato or "csv").strip().lower()
    if formato_limpio not in ("csv", "json"):
        raise EntidadInvalida("Che, el formato tiene que ser 'csv' o 'json'.")

    # Parseo y validación del rango (D13).
    desde_dt = _parse_fecha(desde) if isinstance(desde, str) else desde
    hasta_dt = _parse_fecha(hasta) if isinstance(hasta, str) else hasta

    if dataset != "pacientes":
        if desde_dt is None and hasta_dt is None:
            desde_dt, hasta_dt = _default_periodo(dataset)
        else:
            _validar_rango(dataset, desde_dt, hasta_dt)
    else:
        # pacientes ignora el período (D4/D13).
        desde_dt = None
        hasta_dt = None

    # Filas.
    if dataset == "agenda":
        filas = await _filas_agenda(session, tenant_id, desde_dt, hasta_dt)
    elif dataset == "pacientes":
        filas = await _filas_pacientes(session, tenant_id)
    elif dataset == "caja":
        filas = await _filas_caja(session, tenant_id, desde_dt, hasta_dt)
    else:
        filas = await _filas_liquidaciones(session, tenant_id, desde_dt, hasta_dt)

    columnas = COLUMNAS_POR_DATASET[dataset]
    opaco_final = opaco or str(uuid.uuid4())
    periodo = _periodo_filename(desde_dt, hasta_dt, dataset)
    ext = formato_limpio

    if formato_limpio == "csv":
        contenido = _csv_bytes(columnas, filas)
        media_type = "text/csv; charset=utf-8"
    else:
        contenido = _json_bytes(filas)
        media_type = "application/json"

    nombre = _nombre_archivo(dataset, periodo, opaco_final, ext)
    return ExportacionDataset(
        contenido=contenido,
        media_type=media_type,
        nombre_archivo=nombre,
        nombre_legible=nombre,
        filas=len(filas),
    )


# Alias de compatibilidad con posibles nombres de tests.
exportar_dataset = exportar_dataset
generar_exportacion = exportar_dataset
armar_exportacion = exportar_dataset
exportar = exportar_dataset


def clave_job(tenant_id: Any, job_id: str) -> str:
    return f"exportacion:job:{tenant_id}:{job_id}"


async def leer_job_exportacion(redis: Any, tenant_id: Any, job_id: str) -> dict[str, Any] | None:
    """Lee el hash del job desde Redis (None si no existe o venció)."""
    try:
        data = await redis.hgetall(clave_job(tenant_id, job_id))
    except Exception:
        return None
    if not data:
        return None
    return dict(data)


def _purgar_exportaciones_sync() -> None:
    """Borra archivos de exportaci\u00f3n con antig\u00fcedad mayor a 24 h (D6, D5.5)."""
    import time

    directorio = EXPORTACIONES_DIR
    if not directorio or not os.path.isdir(directorio):
        return
    corte = time.time() - JOB_TTL_SEGUNDOS
    try:
        for nombre in os.listdir(directorio):
            ruta = os.path.join(directorio, nombre)
            if not os.path.isfile(ruta):
                continue
            try:
                if os.stat(ruta).st_mtime < corte:
                    os.remove(ruta)
            except OSError:
                continue
    except OSError:
        return


async def purgar_exportaciones_vencidas() -> None:
    await asyncio.to_thread(_purgar_exportaciones_sync)
