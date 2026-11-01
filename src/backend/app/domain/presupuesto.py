"""Modelos de dominio de Presupuestos y Planes de Tratamiento (C-10, US-022).

Cumple:
- RN-OS-01 / R8: `a_cargo = precio_unit * cantidad - cobertura_os` calculado en servidor.
- RN-CL-04: Aceptación con invasiva exige consentimiento firmado previo.
"""

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class EstadoPresupuesto(enum.StrEnum):
    """Estados del ciclo de vida de un presupuesto / plan de tratamiento (§04)."""

    BORRADOR = "borrador"
    PRESENTADO = "presentado"
    ACEPTADO = "aceptado"
    RECHAZADO = "rechazado"
    EN_CURSO = "en_curso"
    FINALIZADO = "finalizado"


_GRAFO_PRESUPUESTO: dict[EstadoPresupuesto, frozenset[EstadoPresupuesto]] = {
    EstadoPresupuesto.BORRADOR: frozenset(
        {
            EstadoPresupuesto.PRESENTADO,
            EstadoPresupuesto.ACEPTADO,
            EstadoPresupuesto.RECHAZADO,
        }
    ),
    EstadoPresupuesto.PRESENTADO: frozenset(
        {
            EstadoPresupuesto.ACEPTADO,
            EstadoPresupuesto.RECHAZADO,
        }
    ),
    EstadoPresupuesto.ACEPTADO: frozenset(
        {
            EstadoPresupuesto.EN_CURSO,
            EstadoPresupuesto.FINALIZADO,
        }
    ),
    EstadoPresupuesto.RECHAZADO: frozenset(),
    EstadoPresupuesto.EN_CURSO: frozenset({EstadoPresupuesto.FINALIZADO}),
    EstadoPresupuesto.FINALIZADO: frozenset(),
}


def es_transicion_presupuesto_valida(
    actual: EstadoPresupuesto | str,
    nuevo: EstadoPresupuesto | str,
) -> bool:
    """Devuelve True si la transición de estado del presupuesto está permitida en el grafo."""
    try:
        est_actual = EstadoPresupuesto(actual)
        est_nuevo = EstadoPresupuesto(nuevo)
    except ValueError:
        return False
    return est_nuevo in _GRAFO_PRESUPUESTO.get(est_actual, frozenset())


class Presupuesto(Base, TenantMixin, AuditMixin):
    """Cabecera de un presupuesto y plan de tratamiento odontológico (§04)."""

    __tablename__ = "presupuesto"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="RESTRICT"), nullable=False
    )
    obra_social: Mapped[str | None] = mapped_column(String(160), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoPresupuesto.BORRADOR.value
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_cobertura_os: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_a_cargo: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    validez_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('borrador', 'presentado', 'aceptado', "
            "'rechazado', 'en_curso', 'finalizado')",
            name="ck_presupuesto_estado_valido",
        ),
        CheckConstraint(
            "total >= 0 AND total_cobertura_os >= 0 AND total_a_cargo >= 0",
            name="ck_presupuesto_totales_no_negativos",
        ),
        Index(
            "ix_presupuesto_tenant_paciente_estado",
            "tenant_id",
            "paciente_id",
            "estado",
        ),
    )


class PresupuestoItem(Base, TenantMixin):
    """Renglón o prestación incluida en un presupuesto con cálculo de cobertura OS (§04)."""

    __tablename__ = "presupuesto_item"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("presupuesto.id", ondelete="CASCADE"), nullable=False
    )
    prestacion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prestacion.id", ondelete="RESTRICT"), nullable=False
    )
    pieza_fdi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    precio_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cobertura_os: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    a_cargo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("cantidad >= 1", name="ck_presupuesto_item_cantidad_positiva"),
        CheckConstraint(
            "precio_unit >= 0 AND cobertura_os >= 0 AND a_cargo >= 0",
            name="ck_presupuesto_item_montos_no_negativos",
        ),
        Index("ix_presupuesto_item_presupuesto_id", "presupuesto_id"),
    )


class PresupuestoTurno(Base, TenantMixin):
    """Asociación N–N entre un Presupuesto y los Turnos (citas del plan de tratamiento)."""

    __tablename__ = "presupuesto_turno"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("presupuesto.id", ondelete="CASCADE"), nullable=False
    )
    turno_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="CASCADE"), nullable=False
    )
    presupuesto_item_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("presupuesto_item.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "presupuesto_id",
            "turno_id",
            name="uq_presupuesto_turno_presupuesto_turno",
        ),
        Index("ix_presupuesto_turno_presupuesto_id", "presupuesto_id"),
        Index("ix_presupuesto_turno_turno_id", "turno_id"),
    )
