"""Modelo FichaClinica: relación 1:1 con Paciente y contenedor clínico inicial."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.domain.paciente import Paciente


class FichaClinica(Base, TenantMixin, AuditMixin):
    """Ficha clínica y antecedentes de un paciente (1:1).

    En C-05 se crea la estructura vacía; el contenido clínico detallado
    y las evoluciones se completan en C-09.
    """

    __tablename__ = "ficha_clinica"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("paciente.id", ondelete="CASCADE"), nullable=False
    )
    antecedentes: Mapped[str | None] = mapped_column(Text, nullable=True)
    alergias: Mapped[str | None] = mapped_column(Text, nullable=True)
    medicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    habitos: Mapped[str | None] = mapped_column(Text, nullable=True)
    datos_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    paciente: Mapped["Paciente"] = relationship("Paciente", back_populates="ficha_clinica")

    __table_args__ = (
        UniqueConstraint("paciente_id", name="uq_ficha_clinica_paciente_id"),
        Index("ix_ficha_clinica_tenant_paciente", "tenant_id", "paciente_id"),
    )
