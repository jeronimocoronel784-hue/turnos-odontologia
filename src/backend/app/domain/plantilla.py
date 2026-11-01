"""Entidad Plantilla: plantillas versionadas de mensajería WA y email (C-08, RN-CO-04)."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class CodigoPlantilla(enum.StrEnum):
    """Códigos canónicos de las 5 plantillas base del consultorio."""

    CONFIRMACION_RESERVA = "confirmacion_reserva"
    RECORDATORIO_24H = "recordatorio_24h"
    CANCELACION_TURNO = "cancelacion_turno"
    HUECO_LISTA_ESPERA = "hueco_lista_espera"
    SENA_PENDIENTE = "sena_pendiente"


class Plantilla(TenantMixin, AuditMixin, Base):
    """Plantilla versionada para envío de mensajes por WhatsApp o email (RN-CO-04)."""

    __tablename__ = "plantilla"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_plantilla_version_positiva"),
        CheckConstraint("canal IN ('wa', 'email')", name="ck_plantilla_canal_valido"),
        UniqueConstraint(
            "tenant_id",
            "codigo",
            "canal",
            "version",
            name="uq_plantilla_tenant_codigo_canal_version",
        ),
        Index("ix_plantilla_tenant_codigo_activa", "tenant_id", "codigo", "activa"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    codigo: Mapped[str] = mapped_column(String(64), nullable=False)
    canal: Mapped[str] = mapped_column(String(16), nullable=False, default="wa")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    asunto: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
