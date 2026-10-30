"""Sillón o box de atención odontológica por sucursal dentro del consultorio."""

import uuid

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.mixins import GUID, AuditMixin, TenantMixin
from app.infrastructure.db.base import Base


class Sillon(Base, TenantMixin, AuditMixin):
    """Box de atención odontológica. Único por (tenant_id, sucursal, nombre)."""

    __tablename__ = "sillon"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    sucursal: Mapped[str] = mapped_column(String(120), nullable=False, default="central")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "sucursal", "nombre", name="uq_sillon_tenant_sucursal_nombre"
        ),
        Index("ix_sillon_tenant_sucursal", "tenant_id", "sucursal"),
    )
