"""Modelo Paciente: registro, datos de contacto, opt-in WA y relación 1:1 con FichaClinica."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.domain.ficha_clinica import FichaClinica


class Paciente(Base, TenantMixin, AuditMixin):
    """Paciente del consultorio odontológico (sin login de usuario en v1)."""

    __tablename__ = "paciente"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    dni: Mapped[str] = mapped_column(String(20), nullable=False)
    telefono: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha_nac: Mapped[date | None] = mapped_column(Date, nullable=True)
    obra_social_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    nro_afiliado: Mapped[str | None] = mapped_column(String(60), nullable=True)
    optin_wa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ficha_clinica: Mapped["FichaClinica"] = relationship(
        "FichaClinica",
        back_populates="paciente",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "dni", name="uq_paciente_tenant_dni"),
        Index("ix_paciente_tenant_dni", "tenant_id", "dni"),
        Index("ix_paciente_tenant_telefono", "tenant_id", "telefono"),
        Index("ix_paciente_tenant_activo", "tenant_id", "activo"),
    )


def puede_enviar_whatsapp(paciente: Paciente, es_transaccional_critico: bool = False) -> bool:
    """Evalúa la regla RN-CO-01.

    Ningún mensaje automático sale sin optin_wa = True;
    la baja (STOP) corta envíos salvo transaccionales exigidos.
    """
    if not paciente.activo:
        return False
    if es_transaccional_critico:
        return True
    return bool(paciente.optin_wa)
