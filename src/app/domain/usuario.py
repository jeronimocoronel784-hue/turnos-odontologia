"""Usuario interno del consultorio: rol enum, email único por tenant, matrícula según rol."""

import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class RolUsuario(enum.StrEnum):
    """Roles RBAC v1 (matriz §03). El paciente NO es usuario: opera por token público."""

    DUENO = "dueno"
    RECEPCION = "recepcion"
    ODONTOLOGO = "odontologo"


class Usuario(Base, TenantMixin, AuditMixin):
    """Staff de un tenant. Email único por tenant, nunca global (borde multi-tenant)."""

    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(String(20), nullable=False)
    matricula: Mapped[str | None] = mapped_column(String(60), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_usuario_tenant_email"),
        CheckConstraint(
            "(rol != 'odontologo') OR (matricula IS NOT NULL AND matricula != '')",
            name="ck_usuario_matricula_odontologo",
        ),
        Index("ix_usuario_tenant_email", "tenant_id", "email"),
    )
