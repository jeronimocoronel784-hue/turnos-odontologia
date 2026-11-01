"""Modelo Bloqueo horario de profesional y/o sillón (RN-AG-03)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class MotivoBloqueo(enum.StrEnum):
    """Motivos de bloqueo de agenda odontológica."""

    FERIADO = "feriado"
    VACACIONES = "vacaciones"
    MANUAL = "manual"
    ADMINISTRATIVO = "administrativo"


class Bloqueo(Base, TenantMixin, AuditMixin):
    """Rango horario no reservable para un profesional, un sillón o ambos."""

    __tablename__ = "bloqueo"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=True
    )
    sillon_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("sillon.id", ondelete="CASCADE"), nullable=True
    )
    desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    motivo: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MotivoBloqueo.MANUAL.value
    )
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("hasta > desde", name="ck_bloqueo_rango_valido"),
        CheckConstraint(
            "profesional_id IS NOT NULL OR sillon_id IS NOT NULL",
            name="ck_bloqueo_objetivo_no_nulo",
        ),
        Index("ix_bloqueo_tenant_desde_hasta", "tenant_id", "desde", "hasta"),
    )
