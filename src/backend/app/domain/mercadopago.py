"""Modelos de dominio de integración con Mercado Pago (C-12, US-031).

Cumple:
- RN-PA-03: idempotencia de pagos respaldada por `mp_payment_id` único.
- RN-PA-05: conciliación de cobros con detección de discrepancias.
- R7: registros de cobros son append-only (con payload crudo para auditoría).
- R8: montos en `Decimal` (`Numeric(12, 2)`).
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.domain.mixins import GUID, TenantMixin, ahora_utc
from app.infrastructure.db.base import Base


class EstadoMP(enum.StrEnum):
    """Estados estándar de pago en Mercado Pago."""

    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class EstadoConciliacionMP(enum.StrEnum):
    """Estados de conciliación interna del cobro de Mercado Pago."""

    PENDIENTE = "pendiente"
    CONCILIADO = "conciliado"
    DISCREPANCIA = "discrepancia"


class CobroMP(Base, TenantMixin):
    """Registro de cobro o intento de cobro procesado vía Mercado Pago."""

    __tablename__ = "cobro_mp"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    turno_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("turno.id", ondelete="SET NULL"), nullable=True
    )
    sena_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("sena.id", ondelete="SET NULL"), nullable=True
    )
    mp_payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mp_preference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    estado_mp: Mapped[str] = mapped_column(String(24), nullable=False)
    estado_conciliacion: Mapped[str] = mapped_column(
        String(24), nullable=False, default=EstadoConciliacionMP.PENDIENTE.value
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=ahora_utc
    )

    __table_args__ = (
        UniqueConstraint("mp_payment_id", name="uq_cobro_mp_payment_id"),
        CheckConstraint(
            "estado_mp IN ('approved', 'pending', 'rejected', 'refunded', 'cancelled')",
            name="ck_cobro_mp_estado_mp_valido",
        ),
        CheckConstraint(
            "estado_conciliacion IN ('pendiente', 'conciliado', 'discrepancia')",
            name="ck_cobro_mp_estado_conciliacion_valido",
        ),
        CheckConstraint("monto > 0", name="ck_cobro_mp_monto_positivo"),
        Index("ix_cobro_mp_payment_id", "mp_payment_id"),
        Index("ix_cobro_mp_tenant_conciliacion", "tenant_id", "estado_conciliacion"),
    )
