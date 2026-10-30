"""Token público de gestión para el paciente sin login (C-03, RN-SE-03).

Se entrega una sola vez y se guarda hasheado. Está atado a un `recurso` + `recurso_id`
y a un tenant, con vencimiento obligatorio: un token de un turno no sirve para otro.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, TenantMixin, ahora_utc, asegurar_utc
from app.infrastructure.db.base import Base


class TokenGestion(Base, TenantMixin):
    """Token opaco y vencible que habilita operar un recurso puntual sin cuenta."""

    __tablename__ = "token_gestion"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    recurso: Mapped[str] = mapped_column(String(40), nullable=False)
    recurso_id: Mapped[str] = mapped_column(String(60), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    vence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (
        Index("ix_token_gestion_tenant_recurso", "tenant_id", "recurso", "recurso_id"),
    )

    def sirve_para(self, recurso: str, recurso_id: str, ahora: datetime) -> bool:
        """Vigente, no revocado y atado exactamente al recurso pedido."""
        return (
            self.recurso == recurso
            and self.recurso_id == recurso_id
            and self.revocado_at is None
            and asegurar_utc(self.vence_at) > ahora
        )
