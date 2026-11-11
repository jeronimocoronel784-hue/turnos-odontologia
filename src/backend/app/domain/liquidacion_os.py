"""Dominio de liquidaciones mensuales a obras sociales (C-13, US-041, RN-OS-02).

Cumple:
- RN-OS-02: un turno se reclama una sola vez por obra social y período (índice parcial en DB);
  sólo la anulación libera el reclamo (D9/D12).
- R7: la baja de un borrador es lógica (`anulada`), nunca un DELETE físico.
- R8: los montos son `Decimal` persistidos con `Numeric(12, 2)`; los totales los calcula el server.
- D4: grafo cerrado de estados; D5: membresía derivada del período calendario UTC.
- D6: un solo `borrador` simultáneo por OS/período (índice único parcial con `lower()`).
"""

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base
from app.shared.exceptions import EntidadInvalida

LARGO_PERIODO = 6
MENSAJE_PERIODO = "Che, el período tiene que tener el formato 'yyyymm' (por ejemplo 202611)."


class EstadoLiquidacionOS(enum.StrEnum):
    """Estados del ciclo de vida de una liquidación a obra social (D4, §04)."""

    BORRADOR = "borrador"
    PRESENTADA = "presentada"
    PAGADA = "pagada"
    CON_DEBITOS = "con_debitos"
    ANULADA = "anulada"


_GRAFO_LIQUIDACION_OS: dict[EstadoLiquidacionOS, frozenset[EstadoLiquidacionOS]] = {
    EstadoLiquidacionOS.BORRADOR: frozenset(
        {EstadoLiquidacionOS.PRESENTADA, EstadoLiquidacionOS.ANULADA}
    ),
    EstadoLiquidacionOS.PRESENTADA: frozenset(
        {EstadoLiquidacionOS.PAGADA, EstadoLiquidacionOS.CON_DEBITOS}
    ),
    EstadoLiquidacionOS.CON_DEBITOS: frozenset({EstadoLiquidacionOS.PAGADA}),
    EstadoLiquidacionOS.PAGADA: frozenset(),
    EstadoLiquidacionOS.ANULADA: frozenset(),
}


def es_transicion_liquidacion_valida(
    actual: EstadoLiquidacionOS | str,
    nuevo: EstadoLiquidacionOS | str,
) -> bool:
    """True si la transición de estado de la liquidación está permitida en el grafo (D4)."""
    try:
        est_actual = EstadoLiquidacionOS(actual)
        est_nuevo = EstadoLiquidacionOS(nuevo)
    except ValueError:
        return False
    return est_nuevo in _GRAFO_LIQUIDACION_OS.get(est_actual, frozenset())


def periodo_desde_fecha(fecha: date) -> str:
    """Período `yyyymm` del mes calendario de una fecha (D5)."""
    return f"{fecha.year:04d}{fecha.month:02d}"


def periodo_valido(periodo: str) -> bool:
    """True si el período es `yyyymm` con mes 01..12 (el formato lo valida además Pydantic)."""
    if len(periodo) != LARGO_PERIODO or not periodo.isdigit():
        return False
    mes = int(periodo[4:])
    return 1 <= mes <= 12


def rango_periodo(periodo: str) -> tuple[datetime, datetime]:
    """Rango UTC semiabierto `[primer día del período, primer día del siguiente)` (D5)."""
    if not periodo_valido(periodo):
        raise EntidadInvalida(MENSAJE_PERIODO)
    anio = int(periodo[:4])
    mes = int(periodo[4:])
    desde = datetime(anio, mes, 1, tzinfo=UTC)
    hasta = (
        datetime(anio + 1, 1, 1, tzinfo=UTC)
        if mes == 12
        else datetime(anio, mes + 1, 1, tzinfo=UTC)
    )
    return desde, hasta


class LiquidacionOS(Base, TenantMixin, AuditMixin):
    """Cabecera de la liquidación mensual de una obra social (§04, D3/D6)."""

    __tablename__ = "liquidacion_os"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    obra_social: Mapped[str] = mapped_column(String(160), nullable=False)
    periodo: Mapped[str] = mapped_column(String(LARGO_PERIODO), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoLiquidacionOS.BORRADOR.value
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_reconocido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # D12: el conteo de turnos sin cobertura del alta queda persistido (no se pierde al releer).
    turnos_sin_cobertura: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    presentada_por: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True
    )
    presentada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resuelta_por: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True
    )
    resuelta_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulada_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('borrador', 'presentada', 'pagada', 'con_debitos', 'anulada')",
            name="ck_liquidacion_os_estado_valido",
        ),
        CheckConstraint(
            f"length(periodo) = {LARGO_PERIODO}",
            name="ck_liquidacion_os_periodo_largo",
        ),
        CheckConstraint(
            "total >= 0 AND (total_reconocido IS NULL OR total_reconocido >= 0) "
            "AND (total_reconocido IS NULL OR total_reconocido <= total)",
            name="ck_liquidacion_os_totales_no_negativos",
        ),
        CheckConstraint(
            "estado IN ('borrador', 'anulada') "
            "OR (presentada_por IS NOT NULL AND presentada_at IS NOT NULL)",
            name="ck_liquidacion_os_presentada_completa",
        ),
        CheckConstraint(
            "estado NOT IN ('pagada', 'con_debitos') "
            "OR (total_reconocido IS NOT NULL AND resuelta_por IS NOT NULL "
            "AND resuelta_at IS NOT NULL)",
            name="ck_liquidacion_os_resuelta_completa",
        ),
        CheckConstraint(
            "estado <> 'anulada' "
            "OR (anulada_motivo IS NOT NULL AND length(trim(anulada_motivo)) > 0)",
            name="ck_liquidacion_os_anulada_motivo",
        ),
        # D6: un solo borrador simultáneo por OS/período; las complementarias siguen permitidas.
        # D12: `lower(obra_social)` alinea el índice con la comparación de la app.
        Index(
            "uq_liquidacion_os_borrador",
            "tenant_id",
            text("lower(obra_social)"),
            "periodo",
            unique=True,
            sqlite_where=text("estado = 'borrador'"),
            postgresql_where=text("estado = 'borrador'"),
        ),
        Index("ix_liquidacion_os_tenant_os_periodo", "tenant_id", "obra_social", "periodo"),
        Index("ix_liquidacion_os_tenant_estado", "tenant_id", "estado"),
    )


class LiquidacionOSDetalle(Base, TenantMixin, AuditMixin):
    """Una fila por turno liquidado, con débitos y snapshot de arancel vencido (D2/D3)."""

    __tablename__ = "liquidacion_detalle"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    liquidacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("liquidacion_os.id", ondelete="RESTRICT"), nullable=False
    )
    turno_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="RESTRICT"), nullable=False
    )
    # Copias de la cabecera: habilitan el índice parcial de unicidad del reclamo (D3/D9).
    obra_social: Mapped[str] = mapped_column(String(160), nullable=False)
    periodo: Mapped[str] = mapped_column(String(LARGO_PERIODO), nullable=False)
    monto_reclamado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_reconocido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    debito_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    arancel_vencido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # D9/D12: el reclamo sigue vigente mientras la liquidación no esté `anulada`; el pago
    # no lo libera (sólo la anulación, que lo pasa a `false`).
    reclamado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        UniqueConstraint("liquidacion_id", "turno_id", name="uq_liquidacion_detalle_turno"),
        # RN-OS-02 / D9 / D12: un turno se reclama una sola vez por obra social y período.
        # `lower(obra_social)` evita el doble reclamo por diferencia de capitalización.
        Index(
            "uq_liquidacion_detalle_turno_reclamado",
            "tenant_id",
            "turno_id",
            text("lower(obra_social)"),
            "periodo",
            unique=True,
            sqlite_where=text("reclamado"),
            postgresql_where=text("reclamado"),
        ),
        CheckConstraint(
            "monto_reclamado >= 0 AND (monto_reconocido IS NULL OR "
            "(monto_reconocido >= 0 AND monto_reconocido <= monto_reclamado))",
            name="ck_liquidacion_detalle_montos",
        ),
        CheckConstraint(
            "monto_reconocido IS NULL OR monto_reconocido = monto_reclamado "
            "OR (debito_motivo IS NOT NULL AND length(trim(debito_motivo)) > 0)",
            name="ck_liquidacion_detalle_debito_motivo",
        ),
        CheckConstraint(
            f"length(periodo) = {LARGO_PERIODO}",
            name="ck_liquidacion_detalle_periodo_largo",
        ),
        Index("ix_liquidacion_detalle_liquidacion_id", "liquidacion_id"),
        Index("ix_liquidacion_detalle_tenant_turno", "tenant_id", "turno_id"),
    )
