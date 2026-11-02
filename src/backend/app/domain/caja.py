"""Modelos de dominio de Señas y Caja diaria (C-11, US-030 / US-031).

Cumple:
- RN-PA-01 / RN-PA-04: la seña vive atada al turno con grafo cerrado de estados.
- RN-PA-05: todo cobro genera su movimiento de caja conciliado.
- R7: `movimiento_caja` es append-only (sin `updated_at` ni hard delete).
- R8: los montos son `Decimal` persistidos con `Numeric(12, 2)`; nunca floats.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin, ahora_utc
from app.infrastructure.db.base import Base


class EstadoSena(enum.StrEnum):
    """Estados del ciclo de vida de una seña atada a la cita (RN-PA-01)."""

    PENDIENTE = "pendiente"
    COBRADA = "cobrada"
    APLICADA = "aplicada"
    DEVUELTA = "devuelta"
    VENCIDA = "vencida"


_GRAFO_SENA: dict[EstadoSena, frozenset[EstadoSena]] = {
    EstadoSena.PENDIENTE: frozenset(
        {
            EstadoSena.COBRADA,
            EstadoSena.VENCIDA,
            EstadoSena.DEVUELTA,
        }
    ),
    EstadoSena.COBRADA: frozenset({EstadoSena.APLICADA, EstadoSena.DEVUELTA}),
    EstadoSena.APLICADA: frozenset(),
    EstadoSena.DEVUELTA: frozenset(),
    EstadoSena.VENCIDA: frozenset(),
}


def es_transicion_sena_valida(
    actual: EstadoSena | str,
    nuevo: EstadoSena | str,
) -> bool:
    """Devuelve True si la transición de estado de la seña está permitida en el grafo."""
    try:
        est_actual = EstadoSena(actual)
        est_nuevo = EstadoSena(nuevo)
    except ValueError:
        return False
    return est_nuevo in _GRAFO_SENA.get(est_actual, frozenset())


class TipoMovimientoCaja(enum.StrEnum):
    """Signo del movimiento de caja (RN-PA-05)."""

    INGRESO = "ingreso"
    EGRESO = "egreso"


class MedioPago(enum.StrEnum):
    """Medio por el que se cobra o paga un movimiento de caja (§04)."""

    EFECTIVO = "efectivo"
    DEBITO = "debito"
    CREDITO = "credito"
    TRANSFERENCIA = "transferencia"
    MP = "mp"


class EstadoCierreCaja(enum.StrEnum):
    """Estados del cierre diario de caja: abierto (mutable) o cerrado (inmutable)."""

    ABIERTO = "abierto"
    CERRADO = "cerrado"


class Sena(Base, TenantMixin, AuditMixin):
    """Seña de una cita: 1:1 con `turno` (RN-PA-02, §04)."""

    __tablename__ = "sena"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    turno_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="RESTRICT"), nullable=False
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoSena.PENDIENTE.value
    )
    # `mp_payment_id` llega con C-12 (webhooks Mercado Pago): único para idempotencia (RN-PA-03).
    mp_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("turno_id", name="uq_sena_turno_id"),
        UniqueConstraint("mp_payment_id", name="uq_sena_mp_payment_id"),
        CheckConstraint(
            "estado IN ('pendiente', 'cobrada', 'aplicada', 'devuelta', 'vencida')",
            name="ck_sena_estado_valido",
        ),
        CheckConstraint("monto > 0", name="ck_sena_monto_positivo"),
        Index("ix_sena_tenant_estado", "tenant_id", "estado"),
    )


class CierreCaja(Base, TenantMixin, AuditMixin):
    """Cierre diario de caja por consultorio: un registro por fecha (RN-PA-05, design D3)."""

    __tablename__ = "cierre_caja"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    total_sistema: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_contado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    diferencia: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoCierreCaja.ABIERTO.value
    )
    abierto_por: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    cerrado_por: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True
    )
    cerrado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reabierto_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "fecha", name="uq_cierre_caja_tenant_fecha"),
        CheckConstraint(
            "estado IN ('abierto', 'cerrado')",
            name="ck_cierre_caja_estado_valido",
        ),
        # D3: un cierre `cerrado` es inmutable y siempre tiene contado, diferencia y actor/hora.
        CheckConstraint(
            "(estado <> 'cerrado') OR (total_contado IS NOT NULL AND diferencia IS NOT NULL "
            "AND cerrado_por IS NOT NULL AND cerrado_at IS NOT NULL)",
            name="ck_cierre_caja_cierre_completo",
        ),
    )


class MovimientoCaja(Base, TenantMixin):
    """Movimiento de caja append-only: ingreso/egreso por medio de pago (RN-PA-05, R7)."""

    __tablename__ = "movimiento_caja"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    concepto: Mapped[str] = mapped_column(String(160), nullable=False)
    medio: Mapped[str] = mapped_column(String(16), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="RESTRICT"), nullable=True
    )
    sena_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("sena.id", ondelete="RESTRICT"), nullable=True
    )
    # `cobro_mp_id` apunta a `cobro_mp` (C-12): sin FK hasta que exista esa tabla.
    cobro_mp_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    cierre_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("cierre_caja.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=ahora_utc,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("tipo IN ('ingreso', 'egreso')", name="ck_movimiento_caja_tipo_valido"),
        CheckConstraint(
            "medio IN ('efectivo', 'debito', 'credito', 'transferencia', 'mp')",
            name="ck_movimiento_caja_medio_valido",
        ),
        CheckConstraint("monto > 0", name="ck_movimiento_caja_monto_positivo"),
        CheckConstraint(
            "length(trim(concepto)) > 0",
            name="ck_movimiento_caja_concepto_no_vacio",
        ),
        Index("ix_movimiento_caja_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_movimiento_caja_tenant_cierre_id", "tenant_id", "cierre_id"),
        Index("ix_movimiento_caja_turno_id", "turno_id"),
    )
