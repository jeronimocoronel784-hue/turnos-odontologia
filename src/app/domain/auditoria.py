"""Auditoría append-only: solo INSERT+SELECT a nivel de permiso DB (D4, RN-SE-01).

Sin `updated_at` a propósito: el registro jamás se modifica. Retención mínima 5 años.
El enforcement real vive en la migración 001 (GRANT/REVOKE por rol); este modelo
documenta la intención y expone el helper `registrar`.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, ahora_utc
from app.infrastructure.db.base import Base


class Auditoria(Base):
    """Rastro inmutable de cambios críticos: actor, acción, entidad, antes/después."""

    __tablename__ = "auditoria"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad_id: Mapped[str] = mapped_column(String(60), nullable=False)
    antes: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    despues: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (
        Index("ix_auditoria_tenant_entidad", "tenant_id", "entidad", "entidad_id", "created_at"),
    )
