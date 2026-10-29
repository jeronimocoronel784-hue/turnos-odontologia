"""Sesión de refresh: token opaco hasheado, rotación por familia y revocación (C-03, RN-SE-04).

El valor que recibe el cliente NUNCA se guarda: se persiste su SHA-256. `familia_id`
agrupa la cadena de rotaciones para poder revocar toda la sesión cuando se detecta reúso.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, TenantMixin, ahora_utc
from app.infrastructure.db.base import Base


class RefreshToken(Base, TenantMixin):
    """Refresh token de un usuario interno, con estado de rotación y revocación."""

    __tablename__ = "refresh_token"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    familia_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    vence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reemplazado_por_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora_utc, nullable=False
    )

    __table_args__ = (
        Index("ix_refresh_token_tenant_usuario", "tenant_id", "usuario_id"),
        Index("ix_refresh_token_familia", "familia_id"),
    )

    def esta_vivo(self, ahora: datetime) -> bool:
        """Un refresh sirve solo si no fue revocado y no venció."""
        return self.revocado_at is None and self.vence_at > ahora
