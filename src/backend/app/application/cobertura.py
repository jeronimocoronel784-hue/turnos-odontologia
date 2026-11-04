"""Servicio compartido de resolución de cobertura (C-13, D1: única fuente de verdad).

Cumple:
- RN-OS-01 / R8: presupuestos (C-10), saldo de atención (C-11) y liquidaciones (C-13) resuelven
  la cobertura con la misma función pura de `app.domain.cobertura_os`; nadie duplica el cálculo.
- R4: todo lookup filtra por el `tenant_id` del token y jamás cruza consultorios.
- D2: el arancel vencido se usa con advertencia; la cobertura futura es particular.

Los adaptadores (`calcular_montos_item_presupuesto`) conservan firma y retorno para no tocar
los casos de uso de C-10/C-11.
"""

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cobertura_os import (
    CoberturaOS,
    ResolucionCobertura,
    resolver_cobertura_desde_candidatas,
)
from app.domain.mixins import asegurar_utc
from app.domain.prestacion import Prestacion
from app.domain.turno import Turno
from app.shared.exceptions import EntidadInvalida, NoEncontrado

MENSAJE_PRESTACION = "Che, no encontramos la prestación indicada."
MENSAJE_PRESTACION_PRESUPUESTO = "Che, no encontramos la prestación indicada para el presupuesto."


def _fecha_de_referencia(fecha_referencia: date | None) -> date:
    """Fecha de corte del arancel: la indicada o hoy en UTC (coherente con `Turno.inicio`)."""
    return fecha_referencia or datetime.now(UTC).date()


def _obra_social_normalizada(obra_social: str | None) -> str:
    """Normaliza la obra social: `None` y vacíos son paciente particular."""
    return (obra_social or "").strip()


async def _candidatas_de(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_ids: Collection[uuid.UUID],
    obra_social: str,
) -> dict[uuid.UUID, list[CoberturaOS]]:
    """Trae en UNA consulta los convenios activos de la OS para las prestaciones pedidas.

    Incluye los históricos a propósito: la regla del arancel vencido (D2) se decide en el
    dominio, no en el `WHERE`.
    """
    if not prestacion_ids or not obra_social:
        return {}
    os_limpia = obra_social.strip().lower()
    filas = (
        (
            await session.execute(
                select(CoberturaOS)
                .where(
                    CoberturaOS.tenant_id == tenant_id,
                    CoberturaOS.prestacion_id.in_(list(prestacion_ids)),
                    CoberturaOS.activa.is_(True),
                    func.lower(CoberturaOS.obra_social) == os_limpia,
                )
                .order_by(CoberturaOS.vigencia_desde.asc(), CoberturaOS.id.asc())
            )
        )
        .scalars()
        .all()
    )
    agrupadas: dict[uuid.UUID, list[CoberturaOS]] = {}
    for convenio in filas:
        agrupadas.setdefault(convenio.prestacion_id, []).append(convenio)
    return agrupadas


async def _prestaciones_de(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_ids: Collection[uuid.UUID],
) -> dict[uuid.UUID, Prestacion]:
    """Trae en UNA consulta las prestaciones del tenant indexadas por id (R4)."""
    if not prestacion_ids:
        return {}
    filas = (
        (
            await session.execute(
                select(Prestacion).where(
                    Prestacion.tenant_id == tenant_id,
                    Prestacion.id.in_(list(prestacion_ids)),
                )
            )
        )
        .scalars()
        .all()
    )
    return {prestacion.id: prestacion for prestacion in filas}


def _resolver(
    *,
    precio_particular: Decimal,
    candidatas: Iterable[CoberturaOS],
    fecha_referencia: date,
    obra_social: str,
    cantidad: int,
) -> ResolucionCobertura:
    """Delega en la función pura del dominio (D1): el servicio sólo carga datos."""
    return resolver_cobertura_desde_candidatas(
        precio_particular=precio_particular,
        candidatas=candidatas,
        fecha_referencia=fecha_referencia,
        obra_social=obra_social,
        cantidad=cantidad,
    )


async def resolver_cobertura_prestacion(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    cantidad: int = 1,
    obra_social: str | None = None,
    fecha_referencia: date | None = None,
    mensaje_no_encontrada: str = MENSAJE_PRESTACION,
) -> ResolucionCobertura:
    """Resuelve la cobertura de una prestación del tenant (RN-OS-01, D2)."""
    prestacion = await session.get(Prestacion, prestacion_id)
    if prestacion is None or prestacion.tenant_id != tenant_id:
        raise NoEncontrado(mensaje_no_encontrada)

    os_normalizada = _obra_social_normalizada(obra_social)
    candidatas = await _candidatas_de(
        session,
        tenant_id=tenant_id,
        prestacion_ids=[prestacion.id],
        obra_social=os_normalizada,
    )
    return _resolver(
        precio_particular=prestacion.precio_particular,
        candidatas=candidatas.get(prestacion.id, []),
        fecha_referencia=_fecha_de_referencia(fecha_referencia),
        obra_social=os_normalizada,
        cantidad=cantidad,
    )


async def resolver_coberturas_lote(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_ids: Collection[uuid.UUID],
    obra_social: str | None = None,
    fecha_referencia: date | None = None,
) -> dict[uuid.UUID, ResolucionCobertura]:
    """Resuelve varias prestaciones en dos consultas (prestaciones + convenios), sin N+1.

    Cada resolución asume `cantidad = 1` (el caso de la liquidación, una fila por turno). Se
    devuelven sólo las prestaciones que existen en el tenant; el llamador decide qué hacer con
    las que falten (una liquidación las informa como sin cobertura).
    """
    prestaciones = await _prestaciones_de(
        session, tenant_id=tenant_id, prestacion_ids=prestacion_ids
    )
    if not prestaciones:
        return {}

    os_normalizada = _obra_social_normalizada(obra_social)
    candidatas = await _candidatas_de(
        session,
        tenant_id=tenant_id,
        prestacion_ids=list(prestaciones),
        obra_social=os_normalizada,
    )
    fecha = _fecha_de_referencia(fecha_referencia)
    return {
        prestacion_id: _resolver(
            precio_particular=prestacion.precio_particular,
            candidatas=candidatas.get(prestacion_id, []),
            fecha_referencia=fecha,
            obra_social=os_normalizada,
            cantidad=1,
        )
        for prestacion_id, prestacion in prestaciones.items()
    }


async def calcular_montos_item_presupuesto(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID,
    cantidad: int,
    obra_social: str | None = None,
    fecha_referencia: date | None = None,
    mensaje_no_encontrada: str = MENSAJE_PRESTACION_PRESUPUESTO,
) -> tuple[Decimal, Decimal, Decimal]:
    """Adaptador de C-10/C-11: `(precio_unit, cobertura_total, a_cargo_total)` en servidor.

    Conserva firma, mensaje de error y tupla de retorno históricos para no cambiar el contrato
    de presupuestos ni de caja (RN-OS-01, R8).
    """
    resolucion = await resolver_cobertura_prestacion(
        session,
        tenant_id=tenant_id,
        prestacion_id=prestacion_id,
        cantidad=cantidad,
        obra_social=obra_social,
        fecha_referencia=fecha_referencia,
        mensaje_no_encontrada=mensaje_no_encontrada,
    )
    return resolucion.precio_particular, resolucion.cobertura, resolucion.monto_a_cargo


@dataclass(frozen=True)
class ConsultaCobertura:
    """Resultado del lookup de cobertura para agenda/cobro (US-040)."""

    prestacion_id: uuid.UUID
    obra_social: str | None
    resolucion: ResolucionCobertura


async def consultar_cobertura(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    prestacion_id: uuid.UUID | None = None,
    turno_id: uuid.UUID | None = None,
    obra_social: str | None = None,
    fecha: date | None = None,
    cantidad: int = 1,
) -> ConsultaCobertura:
    """Lookup de cobertura por prestación o por turno (US-040, RN-OS-01).

    Con `turno_id` se derivan la prestación y la fecha de referencia del turno, así la advertencia
    de arancel vencido corresponde al momento real de la atención (D2).
    """
    fecha_turno: date | None = None
    if turno_id is not None:
        turno = (
            await session.execute(
                select(Turno).where(Turno.id == turno_id, Turno.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if turno is None:
            raise NoEncontrado("Che, no encontramos ese turno en el consultorio.")
        if prestacion_id is not None and prestacion_id != turno.prestacion_id:
            raise EntidadInvalida(
                "Che, el turno indicado no corresponde a la prestación consultada."
            )
        prestacion_id = turno.prestacion_id
        fecha_turno = asegurar_utc(turno.inicio).date()

    if prestacion_id is None:
        raise EntidadInvalida("Che, indicá la prestación o el turno para consultar la cobertura.")

    os_normalizada = _obra_social_normalizada(obra_social)
    resolucion = await resolver_cobertura_prestacion(
        session,
        tenant_id=tenant_id,
        prestacion_id=prestacion_id,
        cantidad=cantidad,
        obra_social=os_normalizada,
        fecha_referencia=fecha or fecha_turno,
    )
    return ConsultaCobertura(
        prestacion_id=prestacion_id,
        obra_social=os_normalizada or None,
        resolucion=resolucion,
    )
