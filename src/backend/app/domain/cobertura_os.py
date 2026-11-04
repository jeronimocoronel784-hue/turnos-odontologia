"""Cobertura de obra social: padrón de convenios + resolución del arancel aplicable.

Cumple:
- RN-OS-01 / R8: `cobertura = min(precio_particular, arancel)` y `monto_a_cargo` se calculan
  siempre en el servidor con `Decimal`; el cliente nunca manda montos.
- D2 (C-13): el arancel vencido NO se descarta: se usa el último cargado y se devuelve la
  advertencia para que recepción la informe (Flujo 5). La cobertura futura es particular.
"""

import enum
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base
from app.shared.montos import CENTAVOS, CERO, monto_2dp


class EstadoArancel(enum.StrEnum):
    """Vigencia del arancel que se aplicó al resolver la cobertura (RN-OS-01, D2)."""

    VIGENTE = "vigente"
    VENCIDO = "vencido"
    SIN_COBERTURA = "sin_cobertura"


@dataclass(frozen=True)
class ResolucionCobertura:
    """Resultado de resolver la cobertura de una prestación contra el padrón (R8)."""

    precio_particular: Decimal
    cobertura: Decimal
    monto_a_cargo: Decimal
    estado_arancel: EstadoArancel
    cobertura_id: uuid.UUID | None = None
    arancel: Decimal | None = None
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    advertencia: str | None = None

    @property
    def arancel_vencido(self) -> bool:
        """True si se facturó con un arancel cuya vigencia ya expiró (snapshot del detalle)."""
        return self.estado_arancel is EstadoArancel.VENCIDO


class CoberturaOS(Base, TenantMixin, AuditMixin):
    """Convenio con obra social para una prestación del consultorio."""

    __tablename__ = "cobertura_os"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    obra_social: Mapped[str] = mapped_column(String(160), nullable=False)
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prestacion.id", ondelete="RESTRICT"), nullable=False
    )
    arancel: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    copago: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("arancel >= 0 AND copago >= 0", name="ck_cobertura_montos_no_negativos"),
        CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde",
            name="ck_cobertura_vigencia_ordenada",
        ),
        Index("ix_cobertura_os_tenant_os", "tenant_id", "obra_social"),
        Index("ix_cobertura_os_tenant_prestacion", "tenant_id", "prestacion_id"),
    )


def _clave_orden(convenio: CoberturaOS) -> tuple[date, date, str]:
    """Ordena por arancel más reciente: `vigencia_desde` y luego `vigencia_hasta` (D2)."""
    return (convenio.vigencia_desde, convenio.vigencia_hasta or date.max, str(convenio.id))


def _sin_cobertura(
    *,
    precio_unit: Decimal,
    subtotal: Decimal,
    advertencia: str | None = None,
) -> ResolucionCobertura:
    """Modo particular: sin convenio aplicable, `monto_a_cargo` es el precio completo."""
    return ResolucionCobertura(
        precio_particular=precio_unit,
        cobertura=CERO,
        monto_a_cargo=subtotal,
        estado_arancel=EstadoArancel.SIN_COBERTURA,
        advertencia=advertencia,
    )


def resolver_cobertura_desde_candidatas(
    *,
    precio_particular: Decimal,
    candidatas: Iterable[CoberturaOS],
    fecha_referencia: date,
    obra_social: str,
    cantidad: int = 1,
) -> ResolucionCobertura:
    """Resuelve la cobertura aplicable a una prestación (función pura, D1 + D2).

    Orden de resolución:
    1. Convenio `activa` de la misma obra social (comparada en minúsculas) con
       `vigencia_desde <= fecha` y vigente a la fecha -> `vigente`.
    2. Si no hay vigente pero sí histórico -> `vencido`: se usa el de `vigencia_desde`
       más reciente y se devuelve la advertencia con la fecha de vencimiento (Flujo 5).
    3. Sin convenio previo, o sólo con cobertura futura -> `sin_cobertura` (particular).
    """
    if cantidad < 1:
        raise ValueError("La cantidad tiene que ser al menos 1.")

    precio_unit = monto_2dp(precio_particular)
    subtotal = (precio_unit * Decimal(cantidad)).quantize(CENTAVOS)
    os_limpia = obra_social.strip().lower()
    if not os_limpia:
        return _sin_cobertura(precio_unit=precio_unit, subtotal=subtotal)

    aplicables = [
        convenio
        for convenio in candidatas
        if convenio.activa
        and convenio.obra_social.strip().lower() == os_limpia
        and convenio.vigencia_desde <= fecha_referencia
    ]
    vigentes = [
        convenio
        for convenio in aplicables
        if convenio.vigencia_hasta is None or convenio.vigencia_hasta >= fecha_referencia
    ]

    if vigentes:
        elegida, estado = max(vigentes, key=_clave_orden), EstadoArancel.VIGENTE
    elif aplicables:
        elegida, estado = max(aplicables, key=_clave_orden), EstadoArancel.VENCIDO
    else:
        futuras = [
            convenio
            for convenio in candidatas
            if convenio.activa
            and convenio.obra_social.strip().lower() == os_limpia
            and convenio.vigencia_desde > fecha_referencia
        ]
        advertencia = None
        if futuras:
            inicio = min(convenio.vigencia_desde for convenio in futuras).strftime("%d/%m/%Y")
            advertencia = (
                f"El convenio con {os_limpia.upper()} empieza a regir el {inicio}: "
                "hasta esa fecha la prestación se cobra como particular."
            )
        return _sin_cobertura(precio_unit=precio_unit, subtotal=subtotal, advertencia=advertencia)

    arancel_unit = monto_2dp(elegida.arancel)
    cobertura_unit = min(precio_unit, arancel_unit)
    cobertura = (cobertura_unit * Decimal(cantidad)).quantize(CENTAVOS)
    monto_a_cargo = max(CERO, subtotal - cobertura).quantize(CENTAVOS)

    advertencia = None
    if estado is EstadoArancel.VENCIDO:
        vencimiento = (
            elegida.vigencia_hasta.strftime("%d/%m/%Y") if elegida.vigencia_hasta else "sin fecha"
        )
        advertencia = (
            f"El arancel de {os_limpia.upper()} para esta prestación venció el {vencimiento}: "
            f"aplicamos el último cargado (${arancel_unit}). "
            "Confirmalo con la obra social antes de facturar."
        )

    return ResolucionCobertura(
        precio_particular=precio_unit,
        cobertura=cobertura,
        monto_a_cargo=monto_a_cargo,
        estado_arancel=estado,
        cobertura_id=elegida.id,
        arancel=arancel_unit,
        vigencia_desde=elegida.vigencia_desde,
        vigencia_hasta=elegida.vigencia_hasta,
        advertencia=advertencia,
    )
