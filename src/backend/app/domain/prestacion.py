"""Prestación o servicio odontológico: duración, precio, seña e invasividad."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class Prestacion(Base, TenantMixin, AuditMixin):
    """Servicio odontológico ofrecido por el consultorio."""

    __tablename__ = "prestacion"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_particular: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    requiere_sena: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monto_sena: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    invasiva: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_prestacion_tenant_nombre"),
        CheckConstraint("duracion_min > 0", name="ck_prestacion_duracion_positiva"),
        CheckConstraint("precio_particular >= 0", name="ck_prestacion_precio_no_negativo"),
        CheckConstraint(
            "(NOT requiere_sena) OR (monto_sena IS NOT NULL AND monto_sena > 0)",
            name="ck_prestacion_sena_valida",
        ),
        Index("ix_prestacion_tenant_activa", "tenant_id", "activa"),
    )
